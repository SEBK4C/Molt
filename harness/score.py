#!/usr/bin/env python3
"""molt referee. Immutable once the manifest is frozen. Agent consumes JSON verdict only.

Usage: score.py --exp <id> --gguf <path> --server http://127.0.0.1:9021 [--lite]
       score.py --verify-only
Order: manifest check -> gates G1..G5 -> S components -> verdict JSON to stdout.
Exit 0 always (verdict carries pass/fail); exit 2 on manifest violation (tamper => auto-fail).

Checks are AST/exec/exact only — no LLM judges inside the loop (determinism protects the
ratchet). Weights and gate thresholds must match SPEC.md §4.
"""
import argparse
import hashlib
import json
import os
import re
import resource
import subprocess
import sys
import tempfile
import time
import urllib.request

H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H)
import tau_env  # noqa: E402  (harness-local module, manifest-covered)

WEIGHTS = {"bfcl_lite": 0.45, "tau_lite": 0.25, "evalplus_he": 0.20, "nested_json": 0.10}
GATES = {"size_gb_max": 121, "decode_tps_32k_min": 8.0, "prefill_tps_32k_min": 250.0}

ABSENT = "__ABSENT_OK__"  # ref sentinel: this argument may be omitted entirely


def manifest_ok():
    man = json.load(open(f"{H}/manifest.json"))
    for rel, want in man.items():
        p = os.path.join(H, rel)
        got = hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None
        if got != want:
            return False, rel
    return True, None


def chat(server, messages, tools=None, max_tokens=1024, temperature=0.0):
    body = {"model": "molt", "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(f"{server}/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


# --- gates -----------------------------------------------------------------
def g1_size(gguf):
    return os.path.getsize(gguf) / 1e9


def g2_loads(server):
    try:
        with urllib.request.urlopen(f"{server}/health", timeout=30) as r:
            return r.status == 200
    except Exception:
        return False


def g3_smoke(server):
    prompts = json.load(open(f"{H}/prompts/smoke.json"))  # 20 prompts
    for p in prompts:
        try:
            out = chat(server, p["messages"], p.get("tools"),
                       max_tokens=p.get("max_tokens", 512))
            txt = json.dumps(out["choices"][0]["message"], ensure_ascii=False)
        except Exception:
            return False
        if not txt or len(txt) < 8:
            return False
        if p.get("expect_no_nan", True) and re.search(r"\b(nan|inf)\b", txt, re.I):
            return False
        if len(set(txt[-200:].split())) < 5:  # repetition collapse
            return False
    return True


def g45_throughput(server):
    """decode/prefill t/s @32K: prefill fixed 32K-token doc, greedy 512 gen."""
    doc = open(f"{H}/prompts/ctx32k.txt").read()
    t0 = time.time()
    out = chat(server, [{"role": "user", "content": doc + "\nSummarize."}], max_tokens=512)
    dt = time.time() - t0
    u = out.get("usage", {})
    tim = out.get("timings", {})  # server timings preferred when present
    decode = tim.get("predicted_per_second") or (u.get("completion_tokens", 0) / max(dt, 1e-9))
    prefill = tim.get("prompt_per_second", 0.0)
    return decode, prefill


# --- output extraction ------------------------------------------------------
def extract_tool_calls(msg):
    """[{name, arguments-as-obj}] from an assistant message. Handles OpenAI-style
    msg.tool_calls and <tool_call>{...}</tool_call> blocks embedded in content."""
    calls = []
    for tc in (msg.get("tool_calls") or []):
        f = tc.get("function", tc)
        args = f.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {"__unparseable__": args}
        calls.append({"name": f.get("name"), "arguments": args, "id": tc.get("id")})
    if not calls:
        content = msg.get("content") or ""
        for m in re.findall(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", content, re.S):
            try:
                obj = json.loads(m)
                calls.append({"name": obj.get("name"),
                              "arguments": obj.get("arguments", {}), "id": None})
            except Exception:
                calls.append({"name": None, "arguments": {"__unparseable__": m}, "id": None})
    return calls


def extract_code(msg):
    """Python source from an assistant message: last ```python fence, else whole content."""
    content = msg.get("content") or ""
    fences = re.findall(r"```(?:python|py)?\s*\n(.*?)```", content, re.S)
    return fences[-1] if fences else content


def deep_eq(a, b):
    """Exact structural equality. bool never equals int; int equals numerically-equal float;
    strings never coerce to numbers."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(deep_eq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(deep_eq(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


def allows_absent(want):
    return isinstance(want, dict) and ABSENT in want.get("__any_of__", [])


def match_args(got, want):
    """deep_eq extended with ref-side alternates: {"__any_of__": [alt, ...]} at any node;
    the ABSENT sentinel inside __any_of__ marks an omittable argument (dict level)."""
    if isinstance(want, dict) and "__any_of__" in want:
        return any(match_args(got, alt) for alt in want["__any_of__"] if alt != ABSENT)
    if isinstance(want, dict):
        if not isinstance(got, dict):
            return False
        for k, wv in want.items():
            if k not in got:
                if allows_absent(wv):
                    continue
                return False
            if not match_args(got[k], wv):
                return False
        return set(got).issubset(set(want))  # extra (hallucinated) args fail
    if isinstance(want, list):
        return (isinstance(got, list) and len(got) == len(want)
                and all(match_args(g, w) for g, w in zip(got, want)))
    return deep_eq(got, want)


# --- S components (each returns [0,1]) -------------------------------------
def bfcl_lite(server, lite):
    return run_suite(server, "bfcl", n=50 if lite else 300)


def tau_lite(server):
    return run_suite(server, "tau", n=40)  # canned user scripts, deterministic env


def evalplus_he(server):
    return run_suite(server, "evalplus", n=164)  # sandboxed exec


def nested_json(server):
    return run_suite(server, "nested", n=100)


def run_suite(server, name, n):
    cases = json.load(open(f"{H}/prompts/{name}.json"))[:n]
    refs = json.load(open(f"{H}/refs/{name}.json"))
    ok = 0
    for c in cases:
        cid = str(c["id"])
        try:
            if name == "tau":
                result = tau_env.run_episode(
                    lambda msgs, tools, mt: chat(server, msgs, tools, max_tokens=mt),
                    c, extract_fn=extract_tool_calls)
            else:
                out = chat(server, c["messages"], c.get("tools"),
                           max_tokens=c.get("max_tokens", 1024))
                result = out["choices"][0]["message"]
            ok += int(check(name, result, refs[cid]))
        except Exception as e:  # one bad episode = one fail, never a crashed eval
            print(f"[suite {name}] case {cid} error: {type(e).__name__}: {e}", file=sys.stderr)
    return ok / len(cases)


# --- per-suite checkers ------------------------------------------------------
def check(name, msg, ref):
    """AST/exec/exact checks only. No LLM judges inside the loop (determinism)."""
    if name == "bfcl":
        return check_bfcl(msg, ref)
    if name == "tau":
        return check_tau(msg, ref)
    if name == "evalplus":
        return check_evalplus(msg, ref)
    if name == "nested":
        return check_nested(msg, ref)
    raise ValueError(f"unknown suite: {name}")


def check_bfcl(msg, ref):
    """ref: {"expect":"no_call"}  (irrelevance: model must NOT call a tool), or
       {"calls":[{"name":..,"arguments":{..}}], "order":"any"|"strict"}
    argument values may be {"__any_of__": [...]} (+ ABSENT sentinel for omittable args)."""
    got = extract_tool_calls(msg)
    if ref.get("expect") == "no_call":
        return len(got) == 0
    want = ref["calls"]
    if len(got) != len(want):
        return False

    def m(g, w):
        return g["name"] == w["name"] and match_args(g["arguments"], w["arguments"])

    if ref.get("order", "any") == "strict":
        return all(m(g, w) for g, w in zip(got, want))
    remaining = list(want)
    for g in got:
        for i, w in enumerate(remaining):
            if m(g, w):
                del remaining[i]
                break
        else:
            return False
    return True


def check_tau(final_state, ref):
    """final_state: env dict after the canned-script episode. Deep-equal vs ref terminal state."""
    return deep_eq(final_state, ref["final_state"])


def check_nested(msg, ref):
    """Exactly one tool call, exact name, arguments canonical-deep-equal (no alternates)."""
    got = extract_tool_calls(msg)
    if len(got) != 1 or got[0]["name"] != ref["name"]:
        return False
    # canonical re-serialize both sides (normalizes unicode escapes etc.), then deep-equal
    g = json.loads(json.dumps(got[0]["arguments"], ensure_ascii=False))
    w = json.loads(json.dumps(ref["arguments"], ensure_ascii=False))
    return deep_eq(g, w)


# --- evalplus sandbox --------------------------------------------------------
CANDIDATE_MARKER = "### __CANDIDATE_CODE__ ###"
_UNSHARE = None


def _have_unshare():
    global _UNSHARE
    if _UNSHARE is None:
        try:
            r = subprocess.run(["unshare", "-r", "-n", "true"], capture_output=True, timeout=10)
            _UNSHARE = (r.returncode == 0)
        except Exception:
            _UNSHARE = False
    return _UNSHARE


def sandboxed_exec(src, timeout=15):
    """Run python source in a throwaway sandbox: tmpdir cwd, rlimits, isolated -I interpreter,
    no network (net namespace via unshare when available, else strangled proxies).
    True iff exit code 0."""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "t.py")
        with open(path, "w") as f:
            f.write(src)
        env = {"PATH": "/usr/bin:/bin", "HOME": td, "TMPDIR": td, "PYTHONNOUSERSITE": "1",
               "http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9",
               "no_proxy": ""}

        def limits():
            resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout))
            resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
            resource.setrlimit(resource.RLIMIT_FSIZE, (8 << 20, 8 << 20))
            resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
            os.setsid()

        cmd = [sys.executable, "-I", path]
        if _have_unshare():
            cmd = ["unshare", "-r", "-n"] + cmd
        try:
            p = subprocess.run(cmd, cwd=td, env=env, capture_output=True,
                               timeout=timeout + 5, preexec_fn=limits)
            return p.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False


def check_evalplus(msg, ref):
    """ref: {"test_code": "<python source containing CANDIDATE_MARKER>"}; pass@1 by exec."""
    code = extract_code(msg)
    if not code.strip():
        return False
    src = ref["test_code"].replace(CANDIDATE_MARKER, code)
    return sandboxed_exec(src, timeout=ref.get("timeout", 15))


# --- main --------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp")
    ap.add_argument("--gguf")
    ap.add_argument("--server", default="http://127.0.0.1:9021")
    ap.add_argument("--lite", action="store_true")
    ap.add_argument("--verify-only", action="store_true")
    a = ap.parse_args()

    ok, bad = manifest_ok()
    if not ok:
        print(json.dumps({"exp": a.exp, "gates": "FAIL",
                          "reason": f"harness tampered: {bad}"}))
        sys.exit(2)
    if a.verify_only:
        print(json.dumps({"manifest": "OK",
                          "files": len(json.load(open(f"{H}/manifest.json")))}))
        return
    if not a.exp or not a.gguf:
        ap.error("--exp and --gguf required unless --verify-only")

    size = g1_size(a.gguf)
    if not g2_loads(a.server):
        print(json.dumps({"exp": a.exp, "lite": a.lite,
                          "gates": {"G1_size_gb": size, "G2_loads": False},
                          "gates_pass": False, "S": None}, indent=2))
        return
    dec, pre = g45_throughput(a.server)
    gates = {"G1_size_gb": size, "G2_loads": True, "G3_smoke": g3_smoke(a.server),
             "G4_decode_tps": dec, "G5_prefill_tps": pre}
    passed = (size <= GATES["size_gb_max"] and gates["G3_smoke"]
              and dec >= GATES["decode_tps_32k_min"] and pre >= GATES["prefill_tps_32k_min"])
    verdict = {"exp": a.exp, "lite": a.lite, "gates": gates, "gates_pass": passed, "S": None}
    if passed:
        comps = {"bfcl_lite": bfcl_lite(a.server, a.lite), "nested_json": nested_json(a.server)}
        if not a.lite:
            comps["tau_lite"] = tau_lite(a.server)
            comps["evalplus_he"] = evalplus_he(a.server)
        w = {k: WEIGHTS[k] for k in comps}
        z = sum(w.values())
        verdict["components"] = comps
        verdict["S"] = sum(comps[k] * w[k] for k in comps) / z
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()
