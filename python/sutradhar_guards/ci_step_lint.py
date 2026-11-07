#!/usr/bin/env python3
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Guard: every CI step that runs a script must be able to find it, and no
step may pipe its exit code away.

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

The second invariant: a pipe must not swallow an exit code (6.3)
------------------------------------------------------------------
A ``run:`` step's status is its shell's status, and without ``pipefail`` a
pipeline's status is its LAST command's. ``pytest | tail -5`` exits with
tail's 0 whatever pytest said, so a failed build reads as success. GitHub
runs a step with no ``shell:`` key as ``bash -e {0}`` - ``-e`` without
``pipefail`` - so the default is the swallowing one.

*Scar (6.3): ``| tail`` reported a failed production build as success during
a drill. No guard checked a workflow for it; the rule was convention-only
(R22-3).*

A pipe is flagged unless one of these holds, each checked, none guessed:

  * ``set -o pipefail`` (or a ``set -...o pipefail`` cluster) runs earlier
    in the same step;
  * the effective shell - the step's ``shell:``, else the job's
    ``defaults.run.shell``, else the workflow's - is plain ``bash`` (which
    GitHub expands to ``bash --noprofile --norc -eo pipefail {0}``) or names
    ``pipefail`` itself;
  * every command upstream of the last ``|`` is ``echo`` or ``printf``,
    which have no build status to lose (``echo x | tee -a "$GITHUB_STEP_SUMMARY"``
    is a report, not a swallowed check).

``||`` is not a pipe, and ``|`` inside quotes, ``${{ }}`` expressions, or a
comment is not read as one. Nor is the alternation bar of a ``case`` pattern
list (``a|b) ...;;``) or any ``|`` between ``[[`` and ``]]``, ``=~`` regexes
included (R24-7): neither is a pipeline in bash, and both are ordinary CI
shell. A real pipe in the same line - in a case clause's command, after the
``]]`` - is still read. Only POSIX shells (bash, sh, zsh) are read for
pipes at all. pwsh, powershell and cmd have a different exit-code model and
the remedy printed here (``set -o pipefail``) is a bash command that breaks
them; ``python`` or a custom interpreter reads ``|`` as an operator. A step
with no ``shell:`` anywhere, in a job whose ``runs-on`` names windows, runs
under pwsh by GitHub's default and is skipped (R23-10). A ``runs-on`` that
is an expression (``${{ matrix.os }}``) names nothing and is read as bash.

Do not point this at a workflow TEMPLATE. ``ci/guards.yml`` in this
repository names ``scripts/swallow_lint.py``, which resolves in the tree
``bootstrap.sh`` builds and not in this one; running the guard over a
template reports the template's whole point as a finding.

Usage:
    python ci_step_lint.py .                 # -> <repo>/.github/workflows
    python ci_step_lint.py .github/workflows
    python ci_step_lint.py path/to/one.yml
    python ci_step_lint.py --selfcheck

Exit 0 reachable and no swallowing pipe, 1 a step cannot find its script or
pipes away its exit code, 2 the check could not run
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


# ── 6.3: a pipe that swallows the exit code ─────────────────────────────────

#: A single `|` - not `||`. `|&` is a pipe too (stderr rides along).
_PIPE_RX = re.compile(r"(?<!\|)\|(?!\|)")
#: `set -o pipefail`, `set -eo pipefail`, `set -euo pipefail`, ...
_PIPEFAIL_ON_RX = re.compile(r"\bset\s+-[A-Za-z]*o\s+pipefail\b")
_PIPEFAIL_OFF_RX = re.compile(r"\bset\s+\+[A-Za-z]*o\s+pipefail\b")
#: A block-scalar indicator on the `run:` line itself (`|`, `>-`, `|+`, `|2`).
_BLOCK_RX = re.compile(r"^[|>][+-]?\d*[+-]?$")
#: POSIX shells, the only ones whose pipe status `set -o pipefail` governs.
#: pwsh, powershell and cmd have pipelines too, but a different exit-code
#: model, and the remedy this guard prints is a bash command that breaks
#: them (R23-10). `python {0}` and custom interpreters: `|` is an operator.
_POSIX_SHELLS = {"bash", "sh", "zsh"}
#: Upstream commands with no build status to lose.
_HARMLESS_UPSTREAM = {"echo", "printf"}


def _code_only(line: str) -> str:
    """The line with expressions, quoted strings, and a comment removed, so
    a `|` inside any of them is not read as a pipe."""
    s = re.sub(r"\$\{\{.*?\}\}", " ", line)
    s = re.sub(r"'[^']*'", "''", s)
    s = re.sub(r'"(?:[^"\\]|\\.)*"', '""', s)
    return re.sub(r"(^|\s)#.*$", r"\1", s)


#: `[[ ... ]]` - opened by `[[` and a blank, closed by a `]]` that stands as
#: its own word, so the `]]` of a bracket class (`[[:alpha:]]`) does not end
#: it early.
_DBRACKET_RX = re.compile(r"\[\[\s.*?\s\]\](?=$|[\s;&|)])")
#: `case WORD in` in command position (line start, or after a separator or
#: an opening keyword) - not `--case x in` as a flag's value.
_CASE_RX = re.compile(r"(?:^|(?<=[\s;&|({]))case\s+\S+\s+in(?=$|[\s;])")
#: The end of a case clause: `;;`, `;&` or `;;&`.
_CLAUSE_END_RX = re.compile(r";;&?|;&")
#: `esac` as a word in command position.
_ESAC_RX = re.compile(r"(?:^|(?<=[\s;&]))esac(?=$|[\s;&|)])")


def _mask_alternations(code: str, cases: list) -> str:
    """``code`` with every `|` that is not a pipeline blanked: those inside
    `[[ ... ]]`, and the alternation bars of a case pattern list.

    ``cases`` carries state from line to line of one step: one entry per
    open `case`, True while the next thing is a pattern list (after `in`,
    or after `;;`). A pattern list runs to its closing `)` at paren depth
    zero; if a line holds no such `)`, nothing on it is blanked - reading
    a real pipe as a pattern would be the false negative, and this errs the
    other way.
    """
    out = list(code)
    for m in _DBRACKET_RX.finditer(code):
        for j in range(m.start(), m.end()):
            if out[j] == "|":
                out[j] = " "
    i, n = 0, len(code)
    while i < n:
        if cases and cases[-1]:
            while i < n and code[i].isspace():
                i += 1
            if i >= n:
                break
            m = _ESAC_RX.match(code, i)
            if m:
                cases.pop()
                i = m.end()
                continue
            k = i + 1 if code[i] == "(" else i
            depth, close = 0, None
            while k < n:
                if code[k] == "(":
                    depth += 1
                elif code[k] == ")":
                    if depth == 0:
                        close = k
                        break
                    depth -= 1
                k += 1
            if close is None:
                break
            for j in range(i, close):
                if out[j] == "|":
                    out[j] = " "
            cases[-1] = False
            i = close + 1
            continue
        hits = [(m.start(), kind, m) for kind, m in (
            ("case", _CASE_RX.search(code, i)),
            ("end", _CLAUSE_END_RX.search(code, i) if cases else None),
            ("esac", _ESAC_RX.search(code, i) if cases else None),
        ) if m]
        if not hits:
            break
        _, kind, m = min(hits, key=lambda h: h[0])
        if kind == "case":
            cases.append(True)
        elif kind == "end":
            cases[-1] = True
        else:
            cases.pop()
        i = m.end()
    return "".join(out)


def _key_value(line: str, key: str) -> "str | None":
    m = re.match(rf"^\s*(?:-\s+)?{key}:\s*(.+?)\s*$", line)
    return m.group(1).strip("'\"") if m else None


def _effective_shell(lines: list, run_idx: int) -> "str | None":
    """The shell a `run:` step at ``lines[run_idx]`` executes under: the
    step's own `shell:` (in any key order within the step), else the job's
    `defaults.run.shell`, else the workflow's. None when nothing names one,
    which on GitHub means `bash -e {0}` - no pipefail."""
    run_line = lines[run_idx]
    key_indent = len(run_line) - len(run_line.lstrip())
    start = dash = None
    m = re.match(r"^(\s*)-\s+", run_line)
    if m:
        start, dash = run_idx, len(m.group(1))
    else:
        for j in range(run_idx - 1, -1, -1):
            mm = re.match(r"^(\s*)-\s+", lines[j])
            if mm and len(mm.group(1)) < key_indent:
                start, dash = j, len(mm.group(1))
                break
    if start is not None:
        step_keys = dash + 2
        for j in range(start, len(lines)):
            ln = lines[j]
            ind = len(ln) - len(ln.lstrip())
            if j > start and ln.strip() and ind <= dash:
                break
            if j == start or ind == step_keys:
                v = _key_value(ln, "shell")
                if v:
                    return v
        # The job: the nearest job header above, read up to its `steps:`.
        for j in range(start, -1, -1):
            if re.match(r"^  [\w-]+:\s*$", lines[j]):
                for k in range(j + 1, start):
                    if re.match(r"^\s+steps:\s*$", lines[k]):
                        break
                    v = _key_value(lines[k], "shell")
                    if v:
                        return v
                break
    # The workflow: a `defaults.run.shell` before `jobs:`.
    for ln in lines:
        if re.match(r"^jobs:\s*$", ln):
            break
        v = _key_value(ln, "shell")
        if v and ln.startswith(" "):
            return v
    return None


def _job_runs_on_windows(lines: list, run_idx: int) -> bool:
    """True when the job holding ``lines[run_idx]`` names windows in its
    `runs-on` (scalar, flow list, or block list). GitHub's default shell
    there is pwsh, not bash. An expression (`${{ matrix.os }}`) names
    nothing and reads False: the linux leg of a matrix still swallows."""
    for j in range(run_idx, -1, -1):
        if re.match(r"^  [\w-]+:\s*$", lines[j]):
            # A job key sits at indent 4 and may follow `steps:` (key order
            # is free); the next job header, at indent 2, ends the job.
            for k in range(j + 1, len(lines)):
                ln = lines[k]
                if re.match(r"^ {0,2}\S", ln):
                    return False
                m = re.match(r"^    runs-on:\s*(.*)$", ln)
                if not m:
                    continue
                value = [m.group(1)]
                for nxt in lines[k + 1:]:
                    if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= 4:
                        break
                    value.append(nxt)
                named = re.sub(r"\$\{\{.*?\}\}", " ", "\n".join(value))
                named = re.sub(r"(^|\s)#[^\n]*", " ", named, flags=re.M)
                return "windows" in named.lower()
            return False
    return False


def _shell_sets_pipefail(shell: "str | None") -> bool:
    if shell is None:
        return False
    # GitHub's template for a bare `bash` is `bash --noprofile --norc -eo
    # pipefail {0}`; `bash {0}` or `sh` get no such thing.
    return shell.strip() == "bash" or "pipefail" in shell


def swallowing_pipes(text: str) -> list:
    """``[(line_no, line)]`` for every pipe in a `run:` step that replaces
    the step's exit code with its last command's."""
    lines = text.splitlines()
    found: list = []
    for line_no, _wd, body in steps(text):
        shell = _effective_shell(lines, line_no - 1)
        if shell is None and _job_runs_on_windows(lines, line_no - 1):
            continue  # the runner's default is pwsh (R23-10)
        if shell is not None and shell.split()[0] not in _POSIX_SHELLS:
            continue
        if _shell_sets_pipefail(shell):
            continue
        armed = False
        cases: list = []
        for k, raw in enumerate(body.split("\n")):
            if k == 0 and _BLOCK_RX.match(raw.strip()):
                continue
            code = _mask_alternations(_code_only(raw), cases)
            if _PIPEFAIL_OFF_RX.search(code):
                armed = False
            if _PIPEFAIL_ON_RX.search(code):
                armed = True
            if armed:
                continue
            segments = _PIPE_RX.split(code)
            if len(segments) < 2:
                continue
            upstream = [s.split()[0] if s.split() else "" for s in segments[:-1]]
            if all(w in _HARMLESS_UPSTREAM for w in upstream):
                continue
            found.append((line_no + k, raw.strip()))
    return found


def audit(path: Path, repo_root: Path) -> tuple:
    """(problems, scripts checked, absolute paths skipped) for one workflow."""
    problems: list = []
    checked = 0
    skipped_absolute = 0
    text = path.read_text(encoding="utf-8", errors="replace")
    for line_no, line in swallowing_pipes(text):
        problems.append(
            f"{path.name}:{line_no}: `{line}` pipes a command's exit code "
            f"away - the step reports the LAST command's status, so a failed "
            f"build or test reads as success (6.3). Add `set -o pipefail` "
            f"before it, or give the step `shell: bash` (GitHub runs that "
            f"with -o pipefail)."
        )
    for line_no, wd, body in steps(text):
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


_PIPE_BAD = """
jobs:
  a:
    steps:
      - run: python3 scripts/reachable.py | tail -5
"""

_PIPE_PIPEFAIL = """
jobs:
  a:
    steps:
      - run: |
          set -o pipefail
          python3 scripts/reachable.py | tail -5
"""

_PIPE_SHELL_BASH = """
jobs:
  a:
    steps:
      - run: python3 scripts/reachable.py | tail -5
        shell: bash
"""


_PIPE_LINUX_JOB = """
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: python3 scripts/reachable.py | tee out.log
"""

_PIPE_WINDOWS_JOB = """
jobs:
  a:
    runs-on: windows-latest
    steps:
      - run: python3 scripts/reachable.py | tee out.log
"""


_PIPE_CASE_AND_TEST = """
jobs:
  a:
    steps:
      - run: |
          case "$X" in a|b) echo ab;; esac
          case "$KIND" in
            push|pull_request) python3 scripts/reachable.py ;;
            *) exit 1 ;;
          esac
          if [[ "$REF" =~ ^(main|release/.*)$ ]]; then python3 scripts/reachable.py; fi
"""

_PIPE_CASE_AND_TEST_PIPED = """
jobs:
  a:
    steps:
      - run: |
          case "$KIND" in
            push|pull_request) python3 scripts/reachable.py | tail -5 ;;
          esac
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
            ("a build piped through tail with no pipefail", _PIPE_BAD, True),
            ("the same pipe after `set -o pipefail`", _PIPE_PIPEFAIL, False),
            ("the same pipe under `shell: bash`", _PIPE_SHELL_BASH, False),
            ("a pipe in a linux job with no shell key", _PIPE_LINUX_JOB, True),
            ("the same pipe in a windows job, pwsh by default",
             _PIPE_WINDOWS_JOB, False),
            ("case pattern alternations and a `[[ =~ ]]` regex, no pipe",
             _PIPE_CASE_AND_TEST, False),
            ("a real pipe in a case clause's command", _PIPE_CASE_AND_TEST_PIPED,
             True),
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
            "`- run:` inline form read as a step, a pipe that swallows the "
            "exit code rejected, the same pipe accepted under pipefail and "
            "under `shell: bash`, a linux job's pipe rejected and the same "
            "pipe in a windows job (pwsh by default) accepted, case-pattern "
            "and `[[ =~ ]]` alternation bars accepted and a real pipe in a "
            "case clause rejected"
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
