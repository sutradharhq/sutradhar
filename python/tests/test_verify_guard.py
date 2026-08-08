"""Tests for verify_guard - the tool that mechanises doctrine 2.2.

This file carries a heavier burden than most. verify_guard exists to catch
guards that cannot fail, so a verify_guard that cannot fail would be the
purest possible instance of the defect it hunts. The load-bearing tests are
therefore the MUTATION ones at the bottom: they blind the tool and require
its selfcheck to go red.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards import verify_guard as vg


# ── classification (pure) ───────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "tests/test_billing.py", "src/foo_test.go", "cypress/e2e/cart.cy.ts",
    "app/__tests__/nav.spec.tsx", "conftest.py", "spec/models/user_spec.rb",
    "scripts/swallow_baseline.json",
])
def test_guard_paths_are_kept(path):
    assert vg.is_guard_path(path)


@pytest.mark.parametrize("path", [
    "src/billing.py", "app/components/Cart.tsx", "src/latest.go",
    "config/timeouts.yaml", "lib/manifest.json",
])
def test_production_paths_are_reverted(path):
    assert not vg.is_guard_path(path) and not vg.is_inert_path(path)


@pytest.mark.parametrize("path", ["README.md", "docs/adoption.md", "LICENSE",
                                  "assets/logo.svg"])
def test_prose_and_media_are_inert(path):
    assert vg.is_inert_path(path)


def test_requirements_txt_is_not_inert():
    # .txt, but it pins what actually gets installed: reverting it changes
    # behaviour, so it is production code.
    assert not vg.is_inert_path("requirements.txt")
    assert not vg.is_inert_path("requirements-dev.txt")


def test_classify_splits_three_ways():
    code, guard, inert = vg.classify(
        ["src/billing.py", "tests/test_billing.py", "README.md"]
    )
    assert code == ["src/billing.py"]
    assert guard == ["tests/test_billing.py"]
    assert inert == ["README.md"]


def test_explicit_code_list_is_exhaustive():
    # Naming --code makes everything else a guard, so an oddly-named test
    # file is never swept into the revert set.
    code, guard, _ = vg.classify(
        ["src/a.py", "checks/verify_a.py"], code_patterns=["src/a.py"]
    )
    assert code == ["src/a.py"] and guard == ["checks/verify_a.py"]


def test_explicit_code_overrides_the_inert_heuristic():
    code, _, inert = vg.classify(["docs/api.md"], code_patterns=["docs/api.md"])
    assert code == ["docs/api.md"] and inert == []


# ── grading a red ───────────────────────────────────────────────────────────

def test_assertion_failure_is_a_strong_red():
    weak, _ = vg.grade_red("E   AssertionError: assert 1000.0 == 900.0")
    assert not weak


def test_import_error_is_a_weak_red():
    weak, why = vg.grade_red("ModuleNotFoundError: No module named 'discount'")
    assert weak and "weaker proof" in why


# ── end to end, on real git repos ───────────────────────────────────────────

def test_selfcheck_classification_passes():
    assert vg.selfcheck_classification()


def test_end_to_end_selfcheck_passes():
    """A real guard, a decorative guard, a broken premise and a docs-only
    commit, on four real repos, distinguished correctly."""
    assert vg.selfcheck_end_to_end()


def test_cli_selfcheck_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "sutradhar_guards.verify_guard", "--selfcheck"],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_not_a_git_repo_is_inconclusive_not_a_pass(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "sutradhar_guards.verify_guard",
         "--repo", str(tmp_path), "--guard-cmd", "true"],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True, text=True,
    )
    assert proc.returncode == 2, "a non-repo must be INCONCLUSIVE (2), never a pass"


def test_missing_guard_cmd_is_inconclusive(tmp_path):
    res = vg.verify(tmp_path, guard_cmd="")
    assert res.verdict == vg.INCONCLUSIVE and res.exit_code == 2


def test_piped_guard_cmd_is_warned_about():
    """Doctrine 6.3: `pytest ... | tee log` reports tee's exit code, so the
    guard is green while pytest is red. The tool must say so."""
    root = vg._fixture_repo()
    try:
        res = vg.verify(root, commit="HEAD~1",
                        guard_cmd=f"{sys.executable} tests/check_real.py | cat")
        assert any("pipe" in w for w in res.warnings)
    finally:
        __import__("shutil").rmtree(root, ignore_errors=True)


# ── mutation: blind the tool, its selfcheck MUST go red ─────────────────────
#
# Doctrine 2.2 turned on verify_guard itself. Each of these was run by hand
# against the real file before being written down here; all three go red.

def test_a_tool_that_always_says_verified_fails_its_own_selfcheck(monkeypatch):
    """The purest vacuity failure: if verify() could never return
    DECORATION, every CI run would pass while proving nothing."""
    real = vg.verify

    def never_decorates(*args, **kwargs):
        res = real(*args, **kwargs)
        if res.verdict == vg.DECORATION:
            res.verdict = vg.VERIFIED
        return res

    monkeypatch.setattr(vg, "verify", never_decorates)
    assert not vg.selfcheck_end_to_end(), (
        "a tool blinded to DECORATION still passed its selfcheck - the "
        "selfcheck is decoration"
    )


def test_a_blind_guard_classifier_fails_the_selfcheck(monkeypatch):
    """If test files are swept into the revert set, the guard disappears
    along with the fix and every verdict becomes meaningless."""
    monkeypatch.setattr(vg, "is_guard_path", lambda path: False)
    assert not vg.selfcheck_end_to_end()


def test_a_blind_inert_detector_fails_the_selfcheck(monkeypatch):
    """The bug the selfcheck caught on its first run: without the inert
    class, a docs-only commit is reported as DECORATION - a false
    accusation against a perfectly good guard."""
    monkeypatch.setattr(vg, "is_inert_path", lambda path: False)
    # Both halves must notice, not just the cheap one.
    assert not vg.selfcheck_classification(), "the cheap selfcheck missed it"
    assert not vg.selfcheck_end_to_end(), "the end-to-end selfcheck missed it"


def test_guard_collision_warning_does_not_fire_on_substrings():
    """`golden.py` is not mentioned by `test_claim_check_golden.py`; a
    warning that cries wolf gets muted, and a muted net is worse than none."""
    root = vg._fixture_repo()
    try:
        res = vg.verify(root, commit="HEAD~1",
                        guard_cmd=f"{sys.executable} tests/check_real.py")
        assert not any("may be the guard itself" in w for w in res.warnings), res.warnings
    finally:
        __import__("shutil").rmtree(root, ignore_errors=True)


def test_guard_collision_warning_fires_on_a_real_collision():
    root = vg._fixture_repo()
    try:
        # calc.py is production code; naming it in the guard command means
        # the run would revert the very thing it is checking.
        res = vg.verify(root, commit="HEAD~1",
                        guard_cmd=f"{sys.executable} tests/check_real.py calc.py")
        assert any("may be the guard itself" in w for w in res.warnings), res.warnings
    finally:
        __import__("shutil").rmtree(root, ignore_errors=True)
