"""Tests for swallow_lint - including the red cases.

Every guard here is itself mutation-verified: for each thing the detector
must catch there is a test that FAILS if the detector goes blind to it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.swallow_lint import check_source, main, selfcheck


def test_flags_return_empty_dict():
    src = """
def f():
    try:
        risky()
    except Exception:
        return {}
"""
    assert len(check_source(src)) == 1


def test_flags_bare_except_pass():
    src = """
def f():
    try:
        risky()
    except:
        pass
"""
    assert len(check_source(src)) == 1


def test_flags_tuple_handler_containing_exception():
    src = """
def f():
    try:
        risky()
    except (ValueError, Exception):
        return None
"""
    assert len(check_source(src)) == 1


def test_flags_continue_in_loop():
    src = """
def f(items):
    for i in items:
        try:
            risky(i)
        except Exception:
            continue
"""
    assert len(check_source(src)) == 1


def test_logged_swallow_is_clean():
    src = """
def f():
    try:
        risky()
    except Exception as exc:
        log.warning(f"degraded: {exc}")
        return {}
"""
    assert check_source(src) == []


def test_reraise_is_clean():
    src = """
def f():
    try:
        risky()
    except Exception:
        cleanup()
        raise
"""
    assert check_source(src) == []


def test_narrow_handler_is_clean():
    # A narrow catch that returns empty is a judgment call, not a swallow of
    # the world - the guard only polices broad handlers.
    src = """
def f():
    try:
        risky()
    except KeyError:
        return {}
"""
    assert check_source(src) == []


def test_custom_degrade_call_is_clean():
    src = """
def f():
    try:
        risky()
    except Exception:
        mark_degraded("f")
        return {}
"""
    assert check_source(src, extra_calls={"mark_degraded"}) == []


def test_handler_doing_real_work_is_clean():
    src = """
def f():
    try:
        risky()
    except Exception:
        result = fallback_computation()
        return result
"""
    assert check_source(src) == []


def test_selfcheck_passes():
    assert selfcheck()


def test_baseline_ratchet_flow(tmp_path, monkeypatch):
    """End to end: baseline freezes today, a new swallow beyond it fails."""
    monkeypatch.chdir(tmp_path)
    mod = tmp_path / "m.py"
    mod.write_text(
        "def f():\n    try:\n        g()\n    except Exception:\n        return {}\n"
    )
    baseline = tmp_path / "swallow_baseline.json"

    assert main([str(mod), "--update-baseline", "--baseline", str(baseline)]) == 0
    assert json.loads(baseline.read_text()) == {"m.py": 1}

    # At the baseline: green.
    assert main([str(mod), "--baseline", str(baseline)]) == 0

    # One MORE swallow: red. This is the mutation case for the ratchet.
    mod.write_text(
        mod.read_text()
        + "def h():\n    try:\n        g()\n    except Exception:\n        return []\n"
    )
    assert main([str(mod), "--baseline", str(baseline)]) == 1
