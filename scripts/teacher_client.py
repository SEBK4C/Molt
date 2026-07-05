#!/usr/bin/env python3
"""GLM-5.2 teacher client for TEACHER-PROTOCOL.md. The ONLY sanctioned path to the teacher.

- Key from ~/.config/molt/env (FIREWORKS_API_KEY) or env; never passed as an argument.
- Disk cache keyed on the full request (deterministic reruns are free; temperature>0 calls
  can pass cache=False).
- Usage metering: every real call appends {ts, model, usage, est_cost} to
  notes/logs/teacher-usage.jsonl. spent() sums it; callers enforce the protocol's $25 cap.
- GLM-5.2 via this router emits raw thinking in content: extract_final() returns the last
  fenced block or last JSON object — never trust prefix text.

CLI smoke: .venv/bin/python scripts/teacher_client.py "Reply with exactly: TEACHER-ONLINE"
"""
import hashlib
import json
import os
import sys
import time
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://api.fireworks.ai/inference/v1/chat/completions"
MODEL = "accounts/fireworks/routers/glm-5p2-fast"
CACHE_DIR = os.path.join(REPO_ROOT, "corpora", "teacher", ".cache")
USAGE_LOG = os.path.join(REPO_ROOT, "notes", "logs", "teacher-usage.jsonl")
# Fireworks GLM-5.2 list price unknown at write time — measure and correct. Conservative
# placeholder so the cap trips EARLY, not late.
EST_USD_PER_MTOK_IN = 0.60
EST_USD_PER_MTOK_OUT = 2.20


def _key():
    k = os.environ.get("FIREWORKS_API_KEY")
    if not k and os.path.exists(os.path.expanduser("~/.config/molt/env")):
        for line in open(os.path.expanduser("~/.config/molt/env")):
            if line.startswith("FIREWORKS_API_KEY="):
                k = line.split("=", 1)[1].strip()
    if not k:
        sys.exit("FATAL: FIREWORKS_API_KEY not in env or ~/.config/molt/env")
    return k


def spent():
    """Cumulative estimated USD across all logged teacher calls."""
    total = 0.0
    if os.path.exists(USAGE_LOG):
        for line in open(USAGE_LOG):
            try:
                total += json.loads(line).get("est_cost", 0.0)
            except json.JSONDecodeError:
                pass
    return total


def chat(messages, max_tokens=4096, temperature=0.0, cache=True, retries=3):
    body = {"model": MODEL, "max_tokens": max_tokens, "temperature": temperature,
            "messages": messages}
    h = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:24]
    cpath = os.path.join(CACHE_DIR, f"{h}.json")
    if cache and os.path.exists(cpath):
        return json.load(open(cpath))

    req = urllib.request.Request(
        URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": f"Bearer {_key()}",
                 "User-Agent": "molt-teacher/1.0"})  # default Python-urllib UA gets CF-403'd
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                resp = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code != 429:
                raise RuntimeError(f"teacher call rejected (HTTP {e.code}, not retryable): "
                                   f"{e.read()[:300]}") from e
            last = e
            time.sleep(2 ** attempt * 5)
        except Exception as e:
            last = e
            time.sleep(2 ** attempt * 5)
    else:
        raise RuntimeError(f"teacher call failed after {retries} attempts: {last}")

    u = resp.get("usage", {})
    cost = (u.get("prompt_tokens", 0) * EST_USD_PER_MTOK_IN
            + u.get("completion_tokens", 0) * EST_USD_PER_MTOK_OUT) / 1e6
    os.makedirs(os.path.dirname(USAGE_LOG), exist_ok=True)
    with open(USAGE_LOG, "a") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "model": resp.get("model"), "usage": u,
                            "est_cost": round(cost, 6)}) + "\n")
    if cache:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cpath, "w") as f:
            json.dump(resp, f)
    return resp


def extract_final(content):
    """Final answer from a thinking-in-content reply: last fenced block if any, else the
    last balanced {...}/[...] JSON value, else the last non-empty line."""
    if not content:
        return ""
    if "```" in content:
        parts = content.split("```")
        if len(parts) >= 3:
            block = parts[-2]
            return block.split("\n", 1)[1] if "\n" in block and block.split("\n", 1)[0].strip().isalpha() else block
    for opener, closer in (("{", "}"), ("[", "]")):
        start = content.rfind(opener)
        while start != -1:
            depth = 0
            for i in range(start, len(content)):
                if content[i] == opener:
                    depth += 1
                elif content[i] == closer:
                    depth -= 1
                    if depth == 0:
                        cand = content[start:i + 1]
                        try:
                            json.loads(cand)
                            return cand
                        except json.JSONDecodeError:
                            break
            start = content.rfind(opener, 0, start)
    lines = [ln for ln in content.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else ""


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Reply with exactly: TEACHER-ONLINE"
    r = chat([{"role": "user", "content": prompt}], max_tokens=2048)
    content = r["choices"][0]["message"].get("content") or ""
    print("[final]", extract_final(content)[:200])
    print(f"[spent] ${spent():.4f} cumulative (cap $25 per TEACHER-PROTOCOL §5)")
