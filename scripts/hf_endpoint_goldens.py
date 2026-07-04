#!/usr/bin/env python3
"""HG1 (HUMAN gate) — FP8 golden refs + self-generated agent traces from a dedicated
HF Inference Endpoint. SPENDS GPU CREDITS: never run without --confirm-spend (real mode).

Safe modes (no endpoint, no spend):
  --dry-run                     print the exact endpoint call + cost estimate and exit
  --mock http://127.0.0.1:PORT  drive an existing OpenAI-compatible URL (used by the pytest mock)

Real mode (HUMAN ONLY):
  .venv/bin/python scripts/hf_endpoint_goldens.py --confirm-spend \
      [--repo deepreinforce-ai/Ornith-1.0-397B-FP8] [--trace-tokens 5000000]

What it does:
 1. create_inference_endpoint (8xH100, vLLM OpenAI image), wait ready (FP8 397B load: ~15-40 min)
 2. goldens: drive harness/prompts/{smoke,nested,bfcl}.json single-turn greedy + tau episodes
    through tau_env -> write refs_fp8/<suite>.fp8.json (NEXT TO, never over, harness/refs/;
    promotion into harness/refs/ + manifest re-freeze + re-ε is a separate human decision)
 3. traces: sample tool-task prompts at temperature 0.7 -> corpora/fp8_traces.jsonl (+ .txt
    rendered for imatrix) until --trace-tokens completion tokens are collected
 4. ALWAYS pause+delete the endpoint in a finally block.

Cost estimate (verify instance existence + price via
https://api.endpoints.huggingface.cloud/v2/provider before every billable run):
  aws nvidia-h200 x4 (ap-northeast-2) = $20/h as of 2026-07-04. Load ~0.5 h + goldens
  ~1.5 h + 5M trace tokens ~2-3 h. Wrap real runs in a wall-clock `timeout` sized to the
  budget cap (16200 s x $20/h = $90). Teardown immediately after.
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "harness"))

ENDPOINT_NAME = "molt-ornith-fp8-goldens"
DEFAULT_REPO = "deepreinforce-ai/Ornith-1.0-397B-FP8"
# 2026-07-04: h100-x8/us-east-1 no longer exists in the endpoints catalog (verify instance
# existence via api.endpoints.huggingface.cloud/v2/provider before every billable run).
# Account quota (support ticket 2026-07-04): rtx-pro-6000 ≤ 16 accelerators; h200 ≤ 2; a100 ≤ 4.
# rtx-pro-6000-x8 = 768 GB VRAM (Blackwell, native FP8), $22/h — most VRAM per dollar and the
# only ≥420 GB instance within quota. Fallback (quota-blocked as of today, kept for reference):
# h200-x4 ap-northeast-2 (564 GB, $20/h).
INSTANCE = {"vendor": "aws", "region": "us-east-2", "accelerator": "gpu",
            "instance_type": "nvidia-rtx-pro-6000", "instance_size": "x8", "type": "protected"}
FALLBACK_INSTANCE = {"vendor": "aws", "region": "ap-northeast-2", "accelerator": "gpu",
                     "instance_type": "nvidia-h200", "instance_size": "x4", "type": "protected"}
COST_PER_H = 22.0

TRACE_SEED_TASKS = [
    "Book a table for {n} at a {cuisine} restaurant on {day} evening and text me the confirmation.",
    "Find the cheapest flight from {a} to {b} next {day}, then add it to my calendar.",
    "Refund order {oid}: the {item} arrived broken. Follow store policy.",
    "Create a JSON config for a service named '{name}' with {n} replicas, health checks, and env overrides.",
    "Query the orders database for totals over ${n}00 this month and summarize by region.",
    "Update ticket {oid}: set priority to high, assign to the on-call engineer, add a status note.",
    "Plan a 3-step tool workflow to migrate repo '{name}' from svn to git, then execute it.",
    "Parse this address into structured fields and validate the postal code: {n} {name} Street, Springfield.",
]


def chat(server, messages, tools=None, max_tokens=1024, temperature=0.0, api_key=None):
    body = {"model": "molt-fp8", "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(f"{server}/v1/chat/completions",
                                 data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def golden_suites(server, out_dir, api_key=None, limit=None, log=print):
    from score import extract_tool_calls  # harness import, read-only
    import tau_env
    os.makedirs(out_dir, exist_ok=True)
    H = os.path.join(REPO_ROOT, "harness")

    # single-turn suites: nested -> {name, arguments}; bfcl -> {calls, order}; smoke -> raw text
    # cases run concurrently (results keyed by id, ordering irrelevant); serial was ~750
    # thinking-model calls and blew the wall-clock budget on a billed-by-the-hour endpoint
    def one_case(suite, c):
        cid = str(c.get("id"))
        try:
            r = chat(server, c["messages"], c.get("tools"),
                     max_tokens=c.get("max_tokens", 1024), api_key=api_key)
            msg = r["choices"][0]["message"]
            calls = extract_tool_calls(msg)
            if suite == "nested":
                res = ({"name": calls[0]["name"], "arguments": calls[0]["arguments"]}
                       if len(calls) == 1 else {"error": f"{len(calls)} calls"})
            elif suite == "bfcl":
                res = ({"expect": "no_call"} if not calls else
                       {"calls": [{"name": x["name"], "arguments": x["arguments"]}
                                  for x in calls], "order": "any"})
            else:
                res = {"content": msg.get("content")}
        except Exception as e:
            res = {"error": f"{type(e).__name__}: {e}"}
        log(f"[goldens] {suite} {cid} done")
        return cid, res

    for suite in ("nested", "bfcl", "smoke"):
        cases = json.load(open(f"{H}/prompts/{suite}.json"))[:limit]
        with cf.ThreadPoolExecutor(8) as ex:
            out = dict(ex.map(lambda c: one_case(suite, c), cases))
        path = os.path.join(out_dir, f"{suite}.fp8.json")
        with open(path, "w") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        log(f"[goldens] wrote {path} ({len(out)} entries)")

    # tau: full episodes -> terminal states
    cases = json.load(open(f"{H}/prompts/tau.json"))[:limit]
    out = {}
    for c in cases:
        try:
            final = tau_env.run_episode(
                lambda m, t, mt: chat(server, m, t, max_tokens=mt, api_key=api_key),
                c, extract_fn=extract_tool_calls)
            out[str(c["id"])] = {"final_state": final}
        except Exception as e:
            out[str(c["id"])] = {"error": f"{type(e).__name__}: {e}"}
        log(f"[goldens] tau {c['id']} done")
    path = os.path.join(out_dir, "tau.fp8.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    log(f"[goldens] wrote {path} ({len(out)} entries)")


def generate_traces(server, target_tokens, out_jsonl, api_key=None, concurrency=8, log=print):
    import itertools
    import random
    rng = random.Random(4242)
    fills = {"n": lambda: rng.randint(2, 9), "cuisine": lambda: rng.choice(["thai", "oaxacan", "basque"]),
             "day": lambda: rng.choice(["tuesday", "friday", "sunday"]),
             "a": lambda: rng.choice(["SFO", "BER", "NRT"]), "b": lambda: rng.choice(["JFK", "LIS", "SIN"]),
             "oid": lambda: f"T{rng.randint(1000, 9999)}", "item": lambda: rng.choice(["lamp", "kettle", "monitor"]),
             "name": lambda: rng.choice(["orchid", "falcon", "quartz"])}

    def prompt_stream():
        for i in itertools.count():
            t = TRACE_SEED_TASKS[i % len(TRACE_SEED_TASKS)]
            yield t.format(**{k: f() for k, f in fills.items() if "{" + k + "}" in t})

    got_tokens = 0
    lock_file = out_jsonl + ".part"
    with open(lock_file, "a") as f, cf.ThreadPoolExecutor(concurrency) as ex:
        stream = prompt_stream()

        def one(p):
            try:
                r = chat(server, [{"role": "user", "content": p}], max_tokens=800,
                         temperature=0.7, api_key=api_key)
                return p, r["choices"][0]["message"].get("content") or "", \
                    r.get("usage", {}).get("completion_tokens", 0)
            except Exception:
                return p, None, 0

        while got_tokens < target_tokens:
            batch = [next(stream) for _ in range(concurrency * 4)]
            for p, resp, toks in ex.map(one, batch):
                if resp:
                    f.write(json.dumps({"prompt": p, "response": resp}, ensure_ascii=False) + "\n")
                    got_tokens += toks
            f.flush()
            log(f"[traces] {got_tokens}/{target_tokens} completion tokens")
    os.replace(lock_file, out_jsonl)
    log(f"[traces] wrote {out_jsonl}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--mock", metavar="URL", help="drive this URL instead of creating an endpoint")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--confirm-spend", action="store_true")
    ap.add_argument("--trace-tokens", type=int, default=5_000_000)
    ap.add_argument("--fallback-instance", action="store_true",
                    help="use FALLBACK_INSTANCE (a100-x8 us-east-1, W8A16) instead of h200-x4")
    ap.add_argument("--skip-traces", action="store_true")
    ap.add_argument("--limit", type=int, help="cases per suite (mock/testing)")
    ap.add_argument("--out-dir", default=os.path.join(REPO_ROOT, "refs_fp8"))
    a = ap.parse_args(argv)
    instance = FALLBACK_INSTANCE if a.fallback_instance else INSTANCE

    est_h = 0.5 + 1.5 + (0 if a.skip_traces else 2.5 * a.trace_tokens / 5_000_000)
    if a.dry_run:
        print(f"[dry-run] create_inference_endpoint(name={ENDPOINT_NAME!r}, repository={a.repo!r},")
        print(f"          framework='pytorch', task='text-generation', **{instance},")
        print("          custom_image={'health_route': '/health', 'port': 8000,")
        print("            'url': 'vllm/vllm-openai:latest',")
        print("            'env': {'MODEL_ID': '/repository', 'MAX_MODEL_LEN': '32768'}})")
        print(f"[dry-run] estimated {est_h:.1f} h x ${COST_PER_H}/h ~= ${est_h * COST_PER_H:.0f} "
              f"(verify current pricing before running)")
        return 0

    if a.mock:
        golden_suites(a.mock, a.out_dir, limit=a.limit)
        if not a.skip_traces:
            generate_traces(a.mock, a.trace_tokens,
                            os.path.join(REPO_ROOT, "corpora", "fp8_traces.jsonl"))
        return 0

    if not a.confirm_spend:
        print("REFUSING: real mode spends GPU credits. Pass --confirm-spend (HUMAN gate HG1), "
              "or use --dry-run / --mock.", file=sys.stderr)
        return 3

    from huggingface_hub import create_inference_endpoint, get_inference_endpoint
    token = os.environ.get("HF_TOKEN")
    try:
        ep = get_inference_endpoint(ENDPOINT_NAME, token=token)
        print(f"[endpoint] reusing existing {ENDPOINT_NAME} (status={ep.status})")
    except Exception:
        ep = create_inference_endpoint(
            ENDPOINT_NAME, repository=a.repo, framework="pytorch", task="text-generation",
            vendor=instance["vendor"], region=instance["region"],
            accelerator=instance["accelerator"], instance_type=instance["instance_type"],
            instance_size=instance["instance_size"], type=instance["type"],
            custom_image={"health_route": "/health", "port": 8000,
                          "url": "vllm/vllm-openai:latest",
                          "env": {"MODEL_ID": "/repository", "MAX_MODEL_LEN": "32768"}},
            token=token)
    try:
        print("[endpoint] waiting for ready (FP8 397B load: expect 15-40 min)...")
        ep.wait(timeout=3600)
        url = ep.url
        print(f"[endpoint] ready: {url}")
        golden_suites(url, a.out_dir, api_key=token, limit=a.limit)
        if not a.skip_traces:
            generate_traces(url, a.trace_tokens,
                            os.path.join(REPO_ROOT, "corpora", "fp8_traces.jsonl"),
                            api_key=token)
    finally:
        print("[endpoint] tearing down (pause + delete)...")
        try:
            ep.pause()
        except Exception:
            pass
        try:
            ep.delete()
            print("[endpoint] deleted.")
        except Exception as e:
            print(f"[endpoint] DELETE FAILED — REMOVE MANUALLY IN THE HF UI: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
