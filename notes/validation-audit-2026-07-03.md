# Validation audit — why S≈0.92 is real but means less than it looks (2026-07-03)

Owner asked: "this feels too easy — is the protocol or data wrong?" Adversarial self-audit.

## What protects the scores (solid)
- Ref provenance is diversified: bfcl = upstream Berkeley ground truth; evalplus = executing
  canonical solutions; nested = specification-derived; tau = env-derived terminal states.
- Checkers are mechanical (AST/exec/deep-equal), 54 fixture tests incl. known-fail/malformed.
- Round-trip validation: synthesized-perfect answers pass (bfcl 300/300), corrupted fail (210/210).
- SHA-256 manifest (it fired on the maintainer mid-calibration — the mechanism works).
- Replication: bfcl 270–272/300 over four passes; tau 40/40 ×3; nested 71–72.

## Honest inflation sources / blind spots (the "too easy" is partly right)
1. **tau ceiling effect**: episodes are deterministic + unambiguous BY DESIGN (canned scripts,
   explicit policies). Real tau-bench is ambiguous/adversarial (frontier ≈60–80%). Ours is a
   degradation SMOKE ALARM with no discrimination at the top (Q8 and 2-bit both ≈100%).
   Hardening (ambiguity, distractor orders, conflicting constraints, longer horizons) is a
   next-refresh item — refs must stay deterministic.
2. **Grammar assistance**: llama-server grammar-constrains tool calls from schemas → malformed
   JSON is IMPOSSIBLE, masking one whole class of 2-bit degradation. Deployment-realistic but
   flattering. nested semantics (72%) still crack → canary functional.
3. **evalplus deviations from official**: plus_input capped at 30/problem + import safety
   header → a few points above official-protocol numbers. Fine for RELATIVE ratchet use only.
4. **ε measures infra noise, not sampling noise** (temp 0): batched fp-order variance only.
   Cross-config comparisons carry more variance than same-config replication → consider an
   ε floor ≈0.01 (spec/owner decision) and keep program.md's confirm-with-full-S discipline.
5. **No unquantized anchor (biggest gap)**: S grades vs task ground truth, not vs FP8 Ornith.
   Degradation = S_fp8 − S_quant is UNMEASURED until HG1. Do not narrate S as "quality loss".
6. **No per-case result logging**: only counts. Can't audit WHICH evalplus/bfcl cases fail or
   whether failures are stable across runs. Add results.jsonl per run at next harness window.
7. **Quality is untested at long context**: suites are short-ctx; 38K is throughput-probed
   only. Long-ctx behavioral checks are absent (future suite work).

## Falsification queue (post-run-3; no harness changes needed for 1–2)
- [ ] KLD-vs-Q8 diagnostic on ornith-molt-000 (llama-perplexity --kl-divergence vs
      models/kld-base.out) — independent distance-from-master number. ~30–60 min GPU-assisted.
- [ ] Negative control: score the 9B GGUF on eval-lite + tau. A weak model MUST score much
      worse; if tau stays ~100%, tau lacks discrimination (expected) → harden next refresh.
- [ ] HG1 FP8 goldens (owner, ~$100): the real degradation anchor + secret-split material.

Conclusion: protocol not "wrong"; scores are trustworthy for the ratchet's RELATIVE purpose.
Absolute claims ("only lost X% to quantization") are NOT yet supported — that requires HG1.
tau needs hardening to be more than a smoke alarm.
