#!/usr/bin/env python3
"""Generate the EvalPlus HumanEval+ suite: harness/prompts/evalplus.json (164 problems) +
harness/refs/evalplus.json (per-problem sandbox test scripts).

Expected outputs are computed HERE, once, by running each problem's canonical solution on
base_input + a deterministic cap of plus_input (first N — logged, no silent truncation).
The ref test script embeds inputs+expected as literals; at eval time the candidate's code
replaces the marker and runs under score.py's sandbox (subprocess, rlimits, no net).
"""
import json
import os
import signal
import sys

from evalplus.data import get_human_eval_plus

H = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, H)
from score import CANDIDATE_MARKER  # noqa: E402

PLUS_CAP = 30  # plus inputs per problem (base inputs always all included)

SAFETY_HEADER = ("from typing import List, Dict, Tuple, Optional, Any, Union\n"
                 "import math\n")

EQ_HELPER = '''
import math as _math

def _eq(a, b, atol):
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_eq(x, y, atol) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_eq(a[k], b[k], atol) for k in a)
    if isinstance(a, float) or isinstance(b, float):
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return False
        if isinstance(a, bool) or isinstance(b, bool):
            return a is b
        return _math.isclose(a, b, rel_tol=1e-6, abs_tol=(atol or 1e-6))
    return a == b
'''

TEMPLATE = '''{safety}
{marker}

{eq}
import copy as _copy
_inputs = {inputs!r}
_expected = {expected!r}
_atol = {atol!r}
for _i, _e in zip(_inputs, _expected):
    _r = {entry}(*_copy.deepcopy(_i))
    assert _eq(_r, _e, _atol), "mismatch for input %r" % (_i,)
'''


class Timeout(Exception):
    pass


def _alarm(*_):
    raise Timeout()


def compute_expected(problem, inputs):
    """Run the canonical solution in-process (trusted dataset code) with a per-call alarm."""
    ns = {}
    exec(problem["prompt"] + problem["canonical_solution"], ns)  # noqa: S102
    fn = ns[problem["entry_point"]]
    out = []
    import copy
    signal.signal(signal.SIGALRM, _alarm)
    for inp in inputs:
        try:
            signal.alarm(5)
            out.append((True, fn(*copy.deepcopy(inp))))
        except Exception:
            out.append((False, None))
        finally:
            signal.alarm(0)
    return out


def usable(value):
    """Only keep expected values that survive a repr round-trip (embeddable as literal)."""
    try:
        return eval(repr(value), {"inf": float("inf"), "nan": float("nan")}) == value or True
    except Exception:
        return False


def main():
    problems = get_human_eval_plus()
    cases, refs = [], {}
    dropped_inputs = 0
    for tid in sorted(problems):
        p = problems[tid]
        base = list(p.get("base_input") or [])
        plus = list(p.get("plus_input") or [])[:PLUS_CAP]
        raw_inputs = base + plus
        results = compute_expected(p, raw_inputs)
        inputs, expected = [], []
        for inp, (ok, val) in zip(raw_inputs, results):
            if ok and usable(val) and usable(inp):
                inputs.append(inp)
                expected.append(val)
            else:
                dropped_inputs += 1
        if not inputs:
            print(f"[build_evalplus] SKIP {tid}: no usable inputs", file=sys.stderr)
            continue
        cid = tid.replace("/", "_").lower()  # HumanEval/0 -> humaneval_0
        test_code = TEMPLATE.format(safety=SAFETY_HEADER, marker=CANDIDATE_MARKER,
                                    eq=EQ_HELPER, inputs=inputs, expected=expected,
                                    atol=p.get("atol", 0) or 0, entry=p["entry_point"])
        cases.append({"id": cid, "max_tokens": 1280,
                      "messages": [{"role": "user", "content":
                          "Complete the following Python function. Reply with a single "
                          "```python code block containing the COMPLETE function definition "
                          "(signature included, plus any imports you need):\n\n```python\n"
                          + p["prompt"] + "```"}]})
        refs[cid] = {"test_code": test_code, "timeout": 15}

    hp = os.path.join(H, "prompts", "evalplus.json")
    hr = os.path.join(H, "refs", "evalplus.json")
    with open(hp, "w") as f:
        json.dump(cases, f, ensure_ascii=False, indent=1)
    with open(hr, "w") as f:
        json.dump(refs, f, ensure_ascii=False, indent=1)
    print(f"[build_evalplus] {len(cases)} problems (plus_input capped at {PLUS_CAP}/problem, "
          f"{dropped_inputs} inputs dropped as non-embeddable/erroring) -> {hp}")


if __name__ == "__main__":
    main()
