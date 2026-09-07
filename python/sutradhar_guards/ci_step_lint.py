# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
#!/usr/bin/env python3
"""Guard: every CI step that runs a script must be able to find it.

This is doctrine 6.7 - *an exit code is not a witness* - applied to CI
wiring. A step whose interpreter exits 2 on file-not-found has made a claim
about a process and none at all about the code it was pointed at, and it
takes every later step in that job down with it. Red, read as "the guard is
failing", when it means "the guard is absent".

*Scar: a CI step ran a guard by a path that did not resolve under that job's
working directory. The interpreter exited 2 on file-not-found, which is a
claim about a process and not about the code under test, and it took every
later step in the job down with it. The guard had never once run, and its red
was read for weeks as "the guard is failing" rather than "the guard is
absent". A neighbouring step survived on the author's attention rather than
on a rule.*

The invariant
-------------
For every ``run:`` step, resolve each ``*.py`` path it names against that
step's effective working directory - the step's own ``working-directory``,
else the job's ``defaults.run.working-directory``, else the repository root.
The file must exist.

This checks REACHABILITY, not correctness: a script that exists can still be
wrong, but one that cannot be found cannot be either. It is the same class as
R16-1, the plugin that resolved `${CLAUDE_PLUGIN_ROOT}/../python` and so
worked in exactly one layout - the one it was built in. Nothing inside that
layout can see it.

What is deliberately NOT flagged, because a guard that cries wolf is muted:

  * **absolute paths** (``/tmp/target/scripts/x.py``). They do not resolve
    against a working directory at all, and they are usually a file an
    earlier step in the same job created. The count of skipped ones is
    printed rather than hidden - an exclusion the operator cannot see is the
    same class of lie 6.7 is about.
  * **a bare ``foo.py``** with no directory separator, which is ambiguous.
  * anything not ending in ``.py``.

Do not point this at a workflow TEMPLATE. ``ci/guards.yml`` in this
repository names ``scripts/swallow_lint.py``, which resolves in the tree
``bootstrap.sh`` builds and not in this one; running the guard over a
template reports the template's whole point as a finding.

Usage:
    python ci_step_lint.py .                 # -> <repo>/.github/workflows
    python ci_step_lint.py .github/workflows
    python ci_step_lint.py path/to/one.yml
    python ci_step_lint.py --selfcheck

Exit 0 reachable, 1 a step cannot find its script, 2 the check could not run
(no argument, an unknown flag, a directory with no workflows in it). 2 is not
a pass: "could not measure" and "did not fail" are different answers (2.9).

The YAML is read with a hand-rolled indentation scan and no third-party
parser, so the guard runs in any environment a workflow itself would.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

#: Any token ending in .py that sits under a directory-ish prefix.
#: Deliberately narrow: a bare `foo.py` with no separator is ambiguous, and
#: quoting it here would invent findings.
_SCRIPT_RX = re.compile(r"(?<![\w./-])((?:\.\./)*[\w./-]+/[\w.-]+\.py)")


def steps(text: str):
    """Yield ``(line_no, effective_working_dir, run_body)`` per ``run:`` step.

    A hand-rolled indentation scan rather than a YAML parse, so this has no
    dependency and runs wherever a workflow does. It tracks which job and
    step each line belongs to by indentation alone.
    """
    job_wd: dict = {}
    cur_job = None
    in_defaults = False
    step_wd = None
    lines = text.splitlines()

    for i, raw in enumerate(lines, 1):
        if re.match(r"^  [\w-]+:\s*$", raw):
            cur_job = raw.strip().rstrip(":")
            in_defaults = False
            step_wd = None
            continue
        if cur_job and re.match(r"^    defaults:\s*$", raw):
            in_defaults = True
            continue
        m = re.match(r"^\s*working-directory:\s*(\S+)", raw)
        if m:
            if in_defaults:
                job_wd[cur_job] = m.group(1).strip("'\"")
            else:
                step_wd = m.group(1).strip("'\"")
            continue
        if re.match(r"^      - ", raw):
            step_wd = None
            in_defaults = False
        # `- run: ...` is as common as a `- name:` followed by `run:`, and a
        # scanner that saw only the second form would pass whole jobs without
        # reading a line of them - the guard absent, reporting green.
        m = re.match(r"^\s*(?:-\s+)?run:\s*(.*)$", raw)
        if not m or in_defaults:
            # `defaults: run: working-directory:` carries a `run:` key that is
            # not a step. Reading it as one yields a phantom step whose body
            # is the working-directory line - harmless today, and exactly the
            # kind of miscount that makes a later assertion about the scanner
            # unreadable.
            continue
        body = [m.group(1)]
        if m.group(1).strip() in ("|", ">", "|-", ">-", ""):
            indent = len(raw) - len(raw.lstrip())
            for nxt in lines[i:]:
                if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= indent:
                    break
                body.append(nxt)
        yield i, step_wd or job_wd.get(cur_job) or ".", "\n".join(body)


def audit(path: Path, repo_root: Path) -> tuple:
    """(problems, scripts checked, absolute paths skipped) for one workflow."""
    problems: list = []
    checked = 0
    skipped_absolute = 0
    for line_no, wd, body in steps(path.read_text(encoding="utf-8",
                                                  errors="replace")):
        base = repo_root if wd == "." else (repo_root / wd)
        for ref in _SCRIPT_RX.findall(body):
            if ref.startswith("/"):
                skipped_absolute += 1
                continue
            checked += 1
            if (base / ref).exists():
                continue
            problems.append(
                f"{path.name}:{line_no}: step runs {ref!r} from "
                f"working-directory {wd!r}, resolving to {base / ref}, which "
                f"does not exist. The step exits non-zero on file-not-found, "
                f"which reads as a FINDING and is an absent check - and it "
                f"takes every later step in the job with it. Add "
                f"`working-directory: .` or fix the path."
            )
    return problems, checked, skipped_absolute


# ── selfcheck ───────────────────────────────────────────────────────────────

_GOOD = """
jobs:
  a:
    defaults:
      run:
        working-directory: backend
    steps:
      - name: ok because it opts out
        working-directory: .
        run: python3 scripts/reachable.py
"""

_BAD = """
jobs:
  a:
    defaults:
      run:
        working-directory: backend
    steps:
      - name: cannot find its script
        run: python3 scripts/reachable.py
"""

_STEP_LEVEL = """
jobs:
  a:
    steps:
      - name: a step that names its own directory
        working-directory: backend
        run: python3 scripts/reachable.py
"""

_ABSOLUTE = """
jobs:
  a:
    steps:
      - name: a path an earlier step created
        run: python3 /tmp/target/scripts/reachable.py
"""

_INLINE = """
jobs:
  a:
    steps:
      - run: |
          echo hello
          python3 scripts/reachable.py
"""


def selfcheck() -> bool:
    """Known-good and known-bad for every claim, because an exit code is
    evidence only in pairs (6.7)."""
    import tempfile

    problems: list = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "scripts").mkdir()
        (root / "scripts" / "reachable.py").write_text("x = 1\n")
        wf = root / "wf.yml"

        for label, body, want_flagged in (
            ("a job working-directory the step does not opt out of", _BAD, True),
            ("`working-directory: .` on the step", _GOOD, False),
            ("a step-level working-directory that moves the path", _STEP_LEVEL,
             True),
            ("an absolute path an earlier step creates", _ABSOLUTE, False),
        ):
            wf.write_text(body)
            found, checked, skipped = audit(wf, root)
            if bool(found) != want_flagged:
                problems.append(
                    f"{label}: {'flagged' if found else 'accepted'}, expected "
                    f"{'flagged' if want_flagged else 'accepted'}"
                )
            if body is _ABSOLUTE and (skipped != 1 or checked != 0):
                problems.append(
                    f"an absolute path was counted as checked rather than "
                    f"skipped: checked={checked} skipped={skipped}"
                )

        # The parser must actually see the step. A regex that matched nothing
        # would accept every workflow and report the same green. Shapes are
        # checked BEFORE they are indexed: a selfcheck that raises has
        # reported nothing and takes the rest of the run with it (6.11).
        bad_steps = list(steps(_BAD))
        good_steps = list(steps(_GOOD))
        inline = list(steps(_INLINE))
        if len(bad_steps) != 1:
            problems.append(
                f"the step scanner found {len(bad_steps)} `run:` step(s) in a "
                f"workflow with exactly one"
            )
        elif bad_steps[0][1] != "backend":
            problems.append("the job's defaults.run.working-directory was lost")
        if len(good_steps) != 1:
            problems.append(
                f"the step scanner found {len(good_steps)} step(s) in the "
                f"opt-out workflow"
            )
        elif good_steps[0][1] != ".":
            problems.append("a step-level `working-directory: .` did not win")
        if len(inline) != 1 or "reachable.py" not in inline[0][2]:
            problems.append(
                f"the `- run:` inline form was not read as a step: {inline}"
            )

    for p in problems:
        print(f"[ci-step-lint] SELFCHECK FAILED: {p}")
    if not problems:
        print(
            "[ci-step-lint] selfcheck ok: unreachable script rejected, "
            "`working-directory: .` accepted, step-level working-directory "
            "applied, absolute path skipped and counted, job defaults read, "
            "`- run:` inline form read as a step"
        )
    return not problems


# ── CLI ─────────────────────────────────────────────────────────────────────

_KNOWN_FLAGS = {"--selfcheck", "--repo-root", "--help", "-h"}

_HELP = (
    "usage: ci_step_lint.py [PATH] [--repo-root DIR] [--selfcheck]\n"
    "\n"
    "PATH is a workflow file, a directory of workflows, or a repository root\n"
    "(in which case .github/workflows inside it is used).\n"
)


def _resolve(target: Path, explicit_root: "Path | None") -> tuple:
    """(workflow files, repo root, how the root was decided)."""
    target = target.resolve()
    if target.is_file():
        files = [target]
        wf_dir = target.parent
    elif (target / ".github" / "workflows").is_dir():
        wf_dir = target / ".github" / "workflows"
        files = sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml"))
    elif target.is_dir():
        wf_dir = target
        files = sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml"))
    else:
        return [], target, "no such path"

    if explicit_root is not None:
        return files, explicit_root.resolve(), "--repo-root"
    # The paths in a workflow resolve from the checkout root, which is the
    # directory holding `.github`. Walk up for it; say so either way, because
    # a root guessed silently makes every verdict below unreadable.
    for parent in [wf_dir] + list(wf_dir.parents):
        if (parent / ".github").is_dir():
            return files, parent, f"the directory holding .github ({parent})"
    return files, Path.cwd(), f"the working directory ({Path.cwd()})"


def main(argv: "list | None" = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or "--selfcheck" in argv:
        return 0 if selfcheck() else 1
    if "-h" in argv or "--help" in argv:
        print(_HELP)
        print(__doc__)
        return 0

    explicit_root = None
    positional: list = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--repo-root":
            explicit_root = Path(argv[i + 1]); i += 2
        elif a.startswith("-"):
            # Refused, never ignored: a dropped flag makes exit 0 a statement
            # about the import and nothing else (R17-2).
            if a not in _KNOWN_FLAGS:
                print(f"[ci-step-lint] unknown flag: {a}", file=sys.stderr)
                return 2
            i += 1
        else:
            positional.append(Path(a)); i += 1

    if len(positional) != 1:
        print(
            "[ci-step-lint] name exactly one workflow file, workflow "
            "directory, or repository root; nothing was checked",
            file=sys.stderr,
        )
        return 2

    if not selfcheck():
        return 1

    files, repo_root, how = _resolve(positional[0], explicit_root)
    if not files:
        print(
            f"[ci-step-lint] no workflow found at {positional[0]} - nothing "
            f"was checked, and that is itself suspicious. This is not a pass "
            f"(2.9).",
            file=sys.stderr,
        )
        return 2

    print(f"[ci-step-lint] repo root: {repo_root} (from {how})")
    problems: list = []
    checked = skipped = 0
    for wf in files:
        p, c, s = audit(wf, repo_root)
        problems += p
        checked += c
        skipped += s

    if skipped:
        print(
            f"[ci-step-lint] skipped {skipped} absolute path(s): they do not "
            f"resolve against a working directory and are usually written by "
            f"an earlier step in the same job"
        )
    for p in problems:
        print(f"FAIL {p}", file=sys.stderr)
    if problems:
        return 1
    print(
        f"[ci-step-lint] OK - {len(files)} workflow(s), {checked} script "
        f"reference(s), every one reachable from its step's working directory"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
