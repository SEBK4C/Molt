#!/usr/bin/env python3
"""molt harness manifest — SHA-256 freeze of everything under harness/.

Usage:
  manifest.py --write [--provisional]   # (re)generate manifest.json over harness/ contents
  manifest.py --verify                  # exit 0 clean / 2 on any mismatch (tamper)

Covers every file under harness/ recursively EXCEPT: manifest.json itself, manifest.meta.json,
__pycache__/, *.pyc, .pytest_cache. The provisional flag only annotates manifest.meta.json —
hashing is identical; FINAL freeze happens when refs/ is fully populated (drop --provisional).
score.py refuses to score when verification fails; that is the anti-reward-hacking contract.
"""
import argparse
import hashlib
import json
import os
import sys
import time

H = os.path.dirname(os.path.abspath(__file__))
EXCLUDE_NAMES = {"manifest.json", "manifest.meta.json"}
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache"}


def walk():
    out = {}
    for root, dirs, files in os.walk(H):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for fn in sorted(files):
            if fn in EXCLUDE_NAMES or fn.endswith(".pyc"):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, H)
            with open(p, "rb") as f:
                out[rel] = hashlib.sha256(f.read()).hexdigest()
    return out


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--verify", action="store_true")
    ap.add_argument("--provisional", action="store_true")
    a = ap.parse_args()

    if a.write:
        man = walk()
        with open(f"{H}/manifest.json", "w") as f:
            json.dump(man, f, indent=1, sort_keys=True)
        meta = {"provisional": a.provisional, "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "files": len(man)}
        with open(f"{H}/manifest.meta.json", "w") as f:
            json.dump(meta, f, indent=1)
        print(f"[manifest] wrote {len(man)} entries "
              f"({'PROVISIONAL' if a.provisional else 'FINAL'})")
        return

    man = json.load(open(f"{H}/manifest.json"))
    now = walk()
    bad = []
    for rel, want in man.items():
        got = now.get(rel)
        if got != want:
            bad.append(f"{'MISSING' if got is None else 'MODIFIED'} {rel}")
    for rel in now:
        if rel not in man:
            bad.append(f"UNTRACKED {rel}")
    if bad:
        for b in bad:
            print(f"[manifest] {b}", file=sys.stderr)
        print(f"[manifest] TAMPER: {len(bad)} deviations", file=sys.stderr)
        sys.exit(2)
    print(f"[manifest] OK ({len(man)} files)")


if __name__ == "__main__":
    main()
