#!/usr/bin/env bash
# Install the 5-hour molt cadence as a systemd user timer. Run once on llm-serve.
# Fire the FIRST invocation manually at the moment your Claude rate-limit window resets —
# OnUnitActiveSec anchors subsequent runs to that instant, keeping the timer phase-locked
# to the 5h reset instead of wall clock.
set -euo pipefail
mkdir -p ~/.config/systemd/user /home/seb/molt/notes/logs

cat > /home/seb/molt/runner/molt_tick.sh <<'EOF'
#!/usr/bin/env bash
set -a; source ~/.config/molt/env; set +a
cd /home/seb/molt
LOG=notes/logs/tick-$(date -u +%Y%m%dT%H%M%S).log
# -n: if the previous instance is somehow still alive, skip this tick entirely (no queueing)
exec flock -n /home/seb/molt/.molt.lock \
  claude -p "$(cat prompts/resume.md)" \
    --dangerously-skip-permissions --output-format text >"$LOG" 2>&1
EOF
chmod +x /home/seb/molt/runner/molt_tick.sh

cat > ~/.config/systemd/user/molt.service <<'EOF'
[Unit]
Description=molt 5h resume tick
[Service]
Type=oneshot
WorkingDirectory=/home/seb/molt
ExecStart=/home/seb/molt/runner/molt_tick.sh
TimeoutStartSec=17400
EOF

cat > ~/.config/systemd/user/molt.timer <<'EOF'
[Unit]
Description=fire molt tick every 5h, phase-locked to first start
[Timer]
OnUnitActiveSec=5h
AccuracySec=1min
Persistent=false
[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable molt.timer
loginctl enable-linger "$USER"   # timer survives logout/SSH disconnect
echo ">> Phase-lock: at the next rate-limit reset run:"
echo ">>   systemctl --user start molt.service && systemctl --user start molt.timer"
