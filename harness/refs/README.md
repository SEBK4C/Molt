# harness/refs — golden references (AGENT-FORBIDDEN)

The in-session research agent must NEVER read this directory (program.md ownership rule).
Only `harness/score.py` consumes these files. Everything here is covered by the SHA-256
manifest; changing any byte after the freeze auto-fails all subsequent experiments until a
deliberate, human-sanctioned re-freeze (`python harness/manifest.py --write`).

Layout (all keyed by case id, matching `prompts/<suite>.json`):

- `nested.json`   — {id: {name, arguments}}. SPEC-DERIVED (the prompt demands exact args, the
                    ref is those args). Complete without any endpoint.
- `tau.json`      — {id: {final_state}}. Hand-authored ground truth, generated with the same
                    tau_env the referee uses (builder applies the intended tool sequence).
- `evalplus.json` — {id: {test_code, timeout}}. test_code embeds inputs + expected outputs
                    computed from HumanEval+ canonical solutions; candidate code replaces the
                    `### __CANDIDATE_CODE__ ###` marker and is exec'd sandboxed.
- `bfcl.json`     — {id: {calls|expect, order}}. From upstream BFCL ground truth
                    (possible_answer), mapped to the __any_of__/__ABSENT_OK__ ref grammar.

FP8-endpoint upgrade path (HUMAN gate HG1): scripts/hf_endpoint_goldens.py writes
`<suite>.fp8.json` files NEXT TO these (never overwriting). Promotion = human decision:
replace the derived file with the fp8 one, then re-freeze the manifest and re-run Phase 0
(ε depends on the refs). The secret 100-sample split lives OUTSIDE this repo entirely.
