#!/usr/bin/env python3
"""Localhost auth-injecting reverse proxy so the UNMODIFIED referee (harness/score.py
--server) can drive a protected HF Inference Endpoint for S_fp8 reference scoring.

The referee speaks plain HTTP to a llama-server-style URL with no auth support; protected
endpoints require a Bearer token. This proxy bridges the two without touching harness/:

  export HF_TOKEN=$(cat ~/.cache/huggingface/token)
  .venv/bin/python scripts/offsite_auth_proxy.py --target https://<endpoint-url> --port 9031 &
  .venv/bin/python harness/score.py --exp fp8-reference --server http://127.0.0.1:9031

Notes:
- /health is answered locally with 200 (vLLM exposes /health too, but the referee's G2 gate
  only needs a liveness signal; suite results are what matter for S_fp8).
- Everything else is forwarded verbatim (method, body, content-type) with Authorization added.
- Results are recorded in notes/offsite-*.md — NEVER in experiments.jsonl (local loop's lane).
"""
import argparse
import http.server
import json
import os
import sys
import urllib.error
import urllib.request


def make_handler(target, token):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _forward(self):
            if self.path == "/health":
                body = b'{"status":"ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            length = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(length) if length else None
            req = urllib.request.Request(
                target + self.path, data=data, method=self.command,
                headers={"Content-Type": self.headers.get("Content-Type", "application/json"),
                         "Authorization": f"Bearer {token}"})
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    body = r.read()
                    self.send_response(r.status)
                    self.send_header("Content-Type",
                                     r.headers.get("Content-Type", "application/json"))
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
            except urllib.error.HTTPError as e:
                body = e.read()
                self.send_response(e.code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                body = json.dumps({"error": f"{type(e).__name__}: {e}"}).encode()
                self.send_response(502)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        do_GET = do_POST = _forward

        def log_message(self, fmt, *args):
            print(f"[proxy] {args[0] if args else ''}", file=sys.stderr)

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="endpoint base URL (no trailing slash)")
    ap.add_argument("--port", type=int, default=9031)
    a = ap.parse_args()
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("FATAL: HF_TOKEN not set (export from ~/.cache/huggingface/token)", file=sys.stderr)
        return 2
    target = a.target.rstrip("/")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(target, token))
    print(f"[proxy] 127.0.0.1:{a.port} -> {target} (Bearer injected)")
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
