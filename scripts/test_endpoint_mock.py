"""Mock test for scripts/hf_endpoint_goldens.py — proves the golden-generation path works
without any endpoint. Run: .venv/bin/python -m pytest scripts/test_endpoint_mock.py -q"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import hf_endpoint_goldens as g  # noqa: E402


class MockOpenAI(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        tools = body.get("tools") or []
        if tools:
            fn = tools[0]["function"]["name"]
            msg = {"role": "assistant", "content": None,
                   "tool_calls": [{"id": "m1", "type": "function",
                                   "function": {"name": fn,
                                                "arguments": json.dumps({"mock": True})}}]}
        else:
            msg = {"role": "assistant", "content": "mock reply text"}
        resp = {"choices": [{"message": msg}], "usage": {"completion_tokens": 5}}
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def test_mock_goldens(tmp_path):
    srv = HTTPServer(("127.0.0.1", 0), MockOpenAI)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{srv.server_port}"
    try:
        rc = g.main(["--mock", url, "--limit", "2", "--skip-traces",
                     "--out-dir", str(tmp_path)])
        assert rc == 0
        for suite in ("nested", "bfcl", "smoke", "tau"):
            p = tmp_path / f"{suite}.fp8.json"
            assert p.exists(), f"missing {p}"
            data = json.loads(p.read_text())
            assert len(data) == 2
        nested = json.loads((tmp_path / "nested.fp8.json").read_text())
        first = next(iter(nested.values()))
        assert first.get("name") == "submit_payload" and first.get("arguments") == {"mock": True}
        tau = json.loads((tmp_path / "tau.fp8.json").read_text())
        assert all("final_state" in v or "error" in v for v in tau.values())
    finally:
        srv.shutdown()


def test_real_mode_refuses_without_confirm():
    assert g.main(["--repo", "x/y"]) == 3


def test_dry_run_prints_cost(capsys):
    assert g.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "create_inference_endpoint" in out and "$" in out
