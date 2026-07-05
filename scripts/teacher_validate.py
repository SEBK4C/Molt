#!/usr/bin/env python3
"""Mechanical validators gating every teacher-generated sample (TEACHER-PROTOCOL §4).

Standalone by design — no imports from harness/ (frozen; validators must not create pressure
to touch it). deep_eq reproduces the referee's documented semantics exactly: bool is never
int, int == float compares numerically, str never coerces.

validate_nested(demanded, produced_json_text) -> (ok, why)
    parse -> canonical re-serialize -> deep-equal round-trip against the demanded arguments.
validate_code(solution, test_script, timeout=10) -> (ok, why)
    sandboxed exec, harness pattern: subprocess -I, rlimits (CPU/AS/FSIZE/NOFILE), tmpdir,
    `unshare -r -n` network isolation when available.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile


def deep_eq(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(deep_eq(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(deep_eq(x, y) for x, y in zip(a, b))
    return a == b


def validate_nested(demanded, produced_text):
    """demanded: the python object the prompt demands verbatim. produced_text: the model's
    JSON text. Round-trip: parse -> canonical dumps -> parse -> deep_eq."""
    try:
        parsed = json.loads(produced_text)
    except (json.JSONDecodeError, TypeError) as e:
        return False, f"parse: {e}"
    try:
        canon = json.loads(json.dumps(parsed, ensure_ascii=False, sort_keys=False))
    except (ValueError, TypeError) as e:
        return False, f"reserialize: {e}"
    if not deep_eq(demanded, canon):
        return False, "deep_eq: mismatch after round-trip"
    return True, "ok"


def validate_code(solution, test_script, timeout=10):
    """Run solution+tests in a sandbox. test_script must raise/assert on failure and print
    nothing on success. Returns (passed, why)."""
    tmp = tempfile.mkdtemp(prefix="tval-")
    try:
        path = os.path.join(tmp, "case.py")
        with open(path, "w") as f:
            f.write(solution + "\n\n" + test_script + "\n")
        pre = ("import resource as _r\n"
               "_r.setrlimit(_r.RLIMIT_CPU, ({t}, {t}))\n"
               "_r.setrlimit(_r.RLIMIT_AS, (2**31, 2**31))\n"
               "_r.setrlimit(_r.RLIMIT_FSIZE, (2**24, 2**24))\n"
               "_r.setrlimit(_r.RLIMIT_NOFILE, (32, 32))\n"
               "exec(compile(open({p!r}).read(), {p!r}, 'exec'), {{'__name__': '__main__'}})\n"
               ).format(t=timeout, p=path)
        cmd = [sys.executable, "-I", "-c", pre]
        if shutil.which("unshare"):
            probe = subprocess.run(["unshare", "-r", "-n", "true"],
                                   capture_output=True, timeout=5)
            if probe.returncode == 0:
                cmd = ["unshare", "-r", "-n"] + cmd
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout + 5, cwd=tmp)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip().splitlines()
            return False, f"exec rc={r.returncode}: {tail[-1][:160] if tail else 'no output'}"
        return True, "ok"
    except subprocess.TimeoutExpired:
        return False, f"timeout >{timeout + 5}s"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    print("run tests: .venv/bin/python -m pytest scripts/test_teacher_validate.py -q")
