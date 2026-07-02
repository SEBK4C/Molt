#!/usr/bin/env python3
"""Generate the nested-JSON stress suite: harness/prompts/nested.json (100 cases) +
harness/refs/nested.json (specification-derived refs — the ref IS the exact arguments the
prompt demands, so no FP8 endpoint is needed; FP8 goldens may later REPLACE these for
behavioral parity, followed by a manifest re-freeze).

Families (10 cases each): deep_uniform, deep_mixed, escapes, unicode_keys, unicode_values,
wide_64_args, big_numbers, floats, empty_structures, lookalike_keys.
Deterministic: seed 20260702. Expected completion sizes kept ≤ ~1500 tokens (max_tokens 2048).
"""
import json
import os
import random

H = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = 20260702

# Each case ships a schema mirroring its exact payload: llama-server grammar-constrains tool
# calls from the schema, and a propertyless/additionalProperties:true schema collapses the
# grammar to '{}' (Phase-0 discovery: nested scored 0/25 with the model FORCED to emit empty
# args). Real tools ship real schemas; the stress stays on VALUE fidelity.
def schema_for(v):
    if isinstance(v, bool):
        return {"type": "boolean"}
    if v is None:
        return {"type": "null"}
    if isinstance(v, int):
        return {"type": "integer"}
    if isinstance(v, float):
        return {"type": "number"}
    if isinstance(v, str):
        return {"type": "string"}
    if isinstance(v, dict):
        return {"type": "object",
                "properties": {k: schema_for(x) for k, x in v.items()},
                "required": list(v.keys()),
                "additionalProperties": False}
    if isinstance(v, list):
        subs = {json.dumps(schema_for(x), sort_keys=True) for x in v}
        items = [json.loads(s) for s in sorted(subs)]
        it = items[0] if len(items) == 1 else {"anyOf": items}
        return {"type": "array", "items": it,
                "minItems": len(v), "maxItems": len(v)}
    raise TypeError(type(v))


def tool_for(args):
    return {"type": "function", "function": {
        "name": "submit_payload",
        "description": "Submit a structured payload for processing. Arguments are passed through verbatim.",
        "parameters": schema_for(args)}}

WORDS = "alpha beta gamma delta epsilon zeta eta theta iota kappa lam mu nu xi omicron pi rho".split()


def deep_uniform(rng, i):
    depth = 8 + (i % 10)
    leaf = {"value": rng.randint(1, 999), "tag": rng.choice(WORDS)}
    node = leaf
    for d in range(depth):
        node = {f"level_{depth - d}": node, "sibling": rng.choice(WORDS)}
    return node


def deep_mixed(rng, i):
    depth = 6 + (i % 8)
    node = [rng.randint(0, 9), rng.choice(WORDS)]
    for d in range(depth):
        node = {"list": [node, rng.randint(10, 99)]} if d % 2 else [node, {"k": rng.choice(WORDS)}]
    return {"root": node, "depth": depth}


def escapes(rng, i):
    samples = [
        'line1\nline2\r\nline3\ttabbed',
        'she said "quote" and \\backslash\\ and /slash/',
        'null-adjacent:  bell: end',
        'many \\\\ backslashes \\\\\\\\ here',
        'json-in-string: {"a": [1, 2, {"b": "c"}]}',
        'trailing spaces   and\ttabs\t',
        "single'quotes' and `backticks`",
        'unicode escape target:   and   seps',
        'percent %s %% and braces {} {{}}',
        'mixed: "\\n" literal vs \n real newline',
    ]
    return {"text": samples[i % len(samples)], "index": i,
            "nested": {"again": samples[(i + 3) % len(samples)]}}


def unicode_keys(rng, i):
    keys = ["键", "🔑", "ключ", "clé", "מפתח", "κλειδί", "kľúč", "nøkkel", "açar", "kulcs"]
    k = keys[i % len(keys)]
    return {k: {"内側": rng.randint(1, 99), "λ": rng.choice(WORDS)},
            "plain": "ascii_value", f"{k}_2": [k, "混合", rng.randint(100, 999)]}


def unicode_values(rng, i):
    vals = ["こんにちは世界", "Grüße aus Köln", "�", "🎛️🎚️", "Ω≈ç√∫", "ᚱᚢᚾᛖᛋ",
            "中文测试字符串", "علامات الترقيم", "𝔪𝔞𝔱𝔥 𝔟𝔬𝔩𝔡", "é combining"]
    return {"greeting": vals[i % len(vals)], "mirror": vals[(i + 5) % len(vals)],
            "wrap": {"inner": [vals[(i + 2) % len(vals)], i]}}


def wide_64_args(rng, i):
    args = {}
    for j in range(64):
        t = j % 4
        if t == 0:
            args[f"param_{j:02d}"] = rng.randint(-500, 500)
        elif t == 1:
            args[f"param_{j:02d}"] = rng.choice(WORDS)
        elif t == 2:
            args[f"param_{j:02d}"] = rng.random() < 0.5
        else:
            args[f"param_{j:02d}"] = [rng.randint(0, 9), rng.choice(WORDS)]
    return args


def big_numbers(rng, i):
    return {"int64_edge": 9007199254740993 + i,          # > 2^53: float round-trip breaks it
            "negative": -(2**53) - 7 - i,
            "large": rng.randint(10**15, 10**16),
            "small_group": [rng.randint(-9, 9) for _ in range(5)],
            "id_like": int("9" * 15) - i}


def floats(rng, i):
    return {"half": 0.5, "quarter": 3.25 + i,
            "tiny": 1e-07, "big_e": 2.5e15,
            "pi_ish": 3.141592653589793,
            "list": [0.1, 0.25, 1.75, -42.5],
            "nested": {"ratio": (i + 1) * 0.125}}


def empty_structures(rng, i):
    shells = [{}, [], "", {"empty_obj": {}}, {"empty_arr": []}, {"empty_str": ""},
              [[]], [{}], {"a": {"b": {"c": {}}}}, {"mix": [{}, [], "", 0, False, None]}]
    return {"shell": shells[i % len(shells)], "marker": i,
            "also": {"deep_empty": [[], {}, [[], {}]]}}


def lookalike_keys(rng, i):
    pairs = [("a", "а"), ("key", "kеy"), ("O0", "0O"), ("l1", "1l"), ("x ", " x"),
             ("A", "Α"), ("data", "dаta"), ("test", "tеst"), ("v_1", "v-1"), ("π", "п")]
    k1, k2 = pairs[i % len(pairs)]
    return {k1: "first", k2: "second", "note": "keys differ (cyrillic/greek/space lookalikes)"}


FAMILIES = [("deep_uniform", deep_uniform), ("deep_mixed", deep_mixed), ("escapes", escapes),
            ("unicode_keys", unicode_keys), ("unicode_values", unicode_values),
            ("wide_64_args", wide_64_args), ("big_numbers", big_numbers), ("floats", floats),
            ("empty_structures", empty_structures), ("lookalike_keys", lookalike_keys)]

PROMPT = (
    "Call the tool `submit_payload` exactly once. Its arguments must be EXACTLY the following "
    "JSON — every key, every value, every nesting level reproduced verbatim, with no additions, "
    "omissions, reordering of arrays, or reformatting of values:\n\n{payload}\n\n"
    "Reply with only the tool call."
)


def main():
    cases, refs = [], {}
    n = 0
    for fam, fn in FAMILIES:
        for i in range(10):
            rng = random.Random(SEED * 1000 + n)  # per-case stream: order-independent
            args = fn(rng, i)
            cid = f"nested_{n:03d}_{fam}"
            payload = json.dumps(args, ensure_ascii=False, indent=2)
            cases.append({"id": cid, "family": fam, "max_tokens": 4096,
                          "tools": [tool_for(args)],
                          "messages": [{"role": "user",
                                        "content": PROMPT.format(payload=payload)}]})
            refs[cid] = {"name": "submit_payload", "arguments": args}
            n += 1

    hp = os.path.join(H, "prompts", "nested.json")
    hr = os.path.join(H, "refs", "nested.json")
    with open(hp, "w") as f:
        json.dump(cases, f, ensure_ascii=False, indent=1)
    with open(hr, "w") as f:
        json.dump(refs, f, ensure_ascii=False, indent=1)
    sizes = [len(json.dumps(c, ensure_ascii=False)) for c in cases]
    print(f"[build_nested] {len(cases)} cases -> {hp} (case bytes min/med/max "
          f"{min(sizes)}/{sorted(sizes)[50]}/{max(sizes)}), refs -> {hr}")


if __name__ == "__main__":
    main()
