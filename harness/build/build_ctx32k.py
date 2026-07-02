#!/usr/bin/env python3
"""Generate harness/prompts/ctx32k.txt — a deterministic ≥32K-token document for the G4/G5
throughput probe (content is throughput filler; only length matters). Seeded PRNG, stable output.

Token estimate: ~3.9 chars/token for this prose mix on qwen-family BPE; we target ~155 KB
≈ 36-40K tokens for margin. Verify exact count once a GGUF exists:
  vendor/llama.cpp/build/bin/llama-tokenize -m <any qwen3.5 gguf> -f harness/prompts/ctx32k.txt --show-count
"""
import os
import random

H = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(H, "prompts", "ctx32k.txt")

NOUNS = """pipeline cache scheduler tensor kernel register buffer socket cluster daemon shard
replica quorum ledger index vector matrix gradient checkpoint token parser compiler linker heap
stack queue channel mutex thread fiber page block sector inode packet frame router switch bridge
gateway proxy balancer container image layer volume snapshot journal manifest recipe corpus probe
gate referee harness runner experiment hypothesis verdict decision lesson budget tier session
branch commit reset ratchet epsilon threshold ceiling floor window batch chunk stream prefill
decode expert router embedding projection attention head dimension rotation scale offset bias""".split()

VERBS = """streams schedules quantizes serializes amortizes saturates evicts prefetches batches
routes shards replicates journals commits resets verifies scores gates measures probes renders
maps reduces caches pins offloads uploads mmaps pages swaps compresses decompresses encodes
decodes samples drafts verifies accepts rejects promotes demotes freezes thaws rebalances""".split()

ADJS = """monotonic idempotent deterministic append-only disk-bound memory-bound compute-bound
lock-free wait-free cache-friendly bandwidth-limited latency-sensitive fault-tolerant eventually
consistent write-heavy read-mostly cold warm hot resident evicted pinned quantized calibrated
stratified frozen provisional behavioral structural canonical nested escaped fragile aggressive""".split()


def sentence(rng):
    n1, n2, n3 = rng.choice(NOUNS), rng.choice(NOUNS), rng.choice(NOUNS)
    v1, v2 = rng.choice(VERBS), rng.choice(VERBS)
    a1, a2 = rng.choice(ADJS), rng.choice(ADJS)
    forms = [
        f"The {a1} {n1} {v1} each {n2} before the {n3} {v2} again.",
        f"When the {n1} is {a1}, the {n2} {v1} whatever the {a2} {n3} produced.",
        f"A {a1} {n1} rarely {v1} its {n2}; instead the {n3} {v2} under pressure.",
        f"Every {n1} {v1} the {n2} at a rate the {a2} {n3} can sustain.",
        f"Measurements show the {n1} {v1} while the {n2} stays {a1} and the {n3} {v2}.",
    ]
    return rng.choice(forms)


def main():
    rng = random.Random(20260702)
    parts = ["THROUGHPUT PROBE DOCUMENT (deterministic filler, seed 20260702)\n"]
    section = 0
    while sum(len(p) for p in parts) < 155_000:
        section += 1
        parts.append(f"\n\nSection {section}. {sentence(rng)}\n")
        for _ in range(rng.randint(10, 16)):
            parts.append(sentence(rng) + " ")
    doc = "".join(parts)
    with open(OUT, "w") as f:
        f.write(doc)
    print(f"[build_ctx32k] wrote {OUT}: {len(doc)} chars, ~{len(doc)//4}-{len(doc)//3} tokens (est)")


if __name__ == "__main__":
    main()
