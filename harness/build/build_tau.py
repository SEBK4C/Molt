#!/usr/bin/env python3
"""Generate the τ-lite suite: harness/prompts/tau.json (40 canned-script episodes) +
harness/refs/tau.json (terminal states).

Ground-truth strategy: each case declares its INTENDED tool sequence; the builder applies it
through the very same tau_env.execute the referee uses, so ref and engine can never drift.
Cases where the correct behavior is "refuse / don't act" have an empty intended sequence
(ref terminal state == initial state; the permissive env means a policy-violating model
mutates state and fails). Deterministic, no RNG dependence on run order.
"""
import copy
import json
import os
import sys

H = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, H)
import tau_env  # noqa: E402

RETAIL_SYSTEM = """You are the customer support agent for AcmeShop. Binding policy:
1. Cancellation (full refund) is allowed ONLY while the order status is 'placed' or 'processing'. Never cancel shipped or delivered orders; politely refuse instead.
2. The shipping address may be changed ONLY while status is 'placed' or 'processing'.
3. Damaged-item complaints: if the damaged item's price times quantity is UNDER $50, refund exactly that amount via refund_order WITHOUT requiring a return. If it is $50 or more, do NOT refund; call escalate_to_human instead.
4. Exchanges (exchange_item) are allowed only between items of the same price, only while status is 'placed' or 'processing'.
5. Look up the order before acting. Never invent details.
Use the tools to act. When the task is complete (or correctly refused), reply with a short plain-text summary and no tool call."""

AIRLINE_SYSTEM = """You are the reservations agent for AcmeAir. Binding policy:
1. Flight changes (change_flight): allowed for 'flex' and 'economy' fares if seats are available. The system charges the change fee automatically. NOT allowed for 'basic' fare — politely refuse, do not call change_flight.
2. Cancellations (cancel_booking): refund_amount depends on fare class — 'flex': full ticket price; 'economy': 50% of ticket price; 'basic': 0. Compute it exactly.
3. Checked baggage (add_baggage): the system charges automatically per bag.
4. Look up the booking before acting. Never invent details.
Use the tools to act. When the task is complete (or correctly refused), reply with a short plain-text summary and no tool call."""

RETAIL_TOOLS = [
    {"type": "function", "function": {"name": "get_order", "description": "Look up an order by id.",
     "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}},
    {"type": "function", "function": {"name": "cancel_order", "description": "Cancel an order and refund its full total.",
     "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}},
    {"type": "function", "function": {"name": "update_shipping_address", "description": "Set a new shipping address on an order.",
     "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}, "address": {"type": "string"}}, "required": ["order_id", "address"]}}},
    {"type": "function", "function": {"name": "refund_order", "description": "Refund a specific amount on an order (partial refunds allowed).",
     "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}, "amount": {"type": "number"}}, "required": ["order_id", "amount"]}}},
    {"type": "function", "function": {"name": "exchange_item", "description": "Swap one SKU in an order for another.",
     "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}, "old_sku": {"type": "string"}, "new_sku": {"type": "string"}}, "required": ["order_id", "old_sku", "new_sku"]}}},
    {"type": "function", "function": {"name": "get_user", "description": "Look up a user profile.",
     "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}}},
    {"type": "function", "function": {"name": "escalate_to_human", "description": "Escalate the case to a human agent.",
     "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": []}}},
]

AIRLINE_TOOLS = [
    {"type": "function", "function": {"name": "get_booking", "description": "Look up a booking by id.",
     "parameters": {"type": "object", "properties": {"booking_id": {"type": "string"}}, "required": ["booking_id"]}}},
    {"type": "function", "function": {"name": "list_flights", "description": "List flights with seat availability.",
     "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "change_flight", "description": "Move a booking to a different flight (change fee auto-applied by fare class).",
     "parameters": {"type": "object", "properties": {"booking_id": {"type": "string"}, "new_flight": {"type": "string"}}, "required": ["booking_id", "new_flight"]}}},
    {"type": "function", "function": {"name": "cancel_booking", "description": "Cancel a booking, refunding refund_amount (must follow fare policy).",
     "parameters": {"type": "object", "properties": {"booking_id": {"type": "string"}, "refund_amount": {"type": "number"}}, "required": ["booking_id", "refund_amount"]}}},
    {"type": "function", "function": {"name": "add_baggage", "description": "Add checked bags to a booking (fee auto-applied by fare class).",
     "parameters": {"type": "object", "properties": {"booking_id": {"type": "string"}, "count": {"type": "integer"}}, "required": ["booking_id", "count"]}}},
    {"type": "function", "function": {"name": "escalate_to_human", "description": "Escalate the case to a human agent.",
     "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": []}}},
]


def retail_state(oid, status, sku, price, qty, addr="12 Birch Lane, Portland OR", user="u7"):
    total = round(price * qty, 2)
    return {"escalated": False,
            "users": {user: {"name": "Sam Rivera", "membership": "standard"}},
            "orders": {oid: {"user": user, "status": status, "total": total, "refund": 0,
                             "address": addr,
                             "items": [{"sku": sku, "qty": qty, "price": price}]}}}


def airline_state(bid, flight, fare, price, seats_map):
    return {"escalated": False,
            "flights": {f: {"seats_available": s, "price": price} for f, s in seats_map.items()},
            "bookings": {bid: {"user": "u7", "flight": flight, "status": "confirmed",
                               "fare_class": fare, "price": price, "refund": 0,
                               "baggage": 0, "charges": 0}}}


CASES = []


def add(cid, domain, state, script, intended, note):
    """intended: [(tool, args), ...] applied via tau_env to derive the ref terminal state."""
    ref = copy.deepcopy(state)
    for name, args in intended:
        r = tau_env.execute(ref, domain, name, args)
        assert "error" not in r, f"{cid}: intended op failed: {name} {args} -> {r}"
    CASES.append({
        "case": {"id": cid, "domain": domain,
                 "system": RETAIL_SYSTEM if domain == "retail" else AIRLINE_SYSTEM,
                 "tools": RETAIL_TOOLS if domain == "retail" else AIRLINE_TOOLS,
                 "initial_state": state, "user_script": script,
                 "max_steps": 16, "max_tokens": 2048, "note": note},
        "ref": {"final_state": ref}})


# --- retail: cancellations (allowed) ---------------------------------------
for i, (oid, sku, price, qty, status) in enumerate([
        ("W481", "LAMP-3", 64.0, 1, "processing"), ("W482", "DESK-9", 149.99, 1, "placed"),
        ("W483", "CBL-2", 9.5, 3, "processing"), ("W484", "CHR-11", 210.0, 1, "placed"),
        ("W485", "RUG-5", 88.25, 2, "processing")]):
    st = retail_state(oid, status, sku, price, qty)
    add(f"tau_r_cxl_{i}", "retail", st,
        [f"Hi, I need to cancel my order {oid}, I ordered by mistake.",
         "Yes, please cancel it now.", "Thanks, that's everything."],
        [("cancel_order", {"order_id": oid})],
        "cancel allowed: status placed/processing")

# --- retail: cancellation must be refused (shipped) -------------------------
for i, (oid, sku, price, qty) in enumerate([
        ("W510", "TV-42", 399.0, 1), ("W511", "SPK-7", 59.0, 2),
        ("W512", "KBD-1", 45.0, 1), ("W513", "MON-27", 229.0, 1)]):
    st = retail_state(oid, "shipped", sku, price, qty)
    add(f"tau_r_cxlref_{i}", "retail", st,
        [f"Please cancel order {oid} right away.",
         "I really want it cancelled, are you sure you can't?", "Fine. Bye."],
        [],
        "cancel forbidden: shipped; correct terminal state == initial")

# --- retail: address change (allowed) ---------------------------------------
for i, (oid, addr) in enumerate([
        ("W520", "88 Cañón Road, Santa Fe NM 87501"),
        ("W521", "Flat 4B, 12 Königstraße, Stuttgart 70173"),
        ("W522", "1600 Harbor Blvd, Weehawken NJ 07086"),
        ("W523", "Unit 9, 345 O'Connell St, Dublin D01")]):
    st = retail_state(oid, "processing", "BOOK-1", 25.0, 1)
    add(f"tau_r_addr_{i}", "retail", st,
        [f"I moved — please change the shipping address on {oid} to: {addr}",
         "Yes that address is correct, exactly as written.", "Great, thanks!"],
        [("update_shipping_address", {"order_id": oid, "address": addr})],
        "address change allowed while processing; address must be copied verbatim")

# --- retail: damaged item -> partial refund (<$50) or escalate (>=$50) -------
for i, (oid, sku, price, qty, under50) in enumerate([
        ("W530", "GLS-6", 12.5, 2, True),    # 25.00 refund
        ("W531", "PLT-3", 8.0, 4, True),     # 32.00 refund
        ("W532", "VAS-2", 49.99, 1, True),   # 49.99 refund
        ("W533", "ART-9", 30.0, 2, False),   # 60.00 -> escalate
        ("W534", "LMP-8", 75.5, 1, False)]): # 75.50 -> escalate
    st = retail_state(oid, "delivered", sku, price, qty)
    amount = round(price * qty, 2)
    if under50:
        intended = [("refund_order", {"order_id": oid, "amount": amount})]
    else:
        intended = [("escalate_to_human", {})]
    add(f"tau_r_dmg_{i}", "retail", st,
        [f"My {sku} from order {oid} arrived damaged (all {qty} of them). I want this sorted.",
         "Yes, whatever your policy allows, please do it.", "Ok, thanks."],
        intended,
        f"damaged item: qty*price = {amount}; {'refund without return' if under50 else 'must escalate, no refund'}")

# --- retail: exchange (same price) -------------------------------------------
for i, (oid, old, new) in enumerate([
        ("W540", "MUG-BLU", "MUG-RED"), ("W541", "TEE-M", "TEE-L"),
        ("W542", "PEN-BLK", "PEN-BLU"), ("W543", "CAP-GRY", "CAP-NVY")]):
    st = retail_state(oid, "placed", old, 19.0, 1)
    add(f"tau_r_exch_{i}", "retail", st,
        [f"On order {oid}, can you swap the {old} for the {new}? Same product, different variant.",
         "Yes please, make the swap.", "Perfect, bye."],
        [("exchange_item", {"order_id": oid, "old_sku": old, "new_sku": new})],
        "same-price exchange while placed")

# --- airline: flight change ---------------------------------------------------
for i, (bid, fare, seats, ok) in enumerate([
        ("B810", "economy", 4, True), ("B811", "economy", 2, True),
        ("B812", "flex", 3, True), ("B813", "economy", 5, True),
        ("B814", "basic", 6, False)]):  # basic: must refuse
    st = airline_state(bid, "AA100", fare, 320.0, {"AA100": 1, "AA200": seats})
    intended = [("change_flight", {"booking_id": bid, "new_flight": "AA200"})] if ok else []
    add(f"tau_a_chg_{i}", "airline", st,
        [f"I need to move booking {bid} from flight AA100 to AA200 tomorrow.",
         "Yes, go ahead with the change." if ok else "I understand the fare rules, but please try anyway.",
         "That's all, thanks."],
        intended,
        f"fare {fare}: change {'allowed (fee auto)' if ok else 'FORBIDDEN - correct answer refuses'}")

# --- airline: cancellation refund arithmetic ----------------------------------
for i, (bid, fare, price) in enumerate([
        ("B820", "flex", 410.0), ("B821", "flex", 129.5),
        ("B822", "economy", 300.0), ("B823", "economy", 179.98),
        ("B824", "basic", 89.0)]):
    st = airline_state(bid, "AA300", fare, price, {"AA300": 0})
    refund = {"flex": price, "economy": round(price / 2, 2), "basic": 0}[fare]
    add(f"tau_a_cxl_{i}", "airline", st,
        [f"Cancel booking {bid} please. What do I get back?",
         "Understood, please proceed with the cancellation.", "Ok bye."],
        [("cancel_booking", {"booking_id": bid, "refund_amount": refund})],
        f"cancel {fare}: refund must be exactly {refund}")

# --- airline: baggage fees -----------------------------------------------------
for i, (bid, fare, count) in enumerate([
        ("B830", "economy", 2), ("B831", "flex", 1),
        ("B832", "economy", 3), ("B833", "flex", 2)]):
    st = airline_state(bid, "AA400", fare, 250.0, {"AA400": 2})
    add(f"tau_a_bag_{i}", "airline", st,
        [f"Add {count} checked bag{'s' if count > 1 else ''} to booking {bid}.",
         "Yes, charge it to the booking.", "Thanks."],
        [("add_baggage", {"booking_id": bid, "count": count})],
        f"baggage: {count} bags, fare {fare} (fee auto-applied)")

# --- airline: bundled change + bags -------------------------------------------
for i, (bid, fare, count) in enumerate([
        ("B840", "economy", 1), ("B841", "flex", 2),
        ("B842", "economy", 2), ("B843", "flex", 1)]):
    st = airline_state(bid, "AA500", fare, 275.0, {"AA500": 1, "AA600": 4})
    add(f"tau_a_multi_{i}", "airline", st,
        [f"Two things for booking {bid}: move me to flight AA600, and add {count} checked bag{'s' if count > 1 else ''}.",
         "Yes to both, please proceed.", "All good, thanks."],
        [("change_flight", {"booking_id": bid, "new_flight": "AA600"}),
         ("add_baggage", {"booking_id": bid, "count": count})],
        f"bundle: change + {count} bags, fare {fare}")


def main():
    assert len(CASES) == 40, f"expected 40 episodes, built {len(CASES)}"
    prompts = [c["case"] for c in CASES]
    refs = {c["case"]["id"]: c["ref"] for c in CASES}
    hp = os.path.join(H, "prompts", "tau.json")
    hr = os.path.join(H, "refs", "tau.json")
    with open(hp, "w") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=1)
    with open(hr, "w") as f:
        json.dump(refs, f, ensure_ascii=False, indent=1)
    doms = {}
    for c in prompts:
        doms[c["domain"]] = doms.get(c["domain"], 0) + 1
    print(f"[build_tau] {len(prompts)} episodes ({doms}) -> {hp}; refs -> {hr}")


if __name__ == "__main__":
    main()
