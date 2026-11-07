"""The example must keep demonstrating, or it is worse than not shipping it.

A walkthrough that has quietly stopped catching its planted defects is
exactly the decoration this framework exists to name - and it fails in the
most damaging place, in front of someone evaluating whether any of this
works. So the demo runs in CI like any other guard.

Verified by mutation before being written down: fixing the silent swallow,
making the decorative test real, or enforcing the orphan budget each turns
the runner red (6 of 7, exit 1).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "examples" / "run-the-guards.sh"
APP = ROOT / "examples" / "broken-app"

def _missing() -> "str | None":
    """Why the demo cannot run here, or None."""
    if shutil.which("bash") is None:
        return "bash is not on PATH"
    if not RUNNER.exists():
        return f"{RUNNER} does not exist"
    return None


# A skip is not a pass (2.9, B-66). Off CI a contributor without bash may skip
# the demo and is told so; on CI (GitHub sets CI=true) a missing dependency is
# a collection error, because a skipped module there reads as a green suite.
# Verified by mutation: renaming examples/run-the-guards.sh with CI=true makes
# this module error and pytest exit 2; without CI it skips with the reason.
_WHY = _missing()
if _WHY and os.environ.get("CI", "").lower() not in ("", "0", "false"):
    pytest.fail(f"the demo cannot run: {_WHY}. On CI that is a failure, not "
                f"a skip (2.9, B-66).", pytrace=False)
pytestmark = pytest.mark.skipif(_WHY is not None,
                                reason=f"needs bash and the examples tree: {_WHY}")


def _run():
    return subprocess.run(
        ["bash", str(RUNNER)], capture_output=True, text=True,
        env={"PATH": __import__("os").environ["PATH"], "PYTHON": sys.executable},
        cwd=str(ROOT), timeout=300,
    )


def test_every_planted_defect_is_still_caught():
    proc = _run()
    assert proc.returncode == 0, (
        "the examples demo missed a planted defect - it is currently lying to "
        f"anyone who runs it:\n{proc.stdout}\n{proc.stderr}"
    )
    assert "7 of 7 planted defects caught" in proc.stdout


def test_the_apps_own_suite_is_green():
    """The punchline depends on this: the defects live in a codebase whose
    tests pass. If the example's suite ever goes red, the demo stops making
    its point and starts looking like a broken build."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        capture_output=True, text=True, cwd=str(APP), timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "5 passed" in proc.stdout and "1 skipped" in proc.stdout


def test_the_runner_fails_when_a_defect_is_fixed(tmp_path):
    """Mutation: the demo's own pass/fail must discriminate. A runner that
    reports success regardless would be the purest decoration in the repo."""
    sandbox = tmp_path / "sutradhar"
    shutil.copytree(ROOT, sandbox, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", "*.pyc", "node_modules"))
    readings = sandbox / "examples" / "broken-app" / "app" / "readings.py"
    readings.write_text(readings.read_text().replace(
        "    except Exception:\n        return {}",
        "    except Exception:\n        raise"))
    proc = subprocess.run(
        ["bash", str(sandbox / "examples" / "run-the-guards.sh")],
        capture_output=True, text=True,
        env={"PATH": __import__("os").environ["PATH"], "PYTHON": sys.executable},
        cwd=str(sandbox), timeout=300,
    )
    assert proc.returncode == 1, "the runner passed with a planted defect removed"
    assert "MISSED" in proc.stdout


def test_the_runner_fails_when_a_check_is_deleted(tmp_path):
    """R22-1: the total used to be counted from the blocks that ran, so
    deleting one printed "6 of 6" and exited 0 - and a deleted check is the
    one edit nobody reviews as a weakening. The runner now declares
    EXPECTED and refuses a run whose count differs.

    Mutation: restoring the old tail (report `$step` as the total, no
    EXPECTED comparison) turns this red with exit 0 and "6 of 6"."""
    sandbox = tmp_path / "sutradhar"
    shutil.copytree(ROOT, sandbox, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", "*.pyc", "node_modules"))
    runner = sandbox / "examples" / "run-the-guards.sh"
    text = runner.read_text()
    start = text.index("# 3. query interpolation")
    end = text.index("# 4. fabricated numbers")
    runner.write_text(text[:start] + text[end:])
    proc = subprocess.run(
        ["bash", str(runner)], capture_output=True, text=True,
        env={"PATH": __import__("os").environ["PATH"], "PYTHON": sys.executable},
        cwd=str(sandbox), timeout=300,
    )
    assert proc.returncode == 1, (
        f"the runner passed with a check deleted:\n{proc.stdout}")
    assert "6 of 7 checks ran" in proc.stdout
    assert "6 of 6" not in proc.stdout
