#!/usr/bin/env python3
"""Generate the BFCL-lite suite: harness/prompts/bfcl.json (300 stratified cases) +
harness/refs/bfcl.json (from upstream ground truth — no FP8 endpoint needed).

Source: gorilla@main berkeley-function-call-leaderboard/bfcl_eval/data (BFCL v4, JSONL):
  simple_python (120) + parallel (90) + irrelevance (90) = 300, per SPEC §4/§5.
Case order is a seeded weighted round-robin so any prefix is itself stratified —
eval-lite takes the first 50 (=> 20 simple / 15 parallel / 15 irrelevance).

Mappings:
- BFCL param schema types -> JSON Schema: dict->object, float->number, tuple->array, any->string.
- Function names with dots (math.factorial) -> underscores in BOTH tools and refs (OpenAI-safe).
- ground_truth {fn: {param: [alternates]}} -> {"calls":[{name, arguments:{param:
  {"__any_of__": [...]}}}]}; the "" alternate additionally allows omission (ABSENT sentinel).
- irrelevance -> {"expect": "no_call"}.
The fetched raw upstream files are cached in harness/build/cache/ for reproducibility.
"""
import json
import os
import random
import sys
import urllib.request

H = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, H)
from score import ABSENT  # noqa: E402

BASE = ("https://raw.githubusercontent.com/ShishirPatil/gorilla/main/"
        "berkeley-function-call-leaderboard/bfcl_eval/data")
CACHE = os.path.join(H, "build", "cache")
SEED = 20260702
STRATA = [("simple", "BFCL_v4_simple_python.json", 120, True),
          ("parallel", "BFCL_v4_parallel.json", 90, True),
          ("irrelevance", "BFCL_v4_irrelevance.json", 90, False)]

TYPE_MAP = {"dict": "object", "float": "number", "tuple": "array", "any": "string",
            "integer": "integer", "string": "string", "boolean": "boolean",
            "array": "array", "number": "number", "object": "object", "long": "integer",
            "double": "number", "char": "string", "byte": "integer", "short": "integer"}


def fetch(rel):
    os.makedirs(CACHE, exist_ok=True)
    local = os.path.join(CACHE, rel.replace("/", "__"))
    if not os.path.exists(local):
        urllib.request.urlretrieve(f"{BASE}/{rel}", local)
    rows = []
    with open(local) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def conv_schema(node):
    if not isinstance(node, dict):
        return node
    out = {}
    for k, v in node.items():
        if k == "type" and isinstance(v, str):
            out[k] = TYPE_MAP.get(v, "string")
        elif k in ("properties",):
            out[k] = {pk: conv_schema(pv) for pk, pv in v.items()}
        elif k in ("items",):
            out[k] = conv_schema(v)
        elif isinstance(v, dict):
            out[k] = conv_schema(v)
        else:
            out[k] = v
    return out


def sanitize(name):
    return name.replace(".", "_")


def conv_tools(functions):
    tools = []
    for fn in functions:
        tools.append({"type": "function", "function": {
            "name": sanitize(fn["name"]),
            "description": fn.get("description", ""),
            "parameters": conv_schema(fn.get("parameters", {"type": "dict", "properties": {}}))}})
    return tools


def conv_alt(a):
    """One concrete alternate. Dict alternates have per-key alternates-lists again."""
    if isinstance(a, dict):
        return {k: (conv_alts(v) if isinstance(v, list) else conv_alt(v)) for k, v in a.items()}
    return a


def conv_alts(alts):
    out = [conv_alt(a) for a in alts]
    if "" in alts:
        out.append(ABSENT)  # "" upstream marks an omittable parameter
    return {"__any_of__": out}


def conv_ground_truth(gt):
    calls = []
    for entry in gt:
        (fname, params), = entry.items()
        calls.append({"name": sanitize(fname),
                      "arguments": {p: conv_alts(v) if isinstance(v, list) else conv_alt(v)
                                    for p, v in params.items()}})
    return {"calls": calls, "order": "any"}


def main():
    rng = random.Random(SEED)
    per_stratum = []
    for label, fname, want, has_gt in STRATA:
        rows = fetch(fname)
        gts = {}
        if has_gt:
            gts = {r["id"]: r["ground_truth"] for r in fetch(f"possible_answer/{fname}")}
            rows = [r for r in rows if r["id"] in gts]
        rows = sorted(rows, key=lambda r: r["id"])
        rng.shuffle(rows)
        if len(rows) < want:
            print(f"[build_bfcl] WARNING {label}: only {len(rows)} rows (< {want})", file=sys.stderr)
        picked = rows[:want]
        cases = []
        for r in picked:
            q = r["question"]
            messages = q[0] if q and isinstance(q[0], list) else q
            case = {"id": f"bfcl_{r['id']}", "stratum": label,
                    "messages": messages, "max_tokens": 2048}
            if r.get("function"):
                case["tools"] = conv_tools(r["function"])
            ref = conv_ground_truth(gts[r["id"]]) if has_gt else {"expect": "no_call"}
            cases.append((case, ref))
        per_stratum.append((label, want, cases))
        print(f"[build_bfcl] {label}: picked {len(cases)}/{len(rows)}")

    # weighted round-robin: per block of 10 -> 4 simple, 3 parallel, 3 irrelevance
    weights = {"simple": 4, "parallel": 3, "irrelevance": 3}
    queues = {label: list(cases) for label, _, cases in per_stratum}
    ordered = []
    while any(queues.values()):
        for label, w in weights.items():
            take, queues[label] = queues[label][:w], queues[label][w:]
            ordered.extend(take)

    prompts = [c for c, _ in ordered]
    refs = {c["id"]: r for c, r in ordered}
    with open(os.path.join(H, "prompts", "bfcl.json"), "w") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=1)
    with open(os.path.join(H, "refs", "bfcl.json"), "w") as f:
        json.dump(refs, f, ensure_ascii=False, indent=1)
    head = [p["stratum"] for p in prompts[:50]]
    print(f"[build_bfcl] wrote {len(prompts)} cases; eval-lite prefix(50): "
          f"{ {s: head.count(s) for s in set(head)} }")


if __name__ == "__main__":
    main()
