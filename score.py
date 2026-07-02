#!/usr/bin/env python3
"""molt referee. Immutable. Agent consumes JSON verdict only.

Usage: score.py --exp <id> --gguf <path> --server http://127.0.0.1:9021 [--lite]
Order: manifest check -> gates G1..G5 -> S components -> verdict JSON to stdout + journal fragment.
Exit 0 always (verdict carries pass/fail); exit 2 on manifest violation (tamper => auto-fail).
"""
import argparse, hashlib, json, os, statistics, subprocess, sys, time
import urllib.request

H = os.path.dirname(os.path.abspath(__file__))
WEIGHTS = {"bfcl_lite": 0.45, "tau_lite": 0.25, "evalplus_he": 0.20, "nested_json": 0.10}
GATES = {"size_gb_max": 121, "decode_tps_32k_min": 8.0, "prefill_tps_32k_min": 250.0}

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
    if tools: body["tools"] = tools
    req = urllib.request.Request(f"{server}/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)

# --- gates -----------------------------------------------------------------
def g1_size(gguf): return os.path.getsize(gguf) / 1e9
def g3_smoke(server):
    prompts = json.load(open(f"{H}/prompts/smoke.json"))          # 20 prompts
    for p in prompts:
        out = chat(server, p["messages"], p.get("tools"))
        txt = json.dumps(out["choices"][0]["message"])
        if not txt or "nan" in txt.lower() and p["expect_no_nan"]: return False
        if len(set(txt[-200:].split())) < 5: return False          # repetition collapse
    return True
def g45_throughput(server):
    """decode t/s @32K: prefill fixed 32K-token doc from prompts/ctx32k.txt, greedy 512 gen."""
    doc = open(f"{H}/prompts/ctx32k.txt").read()
    t0 = time.time(); out = chat(server, [{"role": "user", "content": doc + "\nSummarize."}],
                                 max_tokens=512)
    u = out.get("usage", {}); dt = time.time() - t0
    # server timings preferred when present:
    tim = out.get("timings", {})
    decode = tim.get("predicted_per_second") or (u.get("completion_tokens", 0) / max(dt, 1e-9))
    prefill = tim.get("prompt_per_second", 0.0)
    return decode, prefill

# --- S components (each returns [0,1]) -------------------------------------
def bfcl_lite(server, lite):   # AST-match on frozen slice; refs in harness/refs/ (agent-forbidden)
    return run_suite(server, "bfcl", n=50 if lite else 300)
def tau_lite(server):          return run_suite(server, "tau", n=40)       # canned user scripts
def evalplus_he(server):       return run_suite(server, "evalplus", n=164) # sandboxed exec
def nested_json(server):       return run_suite(server, "nested", n=100)
def run_suite(server, name, n):
    cases = json.load(open(f"{H}/prompts/{name}.json"))[:n]
    refs  = json.load(open(f"{H}/refs/{name}.json"))
    ok = 0
    for c in cases:
        out = chat(server, c["messages"], c.get("tools"))
        ok += int(check(name, out["choices"][0]["message"], refs[c["id"]]))
    return ok / len(cases)
def check(name, msg, ref):
    """AST/exec/exact checks only. No LLM judges inside the loop (determinism)."""
    raise NotImplementedError  # per-suite checkers: bfcl AST match, tau state match,
                               # evalplus exec, nested-json canonicalized deep-equal

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True); ap.add_argument("--gguf", required=True)
    ap.add_argument("--server", default="http://127.0.0.1:9021"); ap.add_argument("--lite", action="store_true")
    a = ap.parse_args()

    ok, bad = manifest_ok()
    if not ok:
        print(json.dumps({"exp": a.exp, "gates": "FAIL", "reason": f"harness tampered: {bad}"})); sys.exit(2)

    size = g1_size(a.gguf)
    dec, pre = g45_throughput(a.server)
    gates = {"G1_size_gb": size, "G3_smoke": g3_smoke(a.server),
             "G4_decode_tps": dec, "G5_prefill_tps": pre}
    passed = (size <= GATES["size_gb_max"] and gates["G3_smoke"]
              and dec >= GATES["decode_tps_32k_min"] and pre >= GATES["prefill_tps_32k_min"])
    verdict = {"exp": a.exp, "lite": a.lite, "gates": gates, "gates_pass": passed, "S": None}
    if passed:
        comps = {"bfcl_lite": bfcl_lite(a.server, a.lite), "nested_json": nested_json(a.server)}
        if not a.lite:
            comps["tau_lite"] = tau_lite(a.server); comps["evalplus_he"] = evalplus_he(a.server)
        w = {k: WEIGHTS[k] for k in comps}; z = sum(w.values())
        verdict["components"] = comps
        verdict["S"] = sum(comps[k] * w[k] for k in comps) / z
    print(json.dumps(verdict, indent=2))

if __name__ == "__main__":
    main()
