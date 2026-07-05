# molt

**A 397B mixture-of-experts model at 2.41 bits/weight, served on two consumer GPUs — found by
an autonomous research ratchet, with every success and failure journaled.**

molt is a port of [Andrej Karpathy's **autoresearch**](https://github.com/karpathy/autoresearch)
contract to model compression: an agent-owned sandbox (quant recipe + serving config), a frozen
human-owned referee, one metric, fixed budgets, and a git ratchet that keeps a change only when
it beats the best score by more than the *measured* noise floor. The train step is replaced by
quantize/serve/eval against [llama.cpp](https://github.com/ggml-org/llama.cpp); the target is
[`deepreinforce-ai/Ornith-1.0-397B`](https://huggingface.co/deepreinforce-ai/Ornith-1.0-397B)
on one box: 2×RTX 4090, 90 GB DDR5, one Gen5 SSD.

**→ Full findings: [docs/RESEARCH_REPORT.md](docs/RESEARCH_REPORT.md)** ·
model: [`SEBK4C/Ornith-1.0-397B-Featherweight`](https://huggingface.co/SEBK4C/Ornith-1.0-397B-Featherweight) ·
harness + journal: [`SEBK4C/molt-ornith-eval`](https://huggingface.co/datasets/SEBK4C/molt-ornith-eval)

## The ratchet, in one image

![Two-panel ratchet chart. Top: full-suite S with the S_best reference stepping up at the sole
keep, inside a ±ε noise band. Bottom: eval-lite screening runs in their own ±ε_lite
band.](notes/progress.png)

Twelve scored runs across two autonomous sessions, split by instrument. **Top — the frozen full
suite:** three baseline replicas set the noise floor (ε = 2σ = 0.0053), three hypotheses were
falsified, and the sole keep rebases `S_best` to 0.9258 — a *throughput* keep (+4% decode,
−1 h/eval) with S held in-band (Δ +0.0010 < ε), per the journal. **Bottom — the eval-lite
screen** (Tier-A speed runs, separate noise floor ε_lite = 0.041): two provisional keeps that
became the final config, three discards. Six of eight hypotheses falsified — which is what an
honest search looks like.

## Conclusions

**Successes** (details: [report §1–2](docs/RESEARCH_REPORT.md#1-headline-results)):

- **119.5 GB / 2.41 BPW, S = 0.9258** on a frozen behavioral suite: function-calling 91%,
  multi-turn tool episodes 240/240, code 98%, nested-JSON fidelity 72% — the RL'd agentic core
  survives; damage concentrates in a thin token-precision tail (KLD median 0.00075, p99 0.34).
- **18.5 tok/s decode / 717 tok/s prefill @38K ctx** via measured placement (10 GPU expert
  layers with an explicit `--tensor-split`) and the micro-batch/streaming law (`-ub 8192`).
- The **protect-the-fragile-2.6% recipe** (router/attention/embeddings/shared-experts at Q8,
  routed experts at ~2 bits) independently reproduces
  [antirez/ds4](https://github.com/antirez/ds4)'s result on a second MoE architecture.
- A **tamper-proof referee** (SHA-256 manifest, mechanical checks only, replicated noise
  floors) that caught its own maintainer twice — and made every number below trustworthy.

**Falsified — don't pay for these again**
(details: [report §3](docs/RESEARCH_REPORT.md#3-what-did-not-work--documented-so-you-dont-pay-for-it)):

- **Speculative decoding inverts on CPU-resident MoE**: ngram −10%, same-family 9B drafter
  −34% decode. Batch-verifying k drafted tokens streams up to k× the expert weights — the
  amortization premise flips sign. This extends to EAGLE/Medusa-class draft heads on this
  hardware class (we cancelled a planned $1.2K training on this measurement).
- **Recipe search at 2.4 BPW is locally optimal**: last-layer down-proj promotion, imatrix-
  energy-guided promotion (energy ≠ behavioral value — layer 59 holds 53.7% of energy and
  promoting it does nothing), and gate/up promotion all landed within noise.
- **Embeddings must stay Q8**: Q6_K embeddings measurably damage verbatim token fidelity at
  248K vocab (−3–4 nested cases). A measured floor, not a superstition.
- **Thinking budgets below 1024 are a no-op**; unbounded thinking is a serving hazard.
- **Evaluation traps**: permissive tool schemas collapse llama-server's grammar to `{}` (an
  entire suite scored zero until fixed); saturated suites (a 9B *ties* the 397B on BFCL)
  must never be sold as capability numbers; cold-cache throughput lies in both directions.

**Next steps and costs** (details: [report §4](docs/RESEARCH_REPORT.md#4-next-steps-with-costs)):
$100 buys the true degradation anchor (S_fp8) + golden refs + trace corpus; imatrix v2 from
those traces legitimately reopens the recipe search; ~$1.5K LoRA recovery is the surviving
big-ticket quality play; ~$3K demonstrates transfer to a second model family.

## Repository map

`SPEC.md` design contract · `program.md` session rules (human-owned) · `harness/` frozen
referee + suites (SHA-256 manifested) · `runner/` tier runners, GPU lock, journal writer ·
`recipes/` + `serve/` the agent sandbox · `experiments.jsonl` the append-only journal ·
`notes/` measured-reality constants, validation audit, session logs · `docs/` research
report, statement, dataset card · `OFFSITE-AGENT.md` the cloud-lane agent brief.

## Reproduce

```bash
./prepare.sh                      # one-time: build pinned llama.cpp, env, download, corpora
./scripts/post_download_chain.sh  # Q8 master -> imatrix -> KLD base -> baseline quant
./scripts/phase0_epsilon.sh       # 3x replication -> epsilon -> FINAL manifest freeze
./scripts/session_preflight.sh    # all green? then: git checkout -b molt/<date>, read program.md
```

Scores verify against `experiments.jsonl` via `runner/score.sh` (exit 2 = tampered harness).

---

*Method: [karpathy/autoresearch](https://github.com/karpathy/autoresearch). Recipe lineage:
[antirez/ds4](https://github.com/antirez/ds4). Weights: DeepReinforce (MIT). Engine:
llama.cpp/GGML. Research loop: Claude, under human authorization — the journal contains the
mistakes too, on purpose. MIT license.*
