# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Tests for the CI-step reachability guard (R18-3).

6.7 applied to CI wiring. A step whose interpreter exits 2 on file-not-found
has made a claim about a process and none about the code under test, and it
takes every later step in the job with it - so the red reads as "the guard is
failing" when it means "the guard is absent". Same class as R16-1: something
that worked in exactly one layout, invisible from inside that layout.

The refusals matter as much as the catches. A guard that flagged the absolute
paths a job writes for itself, or a template's paths, would be muted inside a
week.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards import ci_step_lint as csl  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def _repo(tmp_path: Path, workflow: str) -> Path:
    """A tree with one reachable script and one workflow in the real place."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "reachable.py").write_text("x = 1\n")
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(workflow)
    return tmp_path


JOB_DEFAULT_WD = """
jobs:
  a:
    defaults:
      run:
        working-directory: backend
    steps:
      - name: cannot find its script
        run: python3 scripts/reachable.py
"""

OPTS_OUT = """
jobs:
  a:
    defaults:
      run:
        working-directory: backend
    steps:
      - name: opts out
        working-directory: .
        run: python3 scripts/reachable.py
"""


# ── the invariant ───────────────────────────────────────────────────────────

def test_a_step_that_cannot_reach_its_script_is_flagged(tmp_path):
    root = _repo(tmp_path, JOB_DEFAULT_WD)
    problems, checked, _ = csl.audit(
        root / ".github" / "workflows" / "ci.yml", root
    )
    assert len(problems) == 1 and checked == 1
    assert "scripts/reachable.py" in problems[0]
    assert "backend" in problems[0]


def test_a_step_that_opts_out_of_the_job_directory_is_clean(tmp_path):
    root = _repo(tmp_path, OPTS_OUT)
    problems, checked, _ = csl.audit(
        root / ".github" / "workflows" / "ci.yml", root
    )
    assert problems == [] and checked == 1


def test_a_step_level_working_directory_is_applied(tmp_path):
    root = _repo(tmp_path, """
jobs:
  a:
    steps:
      - name: names its own directory
        working-directory: backend
        run: python3 scripts/reachable.py
""")
    problems, _, _ = csl.audit(root / ".github" / "workflows" / "ci.yml", root)
    assert len(problems) == 1


def test_a_multiline_run_block_is_read_whole(tmp_path):
    """The scar's step was one line in a block. A scanner that read only the
    `run:` line itself would pass every real workflow forever."""
    root = _repo(tmp_path, """
jobs:
  a:
    defaults:
      run:
        working-directory: backend
    steps:
      - name: a block
        run: |
          echo hello
          python3 scripts/reachable.py
          echo done
""")
    problems, _, _ = csl.audit(root / ".github" / "workflows" / "ci.yml", root)
    assert len(problems) == 1


def test_the_inline_dash_run_form_is_read_as_a_step(tmp_path):
    """Found while building this: the scanner only matched a `run:` on its own
    line, so every `- run: |` step was skipped without a word. On this repo's
    own workflow that was four jobs and eight of nineteen script references -
    a guard reporting green over what it had not read (2.4)."""
    root = _repo(tmp_path, """
jobs:
  a:
    defaults:
      run:
        working-directory: backend
    steps:
      - run: |
          python3 scripts/reachable.py
""")
    problems, checked, _ = csl.audit(
        root / ".github" / "workflows" / "ci.yml", root
    )
    assert checked == 1, "the `- run:` step was not read at all"
    assert len(problems) == 1


def test_the_defaults_run_key_is_not_read_as_a_step(tmp_path):
    """`defaults: run: working-directory:` carries a `run:` key that is not a
    step; counting it makes every later assertion about the scan unreadable."""
    assert len(list(csl.steps(JOB_DEFAULT_WD))) == 1
    assert list(csl.steps(JOB_DEFAULT_WD))[0][1] == "backend"


# ── the refusals, which keep it from being muted ────────────────────────────

def test_an_absolute_path_is_skipped_and_counted(tmp_path):
    """It does not resolve against a working directory at all, and is usually
    a file an earlier step in the same job wrote. Skipped - and SAID, because
    an exclusion the operator cannot see is the lie this guard is about."""
    root = _repo(tmp_path, """
jobs:
  a:
    steps:
      - run: python3 /tmp/target/scripts/reachable.py
""")
    problems, checked, skipped = csl.audit(
        root / ".github" / "workflows" / "ci.yml", root
    )
    assert problems == [] and checked == 0 and skipped == 1


def test_a_bare_filename_is_not_guessed_at(tmp_path):
    root = _repo(tmp_path, """
jobs:
  a:
    steps:
      - run: python3 setup.py check
""")
    problems, checked, _ = csl.audit(
        root / ".github" / "workflows" / "ci.yml", root
    )
    assert problems == [] and checked == 0


def test_a_non_python_path_is_left_alone(tmp_path):
    root = _repo(tmp_path, """
jobs:
  a:
    steps:
      - run: node js/probe/selftest.mjs
""")
    problems, checked, _ = csl.audit(
        root / ".github" / "workflows" / "ci.yml", root
    )
    assert problems == [] and checked == 0


# ── the CLI ─────────────────────────────────────────────────────────────────

def test_the_cli_gates_a_repo_root(tmp_path):
    assert csl.main([str(_repo(tmp_path, JOB_DEFAULT_WD))]) == 1


def test_the_cli_passes_a_clean_repo_root(tmp_path):
    assert csl.main([str(_repo(tmp_path, OPTS_OUT))]) == 0


def test_the_cli_takes_a_single_file(tmp_path):
    root = _repo(tmp_path, JOB_DEFAULT_WD)
    assert csl.main([str(root / ".github" / "workflows" / "ci.yml")]) == 1


def test_a_directory_with_no_workflows_exits_two_not_zero(tmp_path, capsys):
    """2.9. Asked whether every step can reach its script and handed nothing
    to read, the honest answer is "I did not check" - never a green line."""
    empty = tmp_path / "wf"
    empty.mkdir()
    assert csl.main([str(empty)]) == 2
    assert "nothing was checked" in capsys.readouterr().err


def test_no_argument_at_all_is_a_selfcheck(capsys):
    assert csl.main([]) == 0
    assert "ci-step-lint" in capsys.readouterr().out


def test_two_paths_are_refused_rather_than_half_read(tmp_path, capsys):
    assert csl.main([str(tmp_path), str(tmp_path)]) == 2
    assert "nothing was checked" in capsys.readouterr().err


def test_an_unknown_flag_is_refused_with_two(tmp_path):
    assert csl.main([str(tmp_path), "--selfchek"]) == 2


def test_repo_root_can_be_named_explicitly(tmp_path):
    """A workflow directory that is not under the root it resolves against -
    a vendored or generated workflow - must still be checkable."""
    root = _repo(tmp_path, OPTS_OUT)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "ci.yml").write_text(JOB_DEFAULT_WD)
    assert csl.main([str(elsewhere), "--repo-root", str(root)]) == 1


def test_the_root_it_used_is_printed(tmp_path, capsys):
    """A root guessed silently makes every verdict under it unreadable."""
    csl.main([str(_repo(tmp_path, OPTS_OUT))])
    assert "repo root:" in capsys.readouterr().out


def test_a_blinded_scanner_fails_the_cli(tmp_path, monkeypatch):
    """The wiring test: the path from "the scanner went vacuous" to "CI goes
    red" is under test. A clean tree is green; blinded, the same clean tree
    must go red because the embedded selfcheck loses its planted bad case."""
    root = _repo(tmp_path, OPTS_OUT)
    assert csl.main([str(root)]) == 0
    monkeypatch.setattr(csl, "steps", lambda text: iter(()))
    assert csl.main([str(root)]) == 1


def test_the_selfcheck_passes_and_names_what_it_exercised(capsys):
    """6.7: a silent exit 0 cannot be told from a check that never ran."""
    assert csl.selfcheck()
    out = capsys.readouterr().out
    assert "ci-step-lint" in out
    for claim in ("unreachable script rejected", "absolute path skipped"):
        assert claim in out, out


# ── this repository's own wiring ────────────────────────────────────────────

def test_this_repos_workflows_can_all_reach_their_scripts():
    """The real seam, on the real files (2.3). Every guard selftest.yml runs
    is named by a path; a rename that moves one of them lands here rather
    than as a red job nobody can read."""
    wf_dir = REPO_ROOT / ".github" / "workflows"
    files = sorted(wf_dir.glob("*.yml"))
    assert files, "no workflows found - this test would pass vacuously"
    total = 0
    for wf in files:
        problems, checked, _ = csl.audit(wf, REPO_ROOT)
        assert problems == [], "\n".join(problems)
        total += checked
    assert total >= 8, (
        f"only {total} script reference(s) checked across {len(files)} "
        f"workflow(s); the guard is looking at almost nothing"
    )


def test_the_ci_template_is_not_treated_as_this_repos_workflow():
    """`ci/guards.yml` names `scripts/*.py`, which resolve in the tree
    `bootstrap.sh` builds and not in this one. Pointing the guard at a
    template reports the template's whole point as a finding, so the docstring
    says not to - and this pins that the paths it names are the ones bootstrap
    actually copies, which is the check that IS worth having here."""
    template = (REPO_ROOT / "ci" / "guards.yml").read_text()
    bootstrap = (REPO_ROOT / "bootstrap.sh").read_text()
    named = set(csl._SCRIPT_RX.findall(template))
    assert named, "the template names no script - this test proves nothing"
    missing = sorted(
        ref for ref in named
        if f'"$TARGET/{ref}"' not in bootstrap
    )
    assert not missing, (
        f"ci/guards.yml runs {missing}, which bootstrap.sh does not copy into "
        f"the adopter's tree. Every step naming one of these would exit "
        f"non-zero on file-not-found on their first push."
    )
