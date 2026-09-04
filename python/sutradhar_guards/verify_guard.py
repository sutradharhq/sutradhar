"""verify_guard - mechanise doctrine 2.2: a guard must be SHOWN to fail.

Doctrine 2.2 says: revert the fix, and the test must go red. A guard never
shown to fail is decoration. Until now that rule lived entirely on the
honour system - the one rule in this framework with the worst
consequence-to-enforcement ratio.

*Scar: a tenant-isolation fix shipped tested-and-half-dead for a week. Its
tests passed because they set internal state by hand instead of exercising
the real seam; the production path ran the guard in a thread whose context
write was discarded. Reverting the fix would not have reddened a single
test, and nobody ran that experiment.*

This tool runs that experiment mechanically:

  1. check out the fix commit in a throwaway worktree;
  2. run the guard there - it must be GREEN (if not, the premise is broken
     and we say so rather than reporting a result: doctrine 6.4);
  3. revert ONLY the production-code half of the commit, keeping the test
     half;
  4. run the guard again - it MUST go red. If it stays green, the guard is
     decoration and this exits nonzero.

The guard command is yours (`--guard-cmd "pytest tests/test_x.py::test_y"`,
`"go test ./billing/..."`, `"npx cypress run --spec ..."`), so the tool is
stack-agnostic; it only needs Python to run, not to verify.

    python verify_guard.py --guard-cmd "python -m pytest tests/test_tenant.py"
    python verify_guard.py --commit a1b2c3d --guard-cmd "npm test -- cart" \
        --link node_modules

**A guard command is one program with arguments, and it is NOT run through
a shell.** It is `shlex`-split into an argv list and spawned directly; the
one prefix that survives is `cd <dir> && ...`, which sets the working
directory and must resolve inside the worktree. A pipe, a redirection, `;`,
`&&` past that prefix, a backtick or `$(...)` is REFUSED, and a refusal
exits 2 (INCONCLUSIVE) because no guard ran. Put anything more complex in a
script and name the script.

That is a smaller surface on purpose. This tool runs the command it is
handed, as the user running it, and the string can arrive from somewhere
that is not a person typing - an MCP tool argument written by a model, a
`Guard-cmd:` trailer on a commit somebody else authored. Through a shell,
"the guard command" and "an arbitrary shell" were the same surface (R16-3).

Exit codes are a deliberate tri-state - "I could not tell" is never
reported as "pass":

    0  VERIFIED      the guard went red without the fix. It is real.
    1  DECORATION    the guard passed without the fix. It proves nothing.
    2  INCONCLUSIVE  premise broken, timeout, merge commit, bad usage, or a
                     guard command this tool refused to run.

Honest limits, stated plainly:

  - This mechanises the REVERT half of doctrine 2.2. The "weaken the seam,
    behavioural cases must go red" half is mutation testing and is not
    implemented here; `--guard-cmd` pointed at a behavioural suite plus a
    hand-weakened seam remains a manual exercise.
  - A guard can go red for the wrong reason (the revert breaks an import
    and nothing even loads). That is a weaker proof than a discriminating
    assertion, so it is reported as VERIFIED (weak) rather than silently
    counted as a clean pass.
  - Reverting is per-file, not per-hunk. A commit that mixes a fix and an
    unrelated change in one file reverts both; split your commits (or pass
    `--code` explicitly) if that matters.
"""
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

VERIFIED = "VERIFIED"
DECORATION = "DECORATION"
INCONCLUSIVE = "INCONCLUSIVE"

EXIT = {VERIFIED: 0, DECORATION: 1, INCONCLUSIVE: 2}

# Path shapes that are guard/test artifacts rather than production code.
# Deliberately generous: mis-classifying a test as code would revert the
# guard along with the fix and make every verdict meaningless, so the
# failure mode of this list is biased towards "keep it".
GUARD_DIR_SEGMENTS = {
    "test", "tests", "__tests__", "spec", "specs", "e2e", "cypress",
    "testing", "it", "integration_tests", "featuretests",
}
GUARD_FILE_GLOBS = (
    "test_*.py", "*_test.py", "conftest.py",
    "*_test.go", "*_test.rb", "*_spec.rb",
    "*.test.*", "*.spec.*", "*.cy.*",
    "*Test.java", "*Tests.java", "*Test.kt", "*Tests.cs", "*_test.rs",
    "*baseline*.json", "*golden*.json",
)

# Prose and media: reverting them cannot change what the guard observes, so
# a commit whose whole non-test half is inert has no fix to revert and gets
# INCONCLUSIVE rather than a verdict. Config formats (.yaml, .json, .toml,
# .env) are deliberately NOT inert - a wrong timeout in a config file is a
# real defect and its fix is a real fix.
INERT_SUFFIXES = {
    ".md", ".rst", ".adoc", ".txt", ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".webp", ".ico", ".pdf", ".mp4", ".woff", ".woff2",
}
INERT_NAMES = {
    "LICENSE", "LICENCE", "NOTICE", "AUTHORS", "CONTRIBUTORS", "CODEOWNERS",
    ".gitignore", ".gitattributes", ".editorconfig",
}
# ...except the .txt files that pin what actually gets installed.
NOT_INERT_GLOBS = ("requirements*.txt", "constraints*.txt")


@dataclass
class Result:
    verdict: str
    reason: str
    commit: str = ""
    code_files: list[str] = field(default_factory=list)
    guard_files: list[str] = field(default_factory=list)
    inert_files: list[str] = field(default_factory=list)
    baseline_exit: int | None = None
    reverted_exit: int | None = None
    weak: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return EXIT[self.verdict]

    def to_json(self) -> str:
        return json.dumps({
            "verdict": self.verdict,
            "exit_code": self.exit_code,
            "reason": self.reason,
            "commit": self.commit,
            "code_files": self.code_files,
            "guard_files": self.guard_files,
            "inert_files": self.inert_files,
            "baseline_exit": self.baseline_exit,
            "reverted_exit": self.reverted_exit,
            "weak_proof": self.weak,
            "warnings": self.warnings,
        }, indent=2)


# ── classification ──────────────────────────────────────────────────────────

def is_guard_path(path: str) -> bool:
    """True if `path` looks like a test/guard artifact rather than production
    code. Pure and cheap so it can be self-checked on every invocation."""
    p = Path(path)
    if any(seg.lower() in GUARD_DIR_SEGMENTS for seg in p.parts[:-1]):
        return True
    name = p.name
    return any(fnmatch.fnmatch(name, g) for g in GUARD_FILE_GLOBS)


def is_inert_path(path: str) -> bool:
    """True if `path` is prose or media - revertible, but incapable of
    changing what any guard observes."""
    p = Path(path)
    if any(fnmatch.fnmatch(p.name, g) for g in NOT_INERT_GLOBS):
        return False
    return p.name in INERT_NAMES or p.suffix.lower() in INERT_SUFFIXES


def classify(
    changed: list[str],
    code_patterns: list[str] | None = None,
    guard_patterns: list[str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Split a commit's changed files into (code, guard_to_keep, inert).

    Explicit patterns win over the heuristic; `--code` is checked first so
    that naming a file as code overrides a test-looking or prose-looking
    path."""
    code: list[str] = []
    guard: list[str] = []
    inert: list[str] = []
    for path in changed:
        if code_patterns and _matches(path, code_patterns):
            code.append(path)
        elif guard_patterns and _matches(path, guard_patterns):
            guard.append(path)
        elif code_patterns and not guard_patterns:
            # An explicit --code list is exhaustive: everything else is kept.
            guard.append(path)
        elif is_guard_path(path):
            guard.append(path)
        elif is_inert_path(path):
            inert.append(path)
        else:
            code.append(path)
    return code, guard, inert


def _matches(path: str, patterns: list[str]) -> bool:
    return any(
        fnmatch.fnmatch(path, pat) or path == pat or path.startswith(pat.rstrip("/") + "/")
        for pat in patterns
    )


# ── git plumbing ────────────────────────────────────────────────────────────

class GitError(RuntimeError):
    pass


def _git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def changed_files(repo: Path, commit: str) -> list[str]:
    out = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", commit)
    return [line for line in out.splitlines() if line.strip()]


def parents_of(repo: Path, commit: str) -> list[str]:
    line = _git(repo, "rev-list", "--parents", "-n", "1", commit).strip().split()
    return line[1:]


def exists_at(repo: Path, rev: str, path: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{rev}:{path}"],
        capture_output=True, text=True,
    )
    return proc.returncode == 0


# ── what a guard command is allowed to be ───────────────────────────────────
#
# This tool is handed a command by whoever is asking for a verification, and
# it runs that command on the machine it is running on. When it ran the
# string through a shell, "the command" and "an arbitrary shell" were the
# same surface, and every caller that could reach a guard command - an MCP
# tool argument written by a model, a `Guard-cmd:` trailer on a commit
# somebody else authored - was that shell. So the string is parsed here into
# an argv list, and what the parser cannot express cannot happen (1.2).
#
# Exactly one convenience survives, because every `Guard-cmd:` trailer in
# this repository's history uses it: a leading `cd <dir> &&` sets the working
# directory, and `<dir>` must resolve inside the worktree.

_OPERATOR_CHARS = "|;&<>()"
_SUBSTITUTION = ("`", "$")

_HOW_A_GUARD_COMMAND_LOOKS = (
    "A guard command is one program with arguments, optionally prefixed by "
    "`cd <dir> &&`; it is not run through a shell, so pipes, redirections, "
    "chaining, backticks, $(...) and variable expansion have no meaning here "
    "- put anything more complex in a script and name the script."
)


class GuardNotRun(Exception):
    """No guard process ran, for any reason. Never a verdict.

    Every subclass reaches the CLI as INCONCLUSIVE (exit 2), because nothing
    was measured (2.9). It is never VERIFIED, never DECORATION, and never
    exit 0.
    """


class GuardCommandRefused(GuardNotRun, ValueError):
    """The command is not one program with arguments, so it was not run."""


class GuardSpawnFailed(GuardNotRun):
    """The program named could not be started."""


def _refuse(cmd: str, why: str) -> GuardCommandRefused:
    return GuardCommandRefused(
        f"refusing to run {cmd!r}: {why}. {_HOW_A_GUARD_COMMAND_LOOKS}")


def _operators_in(cmd: str) -> list[str]:
    """Shell operators appearing OUTSIDE quotes, in order.

    `shlex.split` alone is not enough: it splits on whitespace, so
    `pytest; rm -rf /` comes back as the single token `pytest;` and an
    exact-token comparison misses the `;` entirely. `punctuation_chars`
    makes the lexer separate `| ; & < > ( )` the way a shell would, which
    is what lets a quoted `-k "a|b"` stay an argument while a bare `|` is
    seen for what it is.
    """
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    return [t for t in lex if t and all(ch in _OPERATOR_CHARS for ch in t)]


def parse_guard_cmd(cmd: str) -> tuple[list[str], str | None]:
    """(argv, working directory relative to the worktree or None).

    Refuses anything that only a shell could interpret. The refusal is the
    product here: this function's job is not to be permissive, it is to make
    "the guard command" a strictly smaller thing than "a command line".
    """
    for mark in _SUBSTITUTION:
        if mark in cmd:
            raise _refuse(cmd, f"it contains {mark!r}: command substitution and "
                               f"variable expansion need a shell, and passing "
                               f"the text through literally instead would run a "
                               f"different check than the one written")
    try:
        tokens = shlex.split(cmd)
        operators = _operators_in(cmd)
    except ValueError as exc:
        raise _refuse(cmd, f"it does not tokenise ({type(exc).__name__}: {exc})")
    if not tokens:
        raise _refuse(cmd, "it is empty, so there is no program to run")

    subdir: str | None = None
    allowed: list[str] = []
    if tokens[0] == "cd":
        if len(tokens) < 4 or tokens[2] != "&&":
            raise _refuse(cmd, "a leading `cd` is only allowed as the exact "
                               "prefix `cd <dir> && <program> [args]`")
        subdir = tokens[1]
        if Path(subdir).is_absolute() or ".." in Path(subdir).parts:
            raise _refuse(cmd, f"the `cd` target {subdir!r} is absolute or "
                               f"climbs out of the worktree; it must name a "
                               f"directory inside the commit under test")
        tokens = tokens[3:]
        allowed = ["&&"]

    if operators != allowed:
        stray = next((op for op in operators if op not in allowed), operators[0])
        raise _refuse(cmd, f"{stray!r} is a shell operator and there is no shell")
    if "cd" in tokens:
        raise _refuse(cmd, "`cd` appears somewhere other than as the single "
                           "permitted `cd <dir> &&` prefix")
    if not tokens:
        raise _refuse(cmd, "the `cd <dir> &&` prefix is followed by no program")
    return tokens, subdir


def resolve_guard_cwd(root: Path, subdir: str | None) -> Path:
    """Where the guard runs. `subdir` must land inside `root`.

    `..` and absolute paths are refused rather than clamped: a guard run
    outside the worktree is not measuring the commit under test, and a
    silently corrected path would report a verdict about the wrong tree.
    """
    base = Path(root).resolve()
    if subdir is None:
        return base
    target = (base / subdir).resolve()
    if target != base and base not in target.parents:
        raise GuardCommandRefused(
            f"refusing to run in {subdir!r}: it resolves to {target}, which is "
            f"outside the worktree at {base}. {_HOW_A_GUARD_COMMAND_LOOKS}")
    if not target.is_dir():
        raise GuardCommandRefused(
            f"refusing to run in {subdir!r}: {target} is not a directory in "
            f"this worktree. {_HOW_A_GUARD_COMMAND_LOOKS}")
    return target


# ── running the guard ───────────────────────────────────────────────────────

@dataclass
class Run:
    exit_code: int | None  # None == timed out
    output: str


def run_guard(cwd: Path, cmd: str, timeout: int, env_extra: dict | None = None) -> Run:
    """Run the guard command and capture its exit code EXPLICITLY.

    Spawned as an argv list with no shell (see `parse_guard_cmd`), so the
    command is a program and its arguments and nothing else.

    Doctrine 6.3: the exit code is the verdict. We never inspect output to
    decide pass/fail, and we never let a wrapper swallow `$?`."""
    argv, subdir = parse_guard_cmd(cmd)
    workdir = resolve_guard_cwd(cwd, subdir)
    env = dict(os.environ)
    env.update(env_extra or {})
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    try:
        proc = subprocess.run(
            argv, cwd=str(workdir), capture_output=True, text=True,
            timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or b"")
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        return Run(None, partial)
    except OSError as exc:
        # A shell turned "no such program" into exit 127, which this tool
        # would have read as a RED guard - a verdict about a process that
        # never started. Without a shell it is an OSError, and it says so.
        raise GuardSpawnFailed(
            f"{argv[0]!r} could not be started in {workdir}: "
            f"{type(exc).__name__}: {exc}. No guard ran, so nothing is claimed "
            f"about the code under test.")
    return Run(proc.returncode, proc.stdout + proc.stderr)


# Heuristic ONLY - used to grade the strength of a red, never to decide it.
_HARNESS_BREAKAGE = re.compile(
    r"(ModuleNotFoundError|ImportError|SyntaxError|NameError:|"
    r"ERROR collecting|error TS\d+|cannot find module|"
    r"undefined reference|no such file or directory)",
    re.IGNORECASE,
)
_DISCRIMINATING = re.compile(
    r"(AssertionError|assert |FAILED |expected .* (but )?(got|received)|"
    r"✕|✗|Expected:|--- FAIL)",
    re.IGNORECASE,
)


def grade_red(output: str) -> tuple[bool, str]:
    """(is_weak, explanation). Best-effort text inspection, reported as such."""
    broke = bool(_HARNESS_BREAKAGE.search(output))
    asserted = bool(_DISCRIMINATING.search(output))
    if broke and not asserted:
        return True, (
            "the guard went red by failing to LOAD (import/collection error), "
            "not by asserting. Removing the fix breaks the build, which is a "
            "weaker proof than a discriminating assertion - the guard has not "
            "been shown to distinguish correct behaviour from incorrect."
        )
    return False, "the guard failed by assertion - it discriminates on behaviour."


# ── the verification ────────────────────────────────────────────────────────

def verify(
    repo: Path,
    commit: str = "HEAD",
    guard_cmd: str = "",
    code_patterns: list[str] | None = None,
    guard_patterns: list[str] | None = None,
    timeout: int = 600,
    links: list[str] | None = None,
    setup_cmd: str = "",
    keep_worktree: bool = False,
    require_guard_in_commit: bool = False,
) -> Result:
    warnings: list[str] = []

    if not guard_cmd.strip():
        return Result(INCONCLUSIVE, "no --guard-cmd given: there is nothing to verify.")

    # Parsed BEFORE any git work: a command that will never be run should not
    # cost a worktree, and a refusal is cheaper to read on its own.
    try:
        parse_guard_cmd(guard_cmd)
        if setup_cmd:
            parse_guard_cmd(setup_cmd)
    except GuardCommandRefused as exc:
        return Result(INCONCLUSIVE, str(exc))

    try:
        sha = _git(repo, "rev-parse", "--verify", f"{commit}^{{commit}}").strip()
    except GitError as exc:
        return Result(INCONCLUSIVE, f"cannot resolve commit {commit!r}: {exc}")

    parents = parents_of(repo, sha)
    if len(parents) == 0:
        return Result(INCONCLUSIVE, f"{sha[:8]} is a root commit: nothing to revert against.",
                      commit=sha)
    if len(parents) > 1:
        return Result(
            INCONCLUSIVE,
            f"{sha[:8]} is a merge commit. Verify the individual fix commits "
            f"instead - 'the fix' is not well defined across a merge.",
            commit=sha,
        )
    parent = parents[0]

    changed = changed_files(repo, sha)
    if not changed:
        return Result(INCONCLUSIVE, f"{sha[:8]} changes no files.", commit=sha)

    code, guard, inert = classify(changed, code_patterns, guard_patterns)

    if not code:
        what = "guard/test artifacts" if guard and not inert else (
            "prose or media" if inert and not guard else "guard and prose files")
        return Result(
            INCONCLUSIVE,
            f"{sha[:8]} changes no executable production code (all "
            f"{len(changed)} path(s) classified as {what}). There is no fix to "
            f"revert, so no verdict is possible - reverting a README and finding "
            f"the guard still green would say nothing about the guard. If the "
            f"classification is wrong, name the code paths with --code.",
            commit=sha, code_files=code, guard_files=guard, inert_files=inert,
            warnings=warnings,
        )

    if not guard:
        msg = (
            f"{sha[:8]} ships no test/guard file of its own (doctrine 2.1: every "
            f"fix ships with a guard in the same commit). Verifying against the "
            f"guard named in --guard-cmd anyway; that is valid when the guard is "
            f"a pre-existing class ratchet."
        )
        if require_guard_in_commit:
            return Result(INCONCLUSIVE, msg.replace("Verifying", "Refusing to verify"),
                          commit=sha, code_files=code, warnings=warnings)
        warnings.append(msg)

    # A guard file swept into the revert set makes every verdict meaningless.
    # Match on a token boundary, not a bare substring: "golden.py" is not
    # mentioned by "test_claim_check_golden.py".
    for path in code:
        name = Path(path).name
        mentioned = path in guard_cmd or (
            name and re.search(r"(?<![\w.\-])" + re.escape(name), guard_cmd)
        )
        if mentioned:
            warnings.append(
                f"{path} is classified as CODE but its name appears in the guard "
                f"command - it may be the guard itself. Reverting the guard would "
                f"invalidate this run; check the classification, and use "
                f"--guard-paths to pin it."
            )

    scratch = Path(tempfile.mkdtemp(prefix="sutradhar-verify-"))
    worktree = scratch / "wt"
    try:
        _git(repo, "worktree", "add", "--detach", "--quiet", str(worktree), sha)

        for link in links or []:
            src = (repo / link).resolve()
            if not src.exists():
                warnings.append(f"--link {link}: not present in the source repo, skipped.")
                continue
            dst = worktree / link
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                os.symlink(src, dst)

        if setup_cmd:
            setup = run_guard(worktree, setup_cmd, timeout)
            if setup.exit_code not in (0, None):
                return Result(
                    INCONCLUSIVE,
                    f"--setup-cmd failed with exit {setup.exit_code}; the worktree "
                    f"is not usable, so no verdict is possible.\n"
                    + _tail(setup.output),
                    commit=sha, code_files=code, guard_files=guard, inert_files=inert, warnings=warnings,
                )

        # ── step 1: the guard must be green WITH the fix ────────────────────
        baseline = run_guard(worktree, guard_cmd, timeout)
        if baseline.exit_code is None:
            return Result(
                INCONCLUSIVE,
                f"the guard timed out after {timeout}s at the fix commit. "
                f"Raise --timeout or narrow --guard-cmd.",
                commit=sha, code_files=code, guard_files=guard, inert_files=inert, warnings=warnings,
            )
        if baseline.exit_code != 0:
            return Result(
                INCONCLUSIVE,
                f"the guard is already RED at {sha[:8]} (exit {baseline.exit_code}), "
                f"with the fix in place. Nothing can be concluded from reverting a "
                f"fix whose guard does not pass - fix the premise first "
                f"(doctrine 6.4).\n" + _tail(baseline.output),
                commit=sha, code_files=code, guard_files=guard, inert_files=inert,
                baseline_exit=baseline.exit_code, warnings=warnings,
            )

        # ── step 2: revert the production half, keep the guard ──────────────
        for path in code + inert:
            if exists_at(repo, parent, path):
                _git(worktree, "checkout", parent, "--", path)
            else:
                target = worktree / path
                if target.exists():
                    target.unlink()

        # ── step 3: the guard must now be RED ───────────────────────────────
        reverted = run_guard(worktree, guard_cmd, timeout)
        if reverted.exit_code is None:
            return Result(
                INCONCLUSIVE,
                f"the guard timed out after {timeout}s with the fix reverted. "
                f"A hang is not a red: it proves nothing about the assertion.",
                commit=sha, code_files=code, guard_files=guard, inert_files=inert,
                baseline_exit=0, warnings=warnings,
            )

        if reverted.exit_code == 0:
            return Result(
                DECORATION,
                f"the guard PASSED with the fix reverted ({len(code)} file(s) "
                f"restored to {parent[:8]}). It cannot detect the defect it was "
                f"written for, so it is decoration: it will not stop the "
                f"regression from coming back. Fix the guard, not the report - "
                f"most often the guard sets internal state by hand instead of "
                f"exercising the real seam (doctrine 2.3).",
                commit=sha, code_files=code, guard_files=guard, inert_files=inert,
                baseline_exit=0, reverted_exit=0, warnings=warnings,
            )

        weak, why = grade_red(reverted.output)
        return Result(
            VERIFIED,
            f"green with the fix, red without it (exit {reverted.exit_code}): {why}",
            commit=sha, code_files=code, guard_files=guard, inert_files=inert,
            baseline_exit=0, reverted_exit=reverted.exit_code,
            weak=weak, warnings=warnings,
        )

    except GitError as exc:
        return Result(INCONCLUSIVE, f"git operation failed: {exc}", commit=sha,
                      code_files=code, guard_files=guard, inert_files=inert, warnings=warnings)
    except GuardNotRun as exc:
        # A refused command or a program that would not start. No guard ran,
        # so this is INCONCLUSIVE - never a DECORATION and never a pass.
        return Result(INCONCLUSIVE, str(exc), commit=sha, code_files=code,
                      guard_files=guard, inert_files=inert, warnings=warnings)
    finally:
        if keep_worktree:
            print(f"[verify-guard] worktree kept at {worktree}", file=sys.stderr)
        else:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force", str(worktree)],
                capture_output=True, text=True,
            )
            shutil.rmtree(scratch, ignore_errors=True)


def _tail(output: str, lines: int = 25) -> str:
    kept = output.strip().splitlines()[-lines:]
    return "  | " + "\n  | ".join(kept) if kept else "  | (no output)"


# ── selfcheck ───────────────────────────────────────────────────────────────

FIXTURE_BUG = '''\
def total(price, qty):
    """Line total. BUG: the bulk discount is never applied."""
    return price * qty
'''

FIXTURE_FIX = '''\
def total(price, qty):
    """Line total, with the 10% bulk discount at qty >= 10."""
    subtotal = price * qty
    if qty >= 10:
        subtotal *= 0.9
    return subtotal
'''

# A guard that exercises the real seam: it calls the public function and
# asserts on what came back. Reverting the fix MUST redden it.
FIXTURE_GUARD_REAL = '''\
import os, sys
sys.path.insert(0, os.getcwd())
import calc
sys.exit(0 if abs(calc.total(100, 10) - 900.0) < 1e-9 else 1)
'''

# The scar, reproduced exactly: a guard that sets up the state by hand and
# asserts on its own arithmetic. It never touches the seam, so it passes
# whether the fix is present or not. This is what "tested and half dead"
# looks like, and it is the case this tool exists to catch.
FIXTURE_GUARD_DECORATIVE = '''\
import sys
subtotal = 100 * 10
subtotal *= 0.9          # the guard re-implements the fix locally
sys.exit(0 if abs(subtotal - 900.0) < 1e-9 else 1)
'''

FIXTURE_GUARD_BROKEN = '''\
import sys
sys.exit(1)              # red no matter what: the premise is broken
'''

# The same real guard, written to be run from INSIDE tests/ - so the
# `cd <dir> && <program>` form has something to prove. Every `Guard-cmd:`
# trailer in this repository's history is of that shape, so the day it stops
# working is the day the per-commit check goes quietly INCONCLUSIVE.
FIXTURE_GUARD_REAL_IN_SUBDIR = '''\
import os, sys
sys.path.insert(0, os.path.dirname(os.getcwd()))
import calc
sys.exit(0 if abs(calc.total(100, 10) - 900.0) < 1e-9 else 1)
'''


def _fixture_repo() -> Path:
    """Build a throwaway repo: a buggy parent, then a fix commit carrying
    three guards - a real one, a decorative one, and a broken one."""
    root = Path(tempfile.mkdtemp(prefix="sutradhar-fixture-")).resolve()

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(root),
             "-c", "user.name=sutradhar-selfcheck",
             "-c", "user.email=selfcheck@sutradhar.invalid",
             "-c", "commit.gpgsign=false",
             *args],
            capture_output=True, text=True, check=True,
        )

    git("init", "-q")
    (root / "calc.py").write_text(FIXTURE_BUG)
    (root / "README.md").write_text("# fixture\n")
    git("add", "calc.py", "README.md")
    git("commit", "-q", "-m", "buggy parent")

    (root / "calc.py").write_text(FIXTURE_FIX)
    (root / "tests").mkdir()
    (root / "tests" / "check_real.py").write_text(FIXTURE_GUARD_REAL)
    (root / "tests" / "check_decorative.py").write_text(FIXTURE_GUARD_DECORATIVE)
    (root / "tests" / "check_broken.py").write_text(FIXTURE_GUARD_BROKEN)
    (root / "tests" / "check_real_here.py").write_text(FIXTURE_GUARD_REAL_IN_SUBDIR)
    git("add", "calc.py", "tests")
    git("commit", "-q", "-m", "fix: apply the bulk discount")

    (root / "README.md").write_text("# fixture\n\ndocs only.\n")
    git("add", "README.md")
    git("commit", "-q", "-m", "docs: nothing to revert here")
    return root


def selfcheck_end_to_end(verbose: bool = False) -> bool:
    """Plant a known-good guard and a known-decorative guard and require the
    tool to tell them apart.

    Doctrine 2.2 applied to itself: a verifier that always answers VERIFIED
    would pass every CI run while proving nothing, so the decorative case is
    the load-bearing half of this check."""
    root = _fixture_repo()
    py = shlex.quote(sys.executable)
    cases = [
        ("real guard on the fix commit", "HEAD~1",
         f"{py} tests/check_real.py", VERIFIED),
        ("decorative guard on the fix commit", "HEAD~1",
         f"{py} tests/check_decorative.py", DECORATION),
        ("guard already red at the fix commit", "HEAD~1",
         f"{py} tests/check_broken.py", INCONCLUSIVE),
        ("docs-only commit has no fix to revert", "HEAD",
         f"{py} tests/check_real.py", INCONCLUSIVE),
        # The one prefix that survived the shell's removal. This is the form
        # every `Guard-cmd:` trailer in this repository uses, so it is run
        # end to end rather than asserted at the parser.
        ("`cd <dir> && cmd` still runs the guard", "HEAD~1",
         f"cd tests && {py} check_real_here.py", VERIFIED),
        # ...and the refusal, which is the half that makes the zero above
        # mean something (6.7, evidence in pairs). A pipe is not a guard
        # command, and refusing it is INCONCLUSIVE - never a pass.
        ("a piped guard command is REFUSED, not run", "HEAD~1",
         f"{py} tests/check_real.py | cat", INCONCLUSIVE),
        ("a chained guard command is REFUSED", "HEAD~1",
         f"{py} tests/check_real.py; id", INCONCLUSIVE),
        ("a `cd` out of the worktree is REFUSED", "HEAD~1",
         f"cd .. && {py} check_real.py", INCONCLUSIVE),
    ]
    ok = True
    try:
        for name, commit, cmd, want in cases:
            res = verify(root, commit=commit, guard_cmd=cmd, timeout=120)
            if res.verdict != want:
                print(
                    f"[verify-guard] SELFCHECK FAILED: {name}\n"
                    f"    expected {want}, got {res.verdict}: {res.reason}",
                    file=sys.stderr,
                )
                ok = False
            elif verbose:
                print(f"[verify-guard] selfcheck ok: {name} -> {res.verdict}")

        # The classifier must have kept the guards and reverted only the code.
        res = verify(root, commit="HEAD~1", guard_cmd=f"{py} tests/check_real.py",
                     timeout=120)
        if res.code_files != ["calc.py"]:
            print(f"[verify-guard] SELFCHECK FAILED: reverted {res.code_files}, "
                  f"expected only ['calc.py']", file=sys.stderr)
            ok = False
        if "tests/check_real.py" not in res.guard_files:
            print(f"[verify-guard] SELFCHECK FAILED: guard file not kept "
                  f"(kept {res.guard_files})", file=sys.stderr)
            ok = False
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return ok


def selfcheck_command_parsing() -> bool:
    """Cheap, pure, runs on every invocation: the accept list and the refuse
    list, because a parser that accepted everything would be exactly the
    shell this replaced, and one that refused everything would make the tool
    unusable while looking safe."""
    accept = [
        ("pytest -q tests/x.py", ["pytest", "-q", "tests/x.py"], None),
        # The shape every `Guard-cmd:` trailer in this repo uses.
        ("cd python && python -m pytest tests/x.py -q",
         ["python", "-m", "pytest", "tests/x.py", "-q"], "python"),
        # A quoted operator is an ARGUMENT, not an operator: without a shell
        # there is nothing to interpret it.
        ('pytest -k "a|b"', ["pytest", "-k", "a|b"], None),
    ]
    refuse = [
        "pytest | cat", "pytest; rm -rf /", "echo $(id)", "`id`",
        "cd .. && pytest", "pytest && cd x", "", "   ",
        "pytest > log", "pytest && pytest", "cd python", "cd python && ",
        "pytest 'unclosed",
    ]
    ok = True
    for cmd, want_argv, want_dir in accept:
        try:
            argv, subdir = parse_guard_cmd(cmd)
        except GuardCommandRefused as exc:
            print(f"[verify-guard] SELFCHECK FAILED: {cmd!r} was refused, and "
                  f"it is a legal guard command: {exc}", file=sys.stderr)
            ok = False
            continue
        if (argv, subdir) != (want_argv, want_dir):
            print(f"[verify-guard] SELFCHECK FAILED: {cmd!r} parsed as "
                  f"{(argv, subdir)}, want {(want_argv, want_dir)}", file=sys.stderr)
            ok = False
    for cmd in refuse:
        try:
            parse_guard_cmd(cmd)
        except GuardCommandRefused:
            continue
        print(f"[verify-guard] SELFCHECK FAILED: {cmd!r} was ACCEPTED. A guard "
              f"command that only a shell could interpret must be refused - "
              f"this tool runs it as the current user.", file=sys.stderr)
        ok = False
    return ok


def selfcheck_classification() -> bool:
    """Cheap, pure, runs on every invocation: a blind classifier would
    revert the tests along with the fix and make every verdict a lie."""
    must_be_guard = [
        "tests/test_billing.py", "src/foo_test.go", "cypress/e2e/cart.cy.ts",
        "app/__tests__/nav.spec.tsx", "scripts/swallow_baseline.json",
        "conftest.py", "spec/models/user_spec.rb",
    ]
    must_be_code = [
        "src/billing.py", "app/components/Cart.tsx",
        "src/latest.go", "lib/manifest.json", "config/timeouts.yaml",
        "requirements.txt",          # pins what gets installed: not prose
    ]
    # Reverting these can never change what a guard observes. Treating them
    # as code produced a false DECORATION verdict on a docs-only commit the
    # first time this selfcheck ran.
    must_be_inert = ["README.md", "docs/adoption.md", "LICENSE", "assets/logo.svg"]

    for path in must_be_guard:
        if not is_guard_path(path):
            print(f"[verify-guard] SELFCHECK FAILED: {path} not seen as a guard file",
                  file=sys.stderr)
            return False
    for path in must_be_code:
        if is_guard_path(path) or is_inert_path(path):
            print(f"[verify-guard] SELFCHECK FAILED: {path} must be treated as "
                  f"production code", file=sys.stderr)
            return False
    for path in must_be_inert:
        if not is_inert_path(path) or is_guard_path(path):
            print(f"[verify-guard] SELFCHECK FAILED: {path} must be treated as inert",
                  file=sys.stderr)
            return False
    return True


# ── CLI ─────────────────────────────────────────────────────────────────────

def _print_human(res: Result) -> None:
    bar = "─" * 68
    print(f"\n[verify-guard] {bar}")
    if res.commit:
        print(f"  commit  {res.commit[:12]}")
    if res.code_files:
        print(f"  code    {len(res.code_files)} file(s) reverted: "
              + ", ".join(res.code_files[:6])
              + (f" (+{len(res.code_files) - 6} more)" if len(res.code_files) > 6 else ""))
    if res.guard_files:
        print(f"  guard   {len(res.guard_files)} file(s) kept: "
              + ", ".join(res.guard_files[:6])
              + (f" (+{len(res.guard_files) - 6} more)" if len(res.guard_files) > 6 else ""))
    if res.inert_files:
        print(f"  inert   {len(res.inert_files)} prose/media file(s): "
              + ", ".join(res.inert_files[:6])
              + (f" (+{len(res.inert_files) - 6} more)" if len(res.inert_files) > 6 else ""))
    for warn in res.warnings:
        print(f"\n  WARNING: {warn}")
    label = {
        VERIFIED: "VERIFIED (weak)" if res.weak else "VERIFIED",
        DECORATION: "DECORATION",
        INCONCLUSIVE: "INCONCLUSIVE",
    }[res.verdict]
    print(f"\n  {label}: {res.reason}")
    print(f"[verify-guard] {bar}\n")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    if not selfcheck_classification() or not selfcheck_command_parsing():
        return 2

    if "--selfcheck" in argv:
        return 0 if selfcheck_end_to_end(verbose=True) else 1

    commit, guard_cmd, setup_cmd = "HEAD", "", ""
    repo = Path.cwd()
    timeout = 600
    code_patterns: list[str] = []
    guard_patterns: list[str] = []
    links: list[str] = []
    as_json = "--json" in argv
    keep = "--keep-worktree" in argv
    require_guard = "--require-guard-in-commit" in argv

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--commit":
            commit = argv[i + 1]; i += 2
        elif arg == "--guard-cmd":
            guard_cmd = argv[i + 1]; i += 2
        elif arg == "--setup-cmd":
            setup_cmd = argv[i + 1]; i += 2
        elif arg == "--repo":
            repo = Path(argv[i + 1]); i += 2
        elif arg == "--timeout":
            timeout = int(argv[i + 1]); i += 2
        elif arg == "--code":
            code_patterns.append(argv[i + 1]); i += 2
        elif arg == "--guard-paths":
            guard_patterns.append(argv[i + 1]); i += 2
        elif arg == "--link":
            links.append(argv[i + 1]); i += 2
        else:
            i += 1

    try:
        root = _git(repo, "rev-parse", "--show-toplevel").strip()
    except GitError:
        res = Result(INCONCLUSIVE, f"{repo} is not inside a git repository.")
        print(res.to_json() if as_json else res.reason)
        return res.exit_code

    res = verify(
        Path(root), commit=commit, guard_cmd=guard_cmd,
        code_patterns=code_patterns or None, guard_patterns=guard_patterns or None,
        timeout=timeout, links=links, setup_cmd=setup_cmd,
        keep_worktree=keep, require_guard_in_commit=require_guard,
    )
    if as_json:
        print(res.to_json())
    else:
        _print_human(res)
    return res.exit_code


if __name__ == "__main__":
    sys.exit(main())
