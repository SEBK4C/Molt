"""Fixture tests for teacher_validate (protocol P1): known-good passes, corrupted fails,
malformed never crashes. Mirrors the harness builders' round-trip validation style."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from teacher_validate import deep_eq, validate_nested, validate_code


DEMANDED = {"name": "café_ünïcode", "n": 2**53 + 1, "pi": 3.5, "flag": True,
            "nested": {"keys": ["Ω", " "], "empty": {}, "big": [1, 2.0, False]}}


def test_nested_good():
    ok, why = validate_nested(DEMANDED, '{"name": "caf\\u00e9_\\u00fcn\\u00efcode", '
                              '"n": 9007199254740993, "pi": 3.5, "flag": true, "nested": '
                              '{"keys": ["\\u03a9", "\\u2028"], "empty": {}, "big": [1, 2.0, false]}}')
    assert ok, why


def test_nested_bigint_corrupted():
    bad = dict(DEMANDED, n=float(2**53 + 1))  # the classic >2^53 float collapse
    import json
    ok, why = validate_nested(DEMANDED, json.dumps(bad))
    assert not ok and "deep_eq" in why


def test_nested_bool_int_confusion():
    ok, _ = validate_nested({"flag": True}, '{"flag": 1}')
    assert not ok
    ok, _ = validate_nested({"n": 1}, '{"n": true}')
    assert not ok


def test_nested_int_float_numeric_equal():
    ok, why = validate_nested({"x": 2}, '{"x": 2.0}')
    assert ok, why  # referee semantics: int == float numerically


def test_nested_malformed_never_crashes():
    for junk in ['{"a": }', "", None, "[1,2", "'single'"]:
        ok, why = validate_nested({"a": 1}, junk)
        assert not ok and why


def test_nested_key_order_irrelevant_value_order_not():
    ok, _ = validate_nested({"a": 1, "b": 2}, '{"b": 2, "a": 1}')
    assert ok
    ok, _ = validate_nested({"l": [1, 2]}, '{"l": [2, 1]}')
    assert not ok


def test_code_good():
    ok, why = validate_code("def add(a, b):\n    return a + b",
                            "assert add(2, 3) == 5\nassert add(-1, 1) == 0")
    assert ok, why


def test_code_broken_solution_fails():
    ok, why = validate_code("def add(a, b):\n    return a - b",
                            "assert add(2, 3) == 5")
    assert not ok and "exec" in why


def test_code_infinite_loop_times_out():
    ok, why = validate_code("def f():\n    pass", "while True:\n    pass", timeout=3)
    assert not ok


def test_code_no_network():
    ok, why = validate_code(
        "def f():\n    pass",
        "import urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('http://1.1.1.1', timeout=2)\n"
        "    raise SystemExit(1)\n"
        "except SystemExit:\n"
        "    raise\n"
        "except Exception:\n"
        "    pass\n", timeout=8)
    assert ok, f"network was reachable from sandbox: {why}"
