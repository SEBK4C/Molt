#!/usr/bin/env python3
"""molt τ-lite environment — deterministic multi-turn tool-use episodes (tau-bench style,
user-sim replaced by canned scripts; no LLM judges anywhere).

Design invariant: tools are PERMISSIVE (they execute anything structurally valid); the POLICY
lives in the episode's system prompt. A model that violates policy mutates state and fails the
terminal-state match; a model that follows it leaves the right final state. State is pure JSON.

Episode case schema (prompts/tau.json):
  {id, domain: "retail"|"airline", system, tools: [openai tool schemas],
   initial_state: {...}, user_script: [utterance, ...], max_steps: int, max_tokens: int}

run_episode(chat_fn, case, extract_fn) -> final state dict
  chat_fn(messages, tools, max_tokens) -> openai chat response dict
  extract_fn(message) -> [{"name":.., "arguments": {..}}]  (falls back to a local extractor)
"""
import copy
import json
import re


# --- tool implementations ----------------------------------------------------
# Every tool: fn(state, args) -> result dict. Mutates state in place only on success.
# Errors return {"error": ...} and leave state untouched. No free-text ever enters state
# except argument values the scripted user dictates verbatim (that copying IS the test).

def _req(args, *names):
    missing = [n for n in names if n not in args]
    if missing:
        return {"error": f"missing argument: {', '.join(missing)}"}
    return None


# retail ----------------------------------------------------------------------
def r_get_order(state, args):
    e = _req(args, "order_id")
    if e:
        return e
    o = state["orders"].get(args["order_id"])
    return o if o else {"error": "order not found"}


def r_cancel_order(state, args):
    e = _req(args, "order_id")
    if e:
        return e
    o = state["orders"].get(args["order_id"])
    if not o:
        return {"error": "order not found"}
    if o["status"] == "cancelled":
        return {"error": "already cancelled"}
    o["status"] = "cancelled"
    o["refund"] = o["total"]
    return {"ok": True, "status": "cancelled", "refund": o["refund"]}


def r_update_shipping_address(state, args):
    e = _req(args, "order_id", "address")
    if e:
        return e
    o = state["orders"].get(args["order_id"])
    if not o:
        return {"error": "order not found"}
    o["address"] = args["address"]
    return {"ok": True, "address": o["address"]}


def r_refund_order(state, args):
    e = _req(args, "order_id", "amount")
    if e:
        return e
    o = state["orders"].get(args["order_id"])
    if not o:
        return {"error": "order not found"}
    amt = args["amount"]
    if not isinstance(amt, (int, float)) or isinstance(amt, bool) or amt <= 0:
        return {"error": "amount must be a positive number"}
    if o["refund"] + amt > o["total"]:
        return {"error": "refund exceeds order total"}
    o["refund"] = round(o["refund"] + amt, 2)
    return {"ok": True, "refund": o["refund"]}


def r_exchange_item(state, args):
    e = _req(args, "order_id", "old_sku", "new_sku")
    if e:
        return e
    o = state["orders"].get(args["order_id"])
    if not o:
        return {"error": "order not found"}
    for it in o["items"]:
        if it["sku"] == args["old_sku"]:
            it["sku"] = args["new_sku"]
            return {"ok": True, "items": o["items"]}
    return {"error": "sku not in order"}


def r_get_user(state, args):
    e = _req(args, "user_id")
    if e:
        return e
    u = state["users"].get(args["user_id"])
    return u if u else {"error": "user not found"}


def r_escalate_to_human(state, args):
    state["escalated"] = True  # bool only — free text must never enter state
    return {"ok": True, "escalated": True}


# airline -----------------------------------------------------------------------
def a_get_booking(state, args):
    e = _req(args, "booking_id")
    if e:
        return e
    b = state["bookings"].get(args["booking_id"])
    return b if b else {"error": "booking not found"}


def a_list_flights(state, args):
    return {"flights": state["flights"]}


def a_change_flight(state, args):
    e = _req(args, "booking_id", "new_flight")
    if e:
        return e
    b = state["bookings"].get(args["booking_id"])
    if not b:
        return {"error": "booking not found"}
    nf = state["flights"].get(args["new_flight"])
    if not nf:
        return {"error": "flight not found"}
    if nf["seats_available"] < 1:
        return {"error": "no seats available"}
    old = b["flight"]
    if old == args["new_flight"]:
        return {"error": "already on that flight"}
    if old in state["flights"]:
        state["flights"][old]["seats_available"] += 1
    nf["seats_available"] -= 1
    b["flight"] = args["new_flight"]
    change_fee = 0 if b.get("fare_class") == "flex" else 75
    b["charges"] = round(b.get("charges", 0) + change_fee, 2)
    return {"ok": True, "flight": b["flight"], "change_fee": change_fee,
            "charges": b["charges"]}


def a_cancel_booking(state, args):
    e = _req(args, "booking_id", "refund_amount")
    if e:
        return e
    b = state["bookings"].get(args["booking_id"])
    if not b:
        return {"error": "booking not found"}
    if b["status"] == "cancelled":
        return {"error": "already cancelled"}
    amt = args["refund_amount"]
    if not isinstance(amt, (int, float)) or isinstance(amt, bool) or amt < 0:
        return {"error": "refund_amount must be a non-negative number"}
    if amt > b["price"]:
        return {"error": "refund exceeds ticket price"}
    fl = state["flights"].get(b["flight"])
    if fl:
        fl["seats_available"] += 1
    b["status"] = "cancelled"
    b["refund"] = amt
    return {"ok": True, "status": "cancelled", "refund": amt}


def a_add_baggage(state, args):
    e = _req(args, "booking_id", "count")
    if e:
        return e
    b = state["bookings"].get(args["booking_id"])
    if not b:
        return {"error": "booking not found"}
    c = args["count"]
    if not isinstance(c, int) or isinstance(c, bool) or c < 1:
        return {"error": "count must be a positive integer"}
    fee_per_bag = 30 if b.get("fare_class") == "flex" else 40
    b["baggage"] = b.get("baggage", 0) + c
    b["charges"] = round(b.get("charges", 0) + fee_per_bag * c, 2)
    return {"ok": True, "baggage": b["baggage"], "fee_charged": fee_per_bag * c,
            "charges": b["charges"]}


REGISTRY = {
    "retail": {
        "get_order": r_get_order,
        "cancel_order": r_cancel_order,
        "update_shipping_address": r_update_shipping_address,
        "refund_order": r_refund_order,
        "exchange_item": r_exchange_item,
        "get_user": r_get_user,
        "escalate_to_human": r_escalate_to_human,
    },
    "airline": {
        "get_booking": a_get_booking,
        "list_flights": a_list_flights,
        "change_flight": a_change_flight,
        "cancel_booking": a_cancel_booking,
        "add_baggage": a_add_baggage,
        "escalate_to_human": r_escalate_to_human,
    },
}


def execute(state, domain, name, args):
    """Run one tool call against state. Unknown tool / malformed args -> error, state unchanged."""
    fn = REGISTRY.get(domain, {}).get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    if not isinstance(args, dict):
        return {"error": "arguments must be an object"}
    return fn(state, args)


# --- episode driver -----------------------------------------------------------
def _local_extract(msg):
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
                calls.append({"name": None, "arguments": {}, "id": None})
    return calls


def run_episode(chat_fn, case, extract_fn=None):
    """Drive one canned-script episode; return the final environment state dict."""
    extract = extract_fn or _local_extract
    state = copy.deepcopy(case["initial_state"])
    script = list(case["user_script"])
    domain = case["domain"]
    max_steps = case.get("max_steps", 24)
    max_tokens = case.get("max_tokens", 1024)

    messages = [{"role": "system", "content": case["system"]},
                {"role": "user", "content": script[0]}]
    idx = 0

    for _ in range(max_steps):
        out = chat_fn(messages, case.get("tools"), max_tokens)
        msg = out["choices"][0]["message"]
        calls = extract(msg)

        clean = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            clean["tool_calls"] = msg["tool_calls"]
        messages.append(clean)

        if calls:
            for c in calls:
                result = execute(state, domain, c.get("name"), c.get("arguments"))
                tmsg = {"role": "tool", "content": json.dumps(result, ensure_ascii=False)}
                if c.get("id"):
                    tmsg["tool_call_id"] = c["id"]
                if c.get("name"):
                    tmsg["name"] = c["name"]
                messages.append(tmsg)
            continue  # same user turn; model reacts to tool results

        idx += 1
        if idx >= len(script):
            break  # script exhausted on a plain-text reply -> episode over
        messages.append({"role": "user", "content": script[idx]})

    return state
