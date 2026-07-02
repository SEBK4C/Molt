"""Fixtures for the tau episode engine + terminal-state checker."""
import copy
import json

import tau_env
from score import check

RETAIL_STATE = {
    "escalated": False,
    "users": {"u1": {"name": "Ada", "membership": "gold"}},
    "orders": {
        "W100": {"user": "u1", "status": "processing", "total": 89.5, "refund": 0,
                 "address": "1 Elm St, Springfield",
                 "items": [{"sku": "TEA-01", "qty": 1, "price": 89.5}]},
        "W200": {"user": "u1", "status": "shipped", "total": 40.0, "refund": 0,
                 "address": "1 Elm St, Springfield",
                 "items": [{"sku": "MUG-07", "qty": 2, "price": 20.0}]},
    },
}

AIRLINE_STATE = {
    "escalated": False,
    "flights": {"AA10": {"seats_available": 3, "price": 250.0},
                "AA20": {"seats_available": 1, "price": 250.0}},
    "bookings": {"B1": {"user": "u1", "flight": "AA10", "status": "confirmed",
                        "fare_class": "economy", "price": 250.0, "refund": 0,
                        "baggage": 0, "charges": 0}},
}


def scripted_chat(responses):
    """chat_fn returning canned assistant messages in order; repeats last when exhausted."""
    it = list(responses)

    def fn(messages, tools, max_tokens):
        msg = it.pop(0) if it else {"role": "assistant", "content": "done"}
        return {"choices": [{"message": msg}]}
    return fn


def tc(name, args, cid="x1"):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": cid, "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}


def case(domain, state, script=("hi, please handle my request", "yes, go ahead", "thanks, bye"),
         max_steps=12):
    return {"id": "t", "domain": domain, "system": "You are a support agent. Follow policy.",
            "tools": [], "initial_state": state, "user_script": list(script),
            "max_steps": max_steps}


def test_pass_cancel_flow_reaches_ref_state():
    chat = scripted_chat([
        tc("get_order", {"order_id": "W100"}),
        tc("cancel_order", {"order_id": "W100"}),
        {"role": "assistant", "content": "Cancelled with a full refund."},
    ])
    final = tau_env.run_episode(chat, case("retail", RETAIL_STATE))
    ref = copy.deepcopy(RETAIL_STATE)
    ref["orders"]["W100"]["status"] = "cancelled"
    ref["orders"]["W100"]["refund"] = 89.5
    assert check("tau", final, {"final_state": ref}) is True


def test_fail_wrong_order_cancelled():
    chat = scripted_chat([
        tc("cancel_order", {"order_id": "W200"}),
        {"role": "assistant", "content": "Done."},
    ])
    final = tau_env.run_episode(chat, case("retail", RETAIL_STATE))
    ref = copy.deepcopy(RETAIL_STATE)
    ref["orders"]["W100"]["status"] = "cancelled"
    ref["orders"]["W100"]["refund"] = 89.5
    assert check("tau", final, {"final_state": ref}) is False


def test_pass_policy_refusal_leaves_state_untouched():
    # policy says shipped orders cannot be cancelled; correct model doesn't mutate
    chat = scripted_chat([
        {"role": "assistant", "content": "W200 already shipped; per policy I cannot cancel it."},
        {"role": "assistant", "content": "Anything else?"},
        {"role": "assistant", "content": "bye"},
    ])
    final = tau_env.run_episode(chat, case("retail", RETAIL_STATE))
    assert check("tau", final, {"final_state": RETAIL_STATE}) is True


def test_fail_policy_violation_mutates_state():
    # permissive env executes the forbidden cancel -> state differs from ref(initial) -> fail
    chat = scripted_chat([
        tc("cancel_order", {"order_id": "W200"}),
        {"role": "assistant", "content": "Cancelled!"},
    ])
    final = tau_env.run_episode(chat, case("retail", RETAIL_STATE))
    assert check("tau", final, {"final_state": RETAIL_STATE}) is False


def test_malformed_toolcall_args_leave_state_unchanged():
    bad = {"role": "assistant", "content": None,
           "tool_calls": [{"id": "x", "type": "function",
                           "function": {"name": "cancel_order", "arguments": '{"order_id":'}}]}
    chat = scripted_chat([bad, {"role": "assistant", "content": "hm"},
                          {"role": "assistant", "content": "bye"},
                          {"role": "assistant", "content": "bye"}])
    final = tau_env.run_episode(chat, case("retail", RETAIL_STATE))
    assert final == RETAIL_STATE  # error result, no mutation


def test_unknown_tool_is_an_error_not_a_crash():
    chat = scripted_chat([tc("teleport_order", {"order_id": "W100"}),
                          {"role": "assistant", "content": "oops"},
                          {"role": "assistant", "content": "bye"},
                          {"role": "assistant", "content": "bye"}])
    final = tau_env.run_episode(chat, case("retail", RETAIL_STATE))
    assert final == RETAIL_STATE


def test_max_steps_terminates_tool_loop():
    chat = scripted_chat([tc("get_order", {"order_id": "W100"})] * 50)
    final = tau_env.run_episode(chat, case("retail", RETAIL_STATE, max_steps=6))
    assert final == RETAIL_STATE  # read-only loop, cut off, state intact


def test_script_advances_on_plain_text_turns():
    # model asks a question (text) -> gets scripted turn 2 -> then acts
    chat = scripted_chat([
        {"role": "assistant", "content": "Can you confirm the cancellation of W100?"},
        tc("cancel_order", {"order_id": "W100"}),
        {"role": "assistant", "content": "Done."},
    ])
    final = tau_env.run_episode(chat, case("retail", RETAIL_STATE))
    assert final["orders"]["W100"]["status"] == "cancelled"


def test_airline_arithmetic_change_fee_and_seats():
    chat = scripted_chat([
        tc("change_flight", {"booking_id": "B1", "new_flight": "AA20"}),
        {"role": "assistant", "content": "Moved you to AA20; $75 change fee applied."},
        {"role": "assistant", "content": "bye"},
    ])
    final = tau_env.run_episode(chat, case("airline", AIRLINE_STATE))
    assert final["bookings"]["B1"]["flight"] == "AA20"
    assert final["bookings"]["B1"]["charges"] == 75
    assert final["flights"]["AA20"]["seats_available"] == 0
    assert final["flights"]["AA10"]["seats_available"] == 4


def test_refund_cap_enforced():
    s = copy.deepcopy(RETAIL_STATE)
    r = tau_env.execute(s, "retail", "refund_order", {"order_id": "W100", "amount": 500})
    assert "error" in r and s == RETAIL_STATE
    r2 = tau_env.execute(s, "retail", "refund_order", {"order_id": "W100", "amount": 20.5})
    assert r2["ok"] and s["orders"]["W100"]["refund"] == 20.5
