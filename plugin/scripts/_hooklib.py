# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Shared floor for the two session hooks. Stdlib only, no package imports.

The design note is `docs/design/agent-loop-hooks.md`; it records the doc
pages every field name here was read from, on the day it was read.

Everything in this file exists to serve one rule:

    **A hook that crashes or cannot run must never block the user.**

An instrument whose error branch cannot tell "the subject failed" from "I
failed" reports the wrong outage with total confidence, and always reports
it about the subject (the R3-1 class, doctrine 2.4). A hook has the sharper
version: its error branch does not merely mislabel the failure, it takes the
commit away. So a guard that RAN and found something is a verdict, and
anything else - missing file, spawn error, timeout, an exit code outside the
guard's documented partition, a bug in this file - is an INSTRUMENT failure
that says so by name and allows.

Exit codes, because they are the blocking mechanism and not decoration:

    0 + JSON      the decision. Deny, or a message, or silence.
    0 + nothing   allow, silently. The common case.
    1             this hook was called wrong (unknown flag). The docs make a
                  non-2 exit a NON-blocking error, so a typo in the hook's
                  own configuration is reported without denying anyone's
                  commit - and is still nonzero, so a human's `$?` is honest.
    2             never emitted. Exit 2 is the harness's block signal, and
                  this file blocks through JSON so the reason travels with
                  the decision.
"""
from __future__ import annotations

import json
import os
import sys

# `subprocess`, `shlex` and `pathlib` are imported inside the functions that
# need them, not here. This module is on the PreToolUse fast path, which
# fires on EVERY Bash call, and those three cost more than a bare
# interpreter start on a Linux runner (R16-8: 3.2x against a 3.0x budget).
# A command that is not a commit must cost a JSON parse and a substring
# check, nothing more.

MARKER = "[sutradhar-hooks]"

#: Captured bytes per stream before a guard's output becomes a denial
#: reason. The harness caps hook output strings at 10,000 characters and
#: replaces anything longer with a preview plus a file path, so an uncapped
#: reason is silently rewritten into something the agent cannot read; and a
#: reason goes straight into a model's context window (doctrine 2.6).
#: Truncation is STATED - a partial finding list read as a complete one is
#: worse than no list.
MAX_REASON_BYTES = 8192

#: Seconds per guard subprocess. Deliberately shorter than the `timeout`
#: declared in hooks/hooks.json, so the decision about a slow guard is ours
#: (reported, allowed) rather than the harness's (cancelled, silent).
GUARD_TIMEOUT_S = 45

#: Seconds per `git` call. A git that hangs must not hang the session.
GIT_TIMEOUT_S = 10

# Verdicts. SKIPPED and INSTRUMENT are both "no measurement was taken", and
# they are distinct because their causes are: one is the user's repo not
# having the thing, the other is us.
GREEN, RED, SKIPPED, INSTRUMENT = "GREEN", "RED", "SKIPPED", "INSTRUMENT"


class InstrumentFailure(Exception):
    """We failed. Never the user's code, never their repo, never their tree."""


class GuardRun:
    """One guard's outcome, already partitioned."""

    def __init__(self, name: str, status: str, detail: str = "", code: int | None = None):
        self.name, self.status, self.detail, self.code = name, status, detail, code

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"GuardRun({self.name!r}, {self.status!r}, code={self.code!r})"


# ── output ──────────────────────────────────────────────────────────────────

def cap(text: str, limit: int = MAX_REASON_BYTES) -> str:
    """Truncate loudly. A silently truncated guard report is worse than none."""
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return text
    kept = raw[:limit].decode("utf-8", errors="ignore")
    return f"{kept}\n{MARKER} [truncated: {limit} of {len(raw)} bytes]"


def emit(payload: dict) -> None:
    """Write EXACTLY one JSON object and nothing else, then exit 0.

    The docs are explicit that any other text on stdout - a stray print, a
    shell profile banner - makes the whole output parse as plain text and
    the decision vanish without an error. So this is the only writer.
    """
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    raise SystemExit(0)


def allow_silently() -> None:
    raise SystemExit(0)


def allow_with_message(text: str) -> None:
    emit({"systemMessage": cap(text, 9000)})


def instrument_failure(exc: BaseException | str, where: str = "") -> None:
    """Name OURSELVES as the failing party, then allow.

    The exception TYPE is printed, not just its message: "something went
    wrong" attached to a commit is read as a finding about the commit.
    """
    if isinstance(exc, BaseException):
        detail = f"{type(exc).__name__}: {exc}"
    else:
        detail = str(exc)
    prefix = f"{MARKER} instrument failure"
    if where:
        prefix += f" in {where}"
    sys.stderr.write(f"{prefix}: {detail}\n")
    emit({"systemMessage": f"{prefix}: {detail}. Nothing was blocked - "
                           f"this is the hook failing, not your code."})


def read_payload() -> dict:
    """The event JSON on stdin. Unreadable payload = we know nothing."""
    raw = sys.stdin.read()
    if not raw.strip():
        raise InstrumentFailure("empty stdin; no hook payload to read")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise InstrumentFailure(f"stdin is not JSON ({type(exc).__name__})")
    if not isinstance(data, dict):
        raise InstrumentFailure(f"hook payload is {type(data).__name__}, not an object")
    return data


# ── subprocesses ────────────────────────────────────────────────────────────

def guard_dir() -> Path:
    """Where the guard CLIs live.

    `SUTRADHAR_GUARD_DIR` first, for adopters who copied the guards to
    `scripts/`; then the guards bundled inside this plugin. Absent is an
    instrument failure naming both paths tried, never a verdict.

    The `../python/sutradhar_guards` this used to fall back to is gone.
    Claude Code copies an installed plugin into `~/.claude/plugins/cache`
    and does NOT copy files outside the plugin directory, so that path
    existed only in the layout this was built in - a checkout - and the
    plugin would have failed the first time anyone installed it from a
    marketplace (R16-1). `plugin/guards/` is pinned byte-for-byte to
    `python/sutradhar_guards/` by `test_plugin_bundle.py`.
    """
    from pathlib import Path
    env = os.environ.get("SUTRADHAR_GUARD_DIR")
    bundled = Path(__file__).resolve().parents[1] / "guards"
    root = Path(env) if env else bundled
    if not root.is_dir():
        tried = f"SUTRADHAR_GUARD_DIR={env}" if env else f"the plugin's own {bundled}"
        raise InstrumentFailure(
            f"no guard directory at {root} (tried {tried}; the fallback is "
            f"{bundled}). Set SUTRADHAR_GUARD_DIR to point at the guards, or "
            f"reinstall the plugin - nothing was measured and nothing is "
            f"claimed about your code."
        )
    return root


def _timeout_expired():
    import subprocess
    return subprocess.TimeoutExpired


def run(argv: list[str], cwd: str | Path, timeout: int) -> "subprocess.CompletedProcess":
    """Spawn. argv list only - no `shell=True` anywhere in this plugin, so a
    repo path containing a semicolon is a path and not a command."""
    import subprocess
    return subprocess.run(
        argv, capture_output=True, text=True, cwd=str(cwd), timeout=timeout,
    )


def run_guard(name: str, argv: list[str], cwd: str | Path,
              result_codes: dict[int, str], timeout: int = GUARD_TIMEOUT_S) -> GuardRun:
    """Run one guard and partition its exit code.

    `result_codes` maps the exit codes that are VERDICTS to GREEN/RED.
    Anything else is INSTRUMENT - by lookup with an explicit default, never
    `if red: ... else: green`, because the fall-through direction of that
    shape is "pass", and a code nobody anticipated would silently become one.
    """
    try:
        proc = run(argv, cwd, timeout)
    except _timeout_expired():
        return GuardRun(name, INSTRUMENT,
                        f"{name} exceeded {timeout}s and was killed. The guard was "
                        f"stopped, which is not the same as the code passing.")
    except OSError as exc:
        return GuardRun(name, INSTRUMENT, f"{name} could not be started: "
                                          f"{type(exc).__name__}: {exc}")
    text = (proc.stdout or "") + (proc.stderr or "")
    status = result_codes.get(proc.returncode)
    if status is None:
        return GuardRun(name, INSTRUMENT,
                        f"{name} exited {proc.returncode}, which is not one of its "
                        f"documented codes {sorted(result_codes)}. An unrecognised "
                        f"exit code is not a verdict; nothing is claimed about the "
                        f"code under test.\n{cap(text, 2048)}", proc.returncode)
    return GuardRun(name, status, cap(text), proc.returncode)


# ── git ─────────────────────────────────────────────────────────────────────

def git(cwd: str | Path, *args: str) -> str:
    try:
        proc = run(["git", *args], cwd, GIT_TIMEOUT_S)
    except _timeout_expired():
        raise InstrumentFailure(f"`git {' '.join(args)}` exceeded {GIT_TIMEOUT_S}s")
    except OSError as exc:
        raise InstrumentFailure(f"git could not be run: {type(exc).__name__}: {exc}")
    if proc.returncode != 0:
        raise InstrumentFailure(
            f"`git {' '.join(args)}` exited {proc.returncode}: "
            f"{(proc.stderr or '').strip()[:400]}")
    return proc.stdout


# ── command parsing ─────────────────────────────────────────────────────────

# `git -C x`, `git -c k=v` and friends take a value; the subcommand is the
# first bare word after them. Getting this wrong in the permissive direction
# costs a needless gate run; in the strict direction it costs the gate.
_GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace",
                        "--super-prefix", "--config-env", "--exec-path"}
_SUBSTITUTION_EDGES = "$(){}`"


def _normalise(token: str) -> str:
    return token.strip(_SUBSTITUTION_EDGES)


def is_git_commit(command: str) -> tuple[bool, bool]:
    """(this command runs `git commit`, the parse fell back).

    Token-based, not substring: `echo "git commit"` is one quoted token and
    must not gate, while `cd x && git commit` and `$(git commit)` must. A
    command shlex cannot parse falls back to a word search and SAYS so - on
    an unparseable command the cheap error is a needless 200 ms gate, not a
    missed one.
    """
    # Fast path first: a token can only normalise to `commit` if the raw
    # text contains those letters once quotes and backslashes are removed
    # (`git "com""mit"`, `git com\\mit`). Everything else - the tokeniser
    # and the `re` it drags in - waits until that is true.
    if "commit" not in command.replace("\\", "").replace('"', "").replace("'", ""):
        return False, False
    import shlex
    try:
        tokens = shlex.split(command)
    except ValueError:
        import re
        return bool(re.search(r"\bgit\b[^|;&]*\bcommit\b", command)), True

    i = 0
    while i < len(tokens):
        if _normalise(tokens[i]) != "git":
            i += 1
            continue
        j = i + 1
        while j < len(tokens):
            tok = _normalise(tokens[j])
            if tok in _GIT_OPTS_WITH_VALUE:
                j += 2
                continue
            if tok.startswith("-"):
                j += 1
                continue
            break
        if j < len(tokens) and _normalise(tokens[j]) == "commit":
            # `git commit --help` prints help and commits nothing.
            rest = {_normalise(t) for t in tokens[j + 1:]}
            if not ({"--help", "-h"} & rest):
                return True, False
        i = j + 1 if j > i else i + 1
    return False, False


def commits_all_tracked(command: str) -> bool:
    """`git commit -a` stages tracked modifications at commit time, so the
    index alone does not describe the tree being committed."""
    try:
        import shlex
        tokens = [_normalise(t) for t in shlex.split(command)]
    except ValueError:
        return True  # cannot tell -> assume the wider scope
    for tok in tokens:
        if tok in ("--all", "--include", "-a"):
            return True
        if len(tok) > 1 and tok.startswith("-") and not tok.startswith("--") and "a" in tok[1:]:
            return True
    return False


# ── entry point plumbing ────────────────────────────────────────────────────

def selftest_trapdoor() -> None:
    """Mutation-verify the honesty rule from the outside (doctrine 2.2).

    A catch-all nobody has watched swallow anything is decoration. This is
    the documented way to make the hook raise inside its own body, so a test
    can assert that a broken hook allows-with-a-message rather than blocks.
    """
    mode = os.environ.get("SUTRADHAR_HOOK_SELFTEST", "")
    if mode == "raise":
        raise RuntimeError("SUTRADHAR_HOOK_SELFTEST=raise: deliberate crash")
    if mode == "exit":
        raise SystemExit(9)


def reject_unknown_flags(argv: list[str], known: set[str]) -> None:
    """A flag we do not know is a caller error, and it exits 1 - not 2.

    Exit 2 is the harness's block signal, so the usual house convention
    would turn a typo in this hook's own configuration into a denial of
    somebody's commit. Exit 1 is a NON-blocking error by the documented
    table: reported in the transcript, nonzero for a human's `$?`, and it
    takes nothing hostage.
    """
    unknown = [a for a in argv if a not in known]
    if unknown:
        sys.stderr.write(f"{MARKER} unknown flag(s): {' '.join(unknown)}\n")
        raise SystemExit(1)


def main_guarded(body) -> None:
    """Run a hook body so that NOTHING it can do blocks the user.

    `SystemExit` passes through - it is how `emit` and the flag check
    return. Every other exception, including one raised by this module, is
    reported as ours and allowed.
    """
    try:
        selftest_trapdoor()
        body()
    except SystemExit:
        raise
    except InstrumentFailure as exc:
        instrument_failure(str(exc))
    except BaseException as exc:  # noqa: BLE001 - the entire point of this file
        instrument_failure(exc)
    allow_silently()
