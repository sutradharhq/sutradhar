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


# ── what a guard command is allowed to be (R16-3) ───────────────────────────
#
# This tool runs the command it is handed, as the user running it, and the
# string does not have to come from a person typing: it can be an MCP tool
# argument written by a model, or a `Guard-cmd:` trailer on a commit
# somebody else authored. Through a shell, "the guard command" and "an
# arbitrary shell" were the same surface. These pin the smaller surface.

@pytest.mark.parametrize("cmd,argv,subdir", [
    ("pytest -q tests/x.py", ["pytest", "-q", "tests/x.py"], None),
    # The shape every `Guard-cmd:` trailer in this repository's history uses.
    # The day this stops parsing, the per-commit check goes quietly
    # INCONCLUSIVE forever (R15-6 is what that failure looks like).
    ("cd python && python -m pytest tests/x.py -q",
     ["python", "-m", "pytest", "tests/x.py", "-q"], "python"),
    # Without a shell a quoted operator is just an argument.
    ('pytest -k "a|b"', ["pytest", "-k", "a|b"], None),
])
def test_a_guard_command_is_a_program_and_its_arguments(cmd, argv, subdir):
    assert vg.parse_guard_cmd(cmd) == (argv, subdir)


@pytest.mark.parametrize("cmd", [
    "pytest | cat",
    "pytest; rm -rf /",
    "echo $(id)",
    "`id`",
    "cd .. && pytest",
    "pytest && cd x",
    "",
    "   ",
    "pytest > log",
    "cd python",
    "pytest 'unclosed",
])
def test_a_command_only_a_shell_could_read_is_refused(cmd):
    with pytest.raises(vg.GuardCommandRefused):
        vg.parse_guard_cmd(cmd)


def test_a_cd_that_leaves_the_worktree_is_refused_at_resolution_too(tmp_path):
    """Belt and braces: the lexical `..` check is not the only thing standing
    between a guard command and somebody else's directory."""
    (tmp_path / "inside").mkdir()
    assert vg.resolve_guard_cwd(tmp_path, "inside") == (tmp_path / "inside").resolve()
    assert vg.resolve_guard_cwd(tmp_path, None) == tmp_path.resolve()
    with pytest.raises(vg.GuardCommandRefused):
        vg.resolve_guard_cwd(tmp_path / "inside", "../..")
    with pytest.raises(vg.GuardCommandRefused):
        vg.resolve_guard_cwd(tmp_path, "not-a-directory")


def test_the_cli_refuses_a_shell_command_as_inconclusive(tmp_path):
    """The exit code and the words, at the CLI seam.

    2 is INCONCLUSIVE - "no guard ran, so nothing was measured" (2.9). It is
    the one non-verdict code this tool has, and it must never be 0: a refusal
    reported as VERIFIED would be this tool claiming a check it declined to
    perform.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "sutradhar_guards.verify_guard",
         "--guard-cmd", "pytest | cat"],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True, text=True,
    )
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)
    said = proc.stdout + proc.stderr
    assert "not run through a shell" in said, said
    assert "INCONCLUSIVE" in said, said
    assert "VERIFIED" not in said and "DECORATION" not in said, said


def test_the_cli_refuses_a_shell_setup_cmd_too():
    """`--setup-cmd` is the same door with a different sign on it."""
    proc = subprocess.run(
        [sys.executable, "-m", "sutradhar_guards.verify_guard",
         "--guard-cmd", "true", "--setup-cmd", "pip install x && curl evil"],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True, text=True,
    )
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)
    assert "not run through a shell" in proc.stdout + proc.stderr


def test_a_refused_command_is_inconclusive_and_never_a_verdict():
    root = vg._fixture_repo()
    try:
        res = vg.verify(root, commit="HEAD~1",
                        guard_cmd=f"{sys.executable} tests/check_real.py | cat")
        assert res.verdict == vg.INCONCLUSIVE and res.exit_code == 2
        assert "not run through a shell" in res.reason
    finally:
        __import__("shutil").rmtree(root, ignore_errors=True)


def test_the_cd_prefix_still_runs_the_guard():
    """The one convenience that survived, exercised end to end rather than
    at the parser: `cd tests && <python> check_real_here.py` must still
    reach VERIFIED."""
    root = vg._fixture_repo()
    try:
        res = vg.verify(
            root, commit="HEAD~1",
            guard_cmd=f"cd tests && {sys.executable} check_real_here.py")
        assert res.verdict == vg.VERIFIED, res.reason
    finally:
        __import__("shutil").rmtree(root, ignore_errors=True)


def test_no_shell_true_survives_anywhere_in_the_verifier():
    """A class ratchet over the AST, not a memory of this change.

    Over the AST rather than the text, so the sentence in the module
    docstring that promises no shell does not read as a violation of itself
    - a guard that goes red at the documentation of its own rule teaches
    everyone to delete it.
    """
    import ast
    source = Path(vg.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source, filename=vg.__file__)):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            assert not (kw.arg == "shell"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value), f"verify_guard.py:{node.lineno} shell=True"


def test_a_program_that_cannot_be_started_is_not_a_red():
    """A shell answered "no such program" with exit 127, which this tool
    would have read as a guard going red - a verdict about a process that
    never started."""
    root = vg._fixture_repo()
    try:
        res = vg.verify(root, commit="HEAD~1",
                        guard_cmd="sutradhar-no-such-program-anywhere --now")
        assert res.verdict == vg.INCONCLUSIVE, res.reason
        assert "could not be started" in res.reason
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
