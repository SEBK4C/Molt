"""Fixtures for the nested-JSON canonical deep-equal checker."""
import json

from score import check

DEEP = {"a": {"b": {"c": {"d": {"e": {"f": [1, 2, {"g": "h"}]}}}}},
        "meta": {"π": 3.14159, "flags": [True, False, None]}}
REF = {"name": "submit_payload", "arguments": DEEP}


def msg_call(name, args_str):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": "n1", "type": "function",
                            "function": {"name": name, "arguments": args_str}}]}


def test_pass_exact_deep_structure():
    m = msg_call("submit_payload", json.dumps(DEEP, ensure_ascii=False))
    assert check("nested", m, REF) is True


def test_pass_unicode_escape_canonicalization():
    # π escaped form must equal the literal π key after canonical re-serialize
    m = msg_call("submit_payload", json.dumps(DEEP, ensure_ascii=True))
    assert check("nested", m, REF) is True


def test_fail_deep_leaf_mismatch():
    bad = json.loads(json.dumps(DEEP))
    bad["a"]["b"]["c"]["d"]["e"]["f"][2]["g"] = "H"
    assert check("nested", msg_call("submit_payload", json.dumps(bad)), REF) is False


def test_fail_missing_key():
    bad = json.loads(json.dumps(DEEP))
    del bad["meta"]
    assert check("nested", msg_call("submit_payload", json.dumps(bad)), REF) is False


def test_fail_extra_key():
    bad = json.loads(json.dumps(DEEP))
    bad["extra"] = 1
    assert check("nested", msg_call("submit_payload", json.dumps(bad)), REF) is False


def test_fail_wrong_tool_name():
    m = msg_call("submit_payloads", json.dumps(DEEP))
    assert check("nested", m, REF) is False


def test_fail_two_calls():
    m = msg_call("submit_payload", json.dumps(DEEP))
    m["tool_calls"].append(m["tool_calls"][0])
    assert check("nested", m, REF) is False


def test_numeric_int_float_equal_but_string_not():
    ref = {"name": "f", "arguments": {"x": 1}}
    assert check("nested", msg_call("f", '{"x": 1.0}'), ref) is True
    assert check("nested", msg_call("f", '{"x": "1"}'), ref) is False


def test_bool_never_equals_int():
    ref = {"name": "f", "arguments": {"x": 1}}
    assert check("nested", msg_call("f", '{"x": true}'), ref) is False


def test_escape_heavy_strings():
    args = {"s": 'line1\nline2\t"quoted"\\backslash/slash', "n": {"‰": " sep"}}
    ref = {"name": "f", "arguments": args}
    assert check("nested", msg_call("f", json.dumps(args, ensure_ascii=True)), ref) is True
    assert check("nested", msg_call("f", json.dumps(args, ensure_ascii=False)), ref) is True


def test_fail_malformed_arguments():
    assert check("nested", msg_call("submit_payload", '{"a": '), REF) is False
