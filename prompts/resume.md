Resume molt from disk state. Budget ~4.5 h; a successor instance starts in 5 h. Chat history does
not exist — TODO.md, notes/, and the filesystem are your memory.

1. Reconcile TODO.md against reality before doing anything: download progress = actual bytes in
   /mnt/proxmox/llm-serve/models/ornith-397b/ vs expected; in-progress items = is the PID alive,
   is the log advancing; GPU state = nvidia-smi; disk = df on /mnt/proxmox AND the root fs.
   Trust disk over the checklist; correct TODO.md where they disagree.

2. Adopt, don't restart: a live detached job (download, convert, imatrix, quantize) stays as-is —
   note its ETA and work around it. A dead job with a partial *.part artifact resumes if the tool
   supports it (hf download does; llama-quantize does not — delete the .part and relaunch
   detached).

3. Advance the frontier in priority order:
   a. anything newly unblocked in the post-download chain (convert -> imatrix -> KLD base ->
      baseline quant -> Phase-0 epsilon), launched detached in tmux with logs, TODO updated with
      window+PID;
   b. remaining skeleton/harness items and their fixture tests;
   c. if refs/ has been populated (HUMAN gate cleared), finalize the harness manifest and run
      score.sh --verify-only.

4. Mode switch: if the full prerequisite chain through harness/epsilon.txt is done AND GPUs are
   free AND the gpu lock is available — stop bootstrapping and run a research session under
   program.md for the remaining budget (Tier-A-heavy if less than 3 h remain; no Tier C).

5. Constraints carried over from bootstrap, verbatim: never kill llama-swap/llama-server PIDs;
   never write large artifacts to the root fs; never execute [HUMAN] items — refresh their
   ready-to-paste commands if stale; never edit harness/, runner/ (post-freeze), or program.md.

6. Final 15 min: update every TODO state; write notes/handoff-<UTC timestamp>.md — running jobs
   with PIDs and ETAs, next three actions for your successor, open HUMAN gates. Exit cleanly
   rather than starting anything that cannot checkpoint.
