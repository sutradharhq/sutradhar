"""The example must keep demonstrating, or it is worse than not shipping it.

A walkthrough that has quietly stopped catching its planted defects is
exactly the decoration this framework exists to name - and it fails in the
most damaging place, in front of someone evaluating whether any of this
works. So the demo runs in CI like any other guard.

Verified by mutation before being written down: fixing the silent swallow,
making the decorative test real, or enforcing the orphan budget each turns
the runner red (6 of 7, exit 1).
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "examples" / "run-the-guards.sh"
APP = ROOT / "examples" / "broken-app"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or not RUNNER.exists(),
    reason="needs bash and the examples tree",
)


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
