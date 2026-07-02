#!/usr/bin/env python3
"""molt D2 — verify the Ornith-1.0-397B BF16 download against the pinned HF tree snapshot.

Compares file count + per-file sizes vs hf-tree.json (saved at download start, revision-pinned);
with --deep also sha256-hashes every LFS file (the LFS oid IS the sha256) — slow (~0.5-2 h).

Usage: python scripts/verify_download.py [--deep] [--jobs 8]
Exit 0 = verified at requested depth; exit 1 = mismatches (listed on stderr).
NEVER deletes or modifies anything.
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import sys

BASE = "/mnt/proxmox/llm-serve/models/ornith-397b"
TREE = f"{BASE}/hf-tree.json"
DEST = f"{BASE}/hf-bf16"


def sha256_file(path, bufsize=16 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", action="store_true", help="sha256 all LFS files (slow)")
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()

    tree = json.load(open(TREE))
    files = [e for e in tree if e.get("type") == "file"]
    bad, missing = [], []
    total = 0

    for e in files:
        p = os.path.join(DEST, e["path"])
        if not os.path.exists(p):
            missing.append(e["path"])
            continue
        got = os.path.getsize(p)
        total += got
        if got != e["size"]:
            bad.append(f"SIZE {e['path']}: got {got} want {e['size']}")

    print(f"[verify] expected {len(files)} files / {sum(e['size'] for e in files)} bytes")
    print(f"[verify] present  {len(files) - len(missing)} files / {total} bytes")
    for m in missing[:20]:
        print(f"[verify] MISSING {m}", file=sys.stderr)
    if len(missing) > 20:
        print(f"[verify] ... and {len(missing) - 20} more missing", file=sys.stderr)

    if a.deep and not missing and not bad:
        lfs = [e for e in files if e.get("lfs")]
        print(f"[verify] deep: sha256 of {len(lfs)} LFS files ...")

        def one(e):
            got = sha256_file(os.path.join(DEST, e["path"]))
            want = e["lfs"]["oid"]
            return None if got == want else f"SHA256 {e['path']}: got {got} want {want}"

        with cf.ThreadPoolExecutor(a.jobs) as ex:
            for i, r in enumerate(ex.map(one, lfs), 1):
                if r:
                    bad.append(r)
                if i % 10 == 0:
                    print(f"[verify] deep progress {i}/{len(lfs)}")

    for b in bad:
        print(f"[verify] BAD {b}", file=sys.stderr)

    if missing or bad:
        print(f"[verify] FAIL: {len(missing)} missing, {len(bad)} bad", file=sys.stderr)
        sys.exit(1)
    print(f"[verify] OK at depth={'deep' if a.deep else 'shallow'}")


if __name__ == "__main__":
    main()
