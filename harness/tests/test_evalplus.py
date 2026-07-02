"""Fixtures for the sandboxed-exec evalplus checker."""
import score
from score import CANDIDATE_MARKER, check, extract_code, _have_unshare

TEST_CODE = (
    f"{CANDIDATE_MARKER}\n"
    "assert add_two(2) == 4\n"
    "assert add_two(-2) == 0\n"
)
REF = {"test_code": TEST_CODE, "timeout": 6}


def msg(content):
    return {"role": "assistant", "content": content}


def test_pass_correct_fenced_code():
    m = msg("Here you go:\n```python\ndef add_two(x):\n    return x + 2\n```")
    assert check("evalplus", m, REF) is True


def test_pass_raw_unfenced_code():
    m = msg("def add_two(x):\n    return x + 2\n")
    assert check("evalplus", m, REF) is True


def test_fail_wrong_logic():
    m = msg("```python\ndef add_two(x):\n    return x + 3\n```")
    assert check("evalplus", m, REF) is False


def test_fail_syntax_error():
    m = msg("```python\ndef add_two(x)\n    return x + 2\n```")
    assert check("evalplus", m, REF) is False


def test_fail_empty_content():
    assert check("evalplus", msg(""), REF) is False


def test_fail_infinite_loop_times_out():
    m = msg("```python\ndef add_two(x):\n    while True:\n        pass\n```")
    assert check("evalplus", m, {"test_code": TEST_CODE, "timeout": 3}) is False


def test_last_fence_wins():
    content = ("```python\ndef add_two(x):\n    return 0\n```\n"
               "wait, corrected:\n"
               "```python\ndef add_two(x):\n    return x + 2\n```")
    assert "return x + 2" in extract_code(msg(content))
    assert check("evalplus", msg(content), REF) is True


def test_fsize_rlimit_blocks_bulk_writes():
    m = msg("```python\ndef add_two(x):\n    return x + 2\n"
            "with open('big.bin','wb') as f:\n"
            "    f.write(b'0' * (64 * 1024 * 1024))\n```")
    assert check("evalplus", m, REF) is False


def test_network_blocked_under_unshare():
    if not _have_unshare():
        import pytest
        pytest.skip("unshare -r -n unavailable; net isolation is proxy-strangling only")
    m = msg("```python\nimport socket\n"
            "def add_two(x):\n    return x + 2\n"
            "socket.create_connection(('1.1.1.1', 80), timeout=3)\n```")
    assert check("evalplus", m, REF) is False


def test_sandbox_is_deterministic_bool():
    assert score.sandboxed_exec("import sys; sys.exit(0)", timeout=5) is True
    assert score.sandboxed_exec("import sys; sys.exit(1)", timeout=5) is False
