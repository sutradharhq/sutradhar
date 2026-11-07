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



# ── 6.3: a pipe that swallows the exit code (R22-3) ─────────────────────────
#
# Without pipefail a pipeline's status is its LAST command's, and GitHub runs
# a step with no `shell:` key as `bash -e {0}` - no pipefail. `pytest | tail`
# exits with tail's 0 whatever pytest said. Every test here goes through
# audit() or main(), the seam CI and the corpus both call.

def _pipe_problems(tmp_path: Path, workflow: str) -> list:
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = _repo(tmp_path, workflow)
    problems, _, _ = csl.audit(root / ".github" / "workflows" / "ci.yml", root)
    return [p for p in problems if "(6.3)" in p]


PIPED = """
jobs:
  a:
    steps:
      - run: python3 scripts/reachable.py | tail -5
"""


def test_a_build_piped_through_tail_without_pipefail_is_flagged(tmp_path):
    """Mutation: in swallowing_pipes(), `if len(segments) < 2:` changed to
    `< 99` (a scanner blind to every pipe) turns this red."""
    problems = _pipe_problems(tmp_path, PIPED)
    assert len(problems) == 1, problems
    assert "ci.yml:5:" in problems[0]
    assert "tail -5" in problems[0]


def test_the_cli_exits_one_on_a_swallowing_pipe(tmp_path, capsys):
    """Through the CLI, the seam CI calls. Mutation: `if len(segments) < 2:`
    changed to `< 99` turns this red - and the embedded selfcheck with it."""
    assert csl.main([str(_repo(tmp_path, PIPED))]) == 1
    assert "pipes a command's exit code away" in capsys.readouterr().err


def test_a_pipe_inside_a_block_is_reported_at_its_own_line(tmp_path):
    """The scar's shape is a line inside a block, and the finding must name
    that line, not the `run:` key. Mutation: `if len(segments) < 2:` changed
    to `< 99` turns this red."""
    problems = _pipe_problems(tmp_path, """
jobs:
  a:
    steps:
      - name: tests
        run: |
          echo start
          python3 -m pytest tests/ -q 2>&1 | tee pytest.log
""")
    assert len(problems) == 1, problems
    assert "ci.yml:8:" in problems[0]


def test_set_pipefail_before_the_pipe_makes_it_clean(tmp_path):
    """Mutation: `if armed: continue` changed to `if False: continue` (pipefail
    ignored) turns this red."""
    for i, opener in enumerate(
        ("set -o pipefail", "set -euo pipefail", "set -eo pipefail")
    ):
        assert _pipe_problems(tmp_path / str(i), f"""
jobs:
  a:
    steps:
      - run: |
          {opener}
          python3 scripts/reachable.py | tail -5
""") == [], opener


def test_pipefail_set_after_the_pipe_does_not_cover_it(tmp_path):
    """Pipefail arms the lines after it, not the whole step. Mutation:
    `armed = False` changed to `armed = bool(_PIPEFAIL_ON_RX.search(body))`
    (a whole-body search) turns this red."""
    assert len(_pipe_problems(tmp_path, """
jobs:
  a:
    steps:
      - run: |
          python3 scripts/reachable.py | tail -5
          set -o pipefail
""")) == 1


def test_shell_bash_on_the_step_is_clean_in_either_key_order(tmp_path):
    """GitHub expands a bare `shell: bash` to `bash --noprofile --norc -eo
    pipefail {0}`. YAML key order is free, so `shell:` after `run:` must
    count as much as before it. Mutation: the step-key scan `range(start,
    len(lines))` cut to `range(start, run_idx)` (keys before `run:` only)
    turns this red."""
    before = """
jobs:
  a:
    steps:
      - name: before
        shell: bash
        run: python3 scripts/reachable.py | tail -5
"""
    after = """
jobs:
  a:
    steps:
      - name: after
        run: python3 scripts/reachable.py | tail -5
        shell: bash
"""
    assert _pipe_problems(tmp_path / "b", before) == []
    assert _pipe_problems(tmp_path / "a", after) == []


def test_a_job_default_shell_bash_covers_its_steps(tmp_path):
    """Mutation: the job-header match in _effective_shell changed to
    `if False:` (job defaults never read) turns this red."""
    assert _pipe_problems(tmp_path, """
jobs:
  a:
    defaults:
      run:
        shell: bash
    steps:
      - run: python3 scripts/reachable.py | tail -5
""") == []


def test_a_workflow_default_shell_bash_covers_every_job(tmp_path):
    """Mutation: `if v and ln.startswith(" "):` in the workflow-defaults scan
    changed to `if False:` turns this red."""
    assert _pipe_problems(tmp_path, """
defaults:
  run:
    shell: bash
jobs:
  a:
    steps:
      - run: python3 scripts/reachable.py | tail -5
""") == []


def test_one_steps_shell_does_not_cover_the_next_step(tmp_path):
    """A shell read from the wrong step would pass the next one on its
    neighbour's setting. Mutation: the step-end test `if j > start and
    ln.strip() and ind <= dash:` changed to `if False:` (the scan runs on
    into the next step) turns this red."""
    assert len(_pipe_problems(tmp_path, """
jobs:
  a:
    steps:
      - run: python3 scripts/reachable.py | tail -5
      - run: python3 scripts/reachable.py | tail -5
        shell: bash
""")) == 1


def test_shell_sh_is_still_flagged(tmp_path):
    """`sh -e {0}` gets no pipefail; only bash's template carries it.
    Mutation: `shell.strip() == "bash"` widened to `in ("bash", "sh")` turns
    this red."""
    assert len(_pipe_problems(tmp_path, """
jobs:
  a:
    steps:
      - run: python3 scripts/reachable.py | tail -5
        shell: sh
""")) == 1


# The refusals: a guard that flagged these would be muted inside a week.

def test_logical_or_quoted_bars_and_expressions_are_not_pipes(tmp_path):
    """Mutation: _code_only() returning the raw line (quotes, expressions and
    comments read as code) turns this red."""
    assert _pipe_problems(tmp_path, """
jobs:
  a:
    steps:
      - run: |
          python3 scripts/reachable.py || exit 1
          grep -E "alpha|beta" notes.txt
          grep -E 'alpha|beta' notes.txt
          echo "${{ github.event.inputs.x || 'none' }}"
          python3 scripts/reachable.py  # never `| tail` here
""") == []


def test_an_echo_into_tee_is_a_report_not_a_swallowed_check(tmp_path):
    """Mutation: `if all(w in _HARMLESS_UPSTREAM ...):` changed to
    `if False:` turns this red."""
    assert _pipe_problems(tmp_path, """
jobs:
  a:
    steps:
      - run: echo "done" | tee -a "$GITHUB_STEP_SUMMARY"
""") == []


def test_a_python_shell_is_not_read_for_pipes(tmp_path):
    """Under `shell: python` a `|` is bitwise-or, not a pipeline.
    Mutation: the non-POSIX-shell skip changed to `if False:` turns this
    red."""
    assert _pipe_problems(tmp_path, """
jobs:
  a:
    steps:
      - shell: python
        run: print(1 | 2)
""") == []


def test_the_block_indicator_is_not_read_as_a_pipe(tmp_path):
    """`run: |` opens a block; it is not a pipeline with an empty upstream.
    Mutation: the `k == 0 and _BLOCK_RX.match(...)` skip changed to
    `if False:` turns this red."""
    assert _pipe_problems(tmp_path, """
jobs:
  a:
    steps:
      - run: |
          python3 scripts/reachable.py
""") == []


def test_the_selfcheck_names_the_pipe_claims(capsys):
    """6.7: the pipe half must be exercised by the embedded selfcheck, or a
    blinded pipe scanner still reports `selfcheck ok`. Mutation: `if
    len(segments) < 2:` changed to `< 99` turns this red."""
    assert csl.selfcheck()
    out = capsys.readouterr().out
    assert "pipe that swallows the exit code rejected" in out, out


# ── R23-10: a windows job's default shell is pwsh, not bash ─────────────────
#
# ci_step_lint ships to every adopter. A step with no `shell:` in a job on a
# windows runner runs under pwsh, and the remedy this guard prints - `set -o
# pipefail` - is a bash command that breaks it. The pair below is the claim:
# the SAME pipe is flagged on linux and left alone on windows.

def _job(runs_on: str) -> str:
    return f"""
jobs:
  a:
    runs-on: {runs_on}
    steps:
      - run: python3 scripts/reachable.py | tee out.log
"""


def test_a_pipe_in_a_linux_job_with_no_shell_key_is_flagged(tmp_path):
    """The known-bad half of the pair. Mutation: `if shell is None and
    _job_runs_on_windows(...)` changed to `if shell is None:` (every
    unshelled step skipped as if windows) turns this red."""
    assert len(_pipe_problems(tmp_path, _job("ubuntu-latest"))) == 1


def test_the_same_pipe_in_a_windows_job_is_not_flagged(tmp_path):
    """The known-good half. Mutation: `return "windows" in named.lower()`
    changed to `return False` (runs-on never read) turns this red."""
    assert _pipe_problems(tmp_path, _job("windows-latest")) == []


def test_a_windows_runner_named_in_a_label_list_is_read(tmp_path):
    """Self-hosted runners name the OS in a label list, flow or block form.
    Mutation: `return "windows" in named.lower()` changed to `return False`
    turns this red."""
    assert _pipe_problems(tmp_path / "flow",
                          _job("[self-hosted, Windows, x64]")) == []
    assert _pipe_problems(tmp_path / "block", """
jobs:
  a:
    runs-on:
      - self-hosted
      - windows
    steps:
      - run: python3 scripts/reachable.py | tee out.log
""") == []


def test_runs_on_after_steps_is_still_read(tmp_path):
    """Job keys are unordered. Mutation: the job-key scan ending at `steps:`
    instead of at the next job header turns this red."""
    assert _pipe_problems(tmp_path, """
jobs:
  a:
    steps:
      - run: python3 scripts/reachable.py | tee out.log
    runs-on: windows-latest
""") == []


def test_a_matrix_expression_names_nothing_and_is_read_as_bash(tmp_path):
    """`${{ matrix.os }}` could be anything; the linux leg still swallows.
    Mutation: the expression strip in _job_runs_on_windows removed, with a
    matrix os expression that spells windows, turns this red."""
    assert len(_pipe_problems(tmp_path, _job("${{ matrix.windows_or_linux }}"))) == 1


def test_one_jobs_runner_does_not_leak_into_the_next_job(tmp_path):
    """Mutation: the next-job-header stop `^ {0,2}\\S` removed turns this
    red (the linux job reads the windows job's runs-on below it)."""
    assert len(_pipe_problems(tmp_path, """
jobs:
  linux:
    steps:
      - run: python3 scripts/reachable.py | tee out.log
  win:
    runs-on: windows-latest
    steps:
      - run: python3 scripts/reachable.py | tee out.log
""")) == 1


def test_an_explicit_pwsh_or_cmd_shell_is_not_read_for_pipes(tmp_path):
    """`set -o pipefail` is not a remedy there. Mutation: `_POSIX_SHELLS`
    lookup replaced by the old set including pwsh and cmd turns this red."""
    for i, shell in enumerate(("pwsh", "powershell", "cmd")):
        assert _pipe_problems(tmp_path / str(i), f"""
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: python3 scripts/reachable.py | tee out.log
        shell: {shell}
""") == [], shell


# ── R24-7: a case pattern's bar and a `[[ ]]` bar are not pipes ─────────────
#
# `case "$X" in a|b) ...` and `[[ "$REF" =~ ^(main|release/.*)$ ]]` are
# ordinary CI shell, and neither holds a pipeline. Each pair below puts a
# real pipe on the same line or the next, so the fix is shown to blank the
# alternation bars and nothing else.

def test_a_one_line_case_pattern_is_not_a_pipe_and_its_clause_pipe_is(tmp_path):
    """Mutation (the line that runs, in swallowing_pipes): `code =
    _mask_alternations(_code_only(raw), cases)` -> `code = _code_only(raw)` -
    the clean half is flagged, red."""
    assert _pipe_problems(tmp_path / "a", """
jobs:
  a:
    steps:
      - run: case "$X" in a|b) echo ab;; esac
""") == []
    piped = _pipe_problems(tmp_path / "b", """
jobs:
  a:
    steps:
      - run: case "$X" in a|b) python3 scripts/reachable.py | tail -5;; esac
""")
    assert len(piped) == 1 and "tail -5" in piped[0], piped


def test_a_multi_line_case_is_not_a_pipe_and_the_pipe_after_esac_is(tmp_path):
    """State crosses lines: the bar on the clause line is a pattern; the
    pipe on the line after `esac` is a pipe again.

    Mutation: `cases[-1] = True` on a clause end -> `pass` - the second
    clause's pattern bar is read as a pipe, red."""
    problems = _pipe_problems(tmp_path, """
jobs:
  a:
    steps:
      - run: |
          case "$KIND" in
            push|pull_request) echo push ;;
            schedule|workflow_dispatch) echo other ;;
            *) exit 1 ;;
          esac
          python3 scripts/reachable.py | tail -5
""")
    assert len(problems) == 1, problems
    assert "ci.yml:11:" in problems[0], problems


def test_a_double_bracket_regex_is_not_a_pipe_and_a_pipe_after_it_is(tmp_path):
    """Mutation (the line that runs): the `[[ ]]` loop's `out[j] = " "` ->
    `pass` - the clean half is flagged, red."""
    assert _pipe_problems(tmp_path / "a", """
jobs:
  a:
    steps:
      - run: |
          if [[ "$REF" =~ ^(main|release/.*)$ ]]; then echo deploy; fi
          if [[ $NAME =~ ^[[:alpha:]]+(a|b)$ ]]; then echo ok; fi
          [[ $A == x || $B == y ]] && echo either
""") == []
    piped = _pipe_problems(tmp_path / "b", """
jobs:
  a:
    steps:
      - run: if [[ "$REF" =~ ^(main|release/.*)$ ]]; then python3 scripts/reachable.py | tail -3; fi
""")
    assert len(piped) == 1 and "tail -3" in piped[0], piped


def test_the_true_positives_survive_the_masking(tmp_path):
    """`|&`, a pipe after pipefail is switched off, and a pipe beside a
    flag spelled `--case` are all still flagged: the masking is narrow.

    Mutation: `_CASE_RX` without its command-position lookbehind (`case` at
    any word boundary) - the subshell's `--case x in` is read as a case, its
    pipe as a pattern bar before the `)`, and blanked; red."""
    problems = _pipe_problems(tmp_path, """
jobs:
  a:
    steps:
      - run: |
          python3 scripts/reachable.py |& tee out.log
          set -o pipefail
          set +o pipefail
          python3 scripts/reachable.py | tail -5
          ( python3 scripts/reachable.py --case x in | tail -2 )
""")
    assert len(problems) == 3, problems
    assert all(f"ci.yml:{n}:" in " ".join(problems) for n in (6, 9, 10)), problems
