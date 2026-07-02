"""Fixtures for the BFCL AST-match checker: known-pass, known-fail, malformed."""
import json

from score import check, deep_eq, match_args, ABSENT


def _msg_toolcalls(*calls):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": f"c{i}", "type": "function",
                            "function": {"name": n, "arguments": json.dumps(a)}}
                           for i, (n, a) in enumerate(calls)]}


REF_WEATHER = {"calls": [{"name": "get_weather",
                          "arguments": {"city": "Paris", "unit": "celsius"}}]}


def test_pass_exact_single_call():
    msg = _msg_toolcalls(("get_weather", {"city": "Paris", "unit": "celsius"}))
    assert check("bfcl", msg, REF_WEATHER) is True


def test_fail_wrong_argument_value():
    msg = _msg_toolcalls(("get_weather", {"city": "London", "unit": "celsius"}))
    assert check("bfcl", msg, REF_WEATHER) is False


def test_fail_extra_hallucinated_argument():
    msg = _msg_toolcalls(("get_weather", {"city": "Paris", "unit": "celsius", "lang": "fr"}))
    assert check("bfcl", msg, REF_WEATHER) is False


def test_fail_malformed_arguments_json():
    msg = {"role": "assistant", "content": None,
           "tool_calls": [{"type": "function",
                           "function": {"name": "get_weather",
                                        "arguments": '{"city": "Paris", "unit":'}}]}
    assert check("bfcl", msg, REF_WEATHER) is False


def test_pass_parallel_calls_any_order():
    ref = {"calls": [{"name": "f", "arguments": {"x": 1}},
                     {"name": "g", "arguments": {"y": 2}}], "order": "any"}
    msg = _msg_toolcalls(("g", {"y": 2}), ("f", {"x": 1}))
    assert check("bfcl", msg, ref) is True


def test_fail_strict_order_violated():
    ref = {"calls": [{"name": "f", "arguments": {"x": 1}},
                     {"name": "g", "arguments": {"y": 2}}], "order": "strict"}
    msg = _msg_toolcalls(("g", {"y": 2}), ("f", {"x": 1}))
    assert check("bfcl", msg, ref) is False


def test_fail_missing_second_call():
    ref = {"calls": [{"name": "f", "arguments": {"x": 1}},
                     {"name": "g", "arguments": {"y": 2}}]}
    msg = _msg_toolcalls(("f", {"x": 1}))
    assert check("bfcl", msg, ref) is False


def test_pass_irrelevance_no_call():
    ref = {"expect": "no_call"}
    msg = {"role": "assistant", "content": "I can't help with that using my tools."}
    assert check("bfcl", msg, ref) is True


def test_fail_irrelevance_called_anyway():
    ref = {"expect": "no_call"}
    msg = _msg_toolcalls(("get_weather", {"city": "Paris"}))
    assert check("bfcl", msg, ref) is False


def test_pass_any_of_alternate():
    ref = {"calls": [{"name": "f",
                      "arguments": {"unit": {"__any_of__": ["c", "celsius"]}}}]}
    msg = _msg_toolcalls(("f", {"unit": "celsius"}))
    assert check("bfcl", msg, ref) is True


def test_pass_omittable_argument_absent():
    ref = {"calls": [{"name": "f",
                      "arguments": {"q": "x",
                                    "limit": {"__any_of__": [10, ABSENT]}}}]}
    msg = _msg_toolcalls(("f", {"q": "x"}))
    assert check("bfcl", msg, ref) is True


def test_fail_omitted_required_argument():
    ref = {"calls": [{"name": "f", "arguments": {"q": "x", "limit": 10}}]}
    msg = _msg_toolcalls(("f", {"q": "x"}))
    assert check("bfcl", msg, ref) is False


def test_pass_xml_toolcall_in_content():
    payload = json.dumps({"name": "get_weather",
                          "arguments": {"city": "Paris", "unit": "celsius"}})
    msg = {"role": "assistant",
           "content": f"<tool_call>\n{payload}\n</tool_call>"}
    assert check("bfcl", msg, REF_WEATHER) is True


def test_matcher_primitives():
    assert deep_eq(1, 1.0) is True          # ints and floats compare numerically
    assert deep_eq(True, 1) is False        # bools never equal ints
    assert deep_eq("1", 1) is False         # strings never coerce
    assert match_args({"a": 2}, {"a": {"__any_of__": [1, 2]}}) is True
    assert match_args({"a": 3}, {"a": {"__any_of__": [1, 2]}}) is False
