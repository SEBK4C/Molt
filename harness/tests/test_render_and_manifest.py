"""Fixtures for runner/render_quant_cmd.py and harness/manifest.py."""
import json
import os
import shutil
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "runner"))

import render_quant_cmd  # noqa: E402


def test_render_baseline_recipe():
    cmd = render_quant_cmd.render(
        os.path.join(REPO, "recipes/baseline.yaml"),
        imatrix="models/imatrix-agentic.dat",
        src="models/Ornith-Q8_0.gguf",
        out="models/ornith-molt-000.gguf",
        threads=32,
    )
    assert "--allow-requantize" in cmd
    assert "--imatrix models/imatrix-agentic.dat" in cmd
    assert "--tensor-type ffn_gate_exps=iq2_xxs" in cmd
    assert "--tensor-type ffn_down_exps=q2_k" in cmd
    assert "'.*gate.*|shared_expert.*=q8_0'" in cmd  # regex needing shell quoting
    assert cmd.rstrip().endswith("&& mv models/ornith-molt-000.gguf.part models/ornith-molt-000.gguf")
    assert " Q8_0 32 " in cmd  # fallback type + threads positionals


def test_render_rejects_unknown_type(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("tensor_types:\n  - pattern: x\n    type: q9_z\nsource_gguf: a.gguf\n")
    with pytest.raises(SystemExit):
        render_quant_cmd.render(str(p), out="o.gguf")


def test_render_rejects_bad_regex(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("tensor_types:\n  - pattern: '['\n    type: q8_0\nsource_gguf: a.gguf\n")
    with pytest.raises(Exception):
        render_quant_cmd.render(str(p), out="o.gguf")


def test_render_requires_out():
    with pytest.raises(SystemExit):
        render_quant_cmd.render(os.path.join(REPO, "recipes/baseline.yaml"), out=None)


def test_render_rejects_duplicate_pattern(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("tensor_types:\n  - pattern: x\n    type: q8_0\n"
                 "  - pattern: x\n    type: q6_k\nsource_gguf: a.gguf\n")
    with pytest.raises(SystemExit):
        render_quant_cmd.render(str(p), out="o.gguf")


# --- manifest ---------------------------------------------------------------
def run_manifest(harness_dir, *args):
    return subprocess.run([sys.executable, os.path.join(harness_dir, "manifest.py"), *args],
                          capture_output=True, text=True)


@pytest.fixture
def mini_harness(tmp_path):
    h = tmp_path / "harness"
    h.mkdir()
    shutil.copy(os.path.join(REPO, "harness/manifest.py"), h / "manifest.py")
    (h / "prompts").mkdir()
    (h / "prompts" / "a.json").write_text('{"x": 1}')
    (h / "refs").mkdir()
    (h / "refs" / "a.json").write_text('{"y": 2}')
    return str(h)


def test_manifest_write_verify_roundtrip(mini_harness):
    assert run_manifest(mini_harness, "--write", "--provisional").returncode == 0
    man = json.load(open(os.path.join(mini_harness, "manifest.json")))
    assert "prompts/a.json" in man and "manifest.py" in man
    assert run_manifest(mini_harness, "--verify").returncode == 0


def test_manifest_detects_modification(mini_harness):
    run_manifest(mini_harness, "--write")
    with open(os.path.join(mini_harness, "refs/a.json"), "w") as f:
        f.write('{"y": 3}')
    r = run_manifest(mini_harness, "--verify")
    assert r.returncode == 2 and "MODIFIED refs/a.json" in r.stderr


def test_manifest_detects_deletion(mini_harness):
    run_manifest(mini_harness, "--write")
    os.unlink(os.path.join(mini_harness, "prompts/a.json"))
    r = run_manifest(mini_harness, "--verify")
    assert r.returncode == 2 and "MISSING prompts/a.json" in r.stderr


def test_manifest_detects_added_file(mini_harness):
    run_manifest(mini_harness, "--write")
    with open(os.path.join(mini_harness, "refs/sneaky.json"), "w") as f:
        f.write("{}")
    r = run_manifest(mini_harness, "--verify")
    assert r.returncode == 2 and "UNTRACKED refs/sneaky.json" in r.stderr
