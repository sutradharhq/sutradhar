#!/usr/bin/env python3
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""PreToolUse hook: run the fast guards before a `git commit` is allowed.

    hooks/hooks.json -> PreToolUse, matcher "Bash|PowerShell"

Stdin carries the documented PreToolUse payload (`tool_name`, `tool_input`,
`cwd`, ...). This hook exits immediately unless `tool_input.command`
actually runs `git commit`; when it does, it runs the guards that are
APPLICABLE to the repo and denies the tool call - with the guard's own
output as the reason - if one of them is red.

Three rules it will not bend:

  1. **A guard that could not run has not passed** (2.9). A missing
     baseline, an absent `docs/rounds/`, no staged Python: each is reported
     by name as skipped, and never folded into a green verdict.
  2. **An instrument failure is ours** (2.4). Missing guard, spawn error,
     timeout, an exit code outside the guard's partition, a bug in this
     file: say so, name the party, and ALLOW. A gate that blocks because it
     broke is a gate that gets uninstalled, and every guard behind it
     leaves with it.
  3. **Name the tree you measured** (backflow B-15). These guards read the
     working tree; `git commit` commits the index. When they differ, the
     message says which one was read and where they disagree. The gate does
     not stash, check out, or otherwise touch anyone's work.

Verdicts travel as JSON on stdout, per the documented PreToolUse decision
shape: `hookSpecificOutput.permissionDecision` = `deny`, with the guard
text in `permissionDecisionReason`. Exit 2 is never used - see `_hooklib`.

    python3 precommit_gate.py --selfcheck   # planted cases, no stdin needed

The design note is docs/design/agent-loop-hooks.md.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import _hooklib as H
except Exception as exc:  # pragma: no cover - exercised by the import mutant
    # Even the import is inside the honesty rule: a hook that cannot load
    # its own library must not be able to deny a commit.
    sys.stderr.write(f"[sutradhar-hooks] instrument failure: cannot import "
                     f"_hooklib: {type(exc).__name__}: {exc}\n")
    sys.stdout.write(
        '{"systemMessage": "[sutradhar-hooks] instrument failure: cannot import '
        '_hooklib. Nothing was blocked - this is the hook failing."}')
    raise SystemExit(0)

SHELL_TOOLS = ("Bash", "PowerShell")

# Exit-code partitions, quoted from docs/design/mcp-server.md. Exit 2 is a
# USAGE error for these three guards, which makes it an instrument failure
# and not a finding.
LINT_CODES = {0: H.GREEN, 1: H.RED}


def _staged_paths(cwd: str, command: str) -> tuple[list[str], list[str]]:
    """(paths in the commit, paths where the index and the tree disagree)."""
    staged = [p for p in H.git(cwd, "diff", "--cached", "--name-only",
                               "--diff-filter=ACMR").splitlines() if p.strip()]
    dirty = [p for p in H.git(cwd, "diff", "--name-only",
                              "--diff-filter=ACMR").splitlines() if p.strip()]
    if H.commits_all_tracked(command):
        # `git commit -a` will stage these too, so they are part of the commit.
        staged = sorted(set(staged) | set(dirty))
        return staged, []
    return staged, sorted(set(staged) & set(dirty))


def _plan(root: Path, staged: list[str]) -> list[tuple[str, list[str] | None, str]]:
    """(guard name, argv or None when inapplicable, why it is inapplicable)."""
    gdir = H.guard_dir()
    py = sys.executable or "python3"
    out: list[tuple[str, list[str] | None, str]] = []

    py_files = [p for p in staged if p.endswith(".py") and (root / p).is_file()]
    out.append((
        "interpolation_lint",
        [py, str(gdir / "interpolation_lint.py"), *py_files] if py_files else None,
        "no Python file in this commit",
    ))

    baseline = os.environ.get("SUTRADHAR_SWALLOW_BASELINE")
    found = Path(baseline) if baseline else next(
        (c for c in (root / "swallow_baseline.json",
                     root / "scripts" / "swallow_baseline.json") if c.is_file()), None)
    out.append((
        "swallow_lint",
        [py, str(gdir / "swallow_lint.py"), str(root), "--baseline", str(found)]
        if found and Path(found).is_file() else None,
        "no swallow_baseline.json - the ratchet has no floor to hold",
    ))

    rounds_dir = root / "docs" / "rounds"
    argv = None
    if rounds_dir.is_dir():
        argv = [py, str(gdir / "rounds.py"), str(rounds_dir), "--check"]
        if (root / "DOCTRINE.md").is_file():
            argv[3:3] = ["--doctrine", str(root / "DOCTRINE.md")]
    out.append(("rounds", argv, "no docs/rounds/ in this repo"))
    return out


def _summary(runs: list[H.GuardRun], skips: dict[str, str]) -> str:
    parts = []
    for r in runs:
        if r.status == H.GREEN:
            parts.append(f"{r.name} OK")
        elif r.status == H.RED:
            parts.append(f"{r.name} RED")
        else:
            parts.append(f"{r.name} INSTRUMENT-FAILURE")
    for name, why in skips.items():
        parts.append(f"{name} skipped ({why})")
    return " | ".join(parts)


def gate(payload: dict) -> None:
    if payload.get("tool_name") not in SHELL_TOOLS:
        H.allow_silently()
    command = (payload.get("tool_input") or {}).get("command") or ""
    is_commit, fell_back = H.is_git_commit(command)
    if not is_commit:
        H.allow_silently()

    cwd = payload.get("cwd") or os.getcwd()
    root = Path(H.git(cwd, "rev-parse", "--show-toplevel").strip())
    staged, disagreeing = _staged_paths(str(root), command)

    runs: list[H.GuardRun] = []
    skips: dict[str, str] = {}
    for name, argv, why in _plan(root, staged):
        if argv is None:
            skips[name] = why
            continue
        runs.append(H.run_guard(name, argv, root, LINT_CODES))

    tree = [f"Measured the working tree at {root}, not the index."]
    if disagreeing:
        tree.append(
            f"{len(disagreeing)} staged path(s) differ from the working tree, so "
            f"this verdict is about a slightly different tree than the one being "
            f"committed: {', '.join(disagreeing[:8])}"
            + (" ..." if len(disagreeing) > 8 else ""))
    if fell_back:
        tree.append("The command could not be tokenised, so the gate ran on a "
                    "word-level fallback match.")

    line = _summary(runs, skips)
    red = [r for r in runs if r.status == H.RED]
    broke = [r for r in runs if r.status == H.INSTRUMENT]

    if red:
        body = "\n\n".join(f"--- {r.name} (exit {r.code}) ---\n{r.detail}" for r in red)
        extra = "".join(f"\n{H.MARKER} {r.name}: {r.detail}" for r in broke)
        H.emit({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": H.cap(
                f"{H.MARKER} pre-commit gate: BLOCKED by "
                f"{', '.join(r.name for r in red)}.\n\n{body}\n\n"
                f"Guards: {line}\n{' '.join(tree)}{extra}\n"
                f"Fix the finding, or run the guard yourself to see the same "
                f"output. This gate is advisory about WHICH tree it read: see "
                f"the line above.", 9000),
        }})

    if broke:
        H.allow_with_message(
            f"{H.MARKER} pre-commit gate ALLOWED the commit: {len(broke)} guard(s) "
            f"could not run, which is the hook's failure and not a verdict on your "
            f"code.\n" + "\n".join(f"  {r.name}: {r.detail}" for r in broke)
            + f"\nGuards: {line}")

    if not runs:
        H.allow_with_message(
            f"{H.MARKER} pre-commit gate measured NOTHING: every guard was "
            f"inapplicable to this repo. Allowed, and saying so - a gate with no "
            f"applicable instrument is not a green one.\nGuards: {line}")

    H.allow_with_message(f"{H.MARKER} pre-commit gate: {line}. {tree[0]}"
                         + (f" {tree[1]}" if len(tree) > 1 else ""))


# ── selfcheck ───────────────────────────────────────────────────────────────

def selfcheck() -> bool:
    """Prove the classifier can tell a commit from a lookalike, and that the
    exit-code partition refuses a code it does not know.

    Doctrine 6.7: an exit code is evidence only in pairs. Every case below
    has a positive and a negative side, because a matcher that answers True
    to everything would pass a one-sided check."""
    ok = True
    cases = [
        ("git commit -m 'x'", True), ("cd app && git commit -am wip", True),
        ("$(git commit)", True), ("git -C /tmp/repo commit -m x", True),
        ("git -c user.name=x commit", True), ("  git   commit  ", True),
        ("echo 'git commit'", False), ("git commit --help", False),
        ("git commit-graph write", False), ("git log --format=%B", False),
        ("npm test", False), ("git add -A", False),
    ]
    for command, want in cases:
        got, _ = H.is_git_commit(command)
        if got != want:
            print(f"[precommit-gate] SELFCHECK FAILED: is_git_commit({command!r}) "
                  f"= {got}, want {want}", file=sys.stderr)
            ok = False

    for command, want in [("git commit -am x", True), ("git commit -a", True),
                          ("git commit --all", True), ("git commit -m x", False)]:
        if H.commits_all_tracked(command) != want:
            print(f"[precommit-gate] SELFCHECK FAILED: commits_all_tracked("
                  f"{command!r}) != {want}", file=sys.stderr)
            ok = False

    unknown = H.run_guard("planted", [sys.executable, "-c", "raise SystemExit(7)"],
                          Path.cwd(), LINT_CODES)
    if unknown.status != H.INSTRUMENT:
        print("[precommit-gate] SELFCHECK FAILED: exit 7 was partitioned as "
              f"{unknown.status}, not an instrument failure. An unrecognised exit "
              "code must never become a verdict.", file=sys.stderr)
        ok = False
    for code, want in ((0, H.GREEN), (1, H.RED)):
        r = H.run_guard("planted", [sys.executable, "-c", f"raise SystemExit({code})"],
                        Path.cwd(), LINT_CODES)
        if r.status != want:
            print(f"[precommit-gate] SELFCHECK FAILED: exit {code} partitioned as "
                  f"{r.status}, want {want}", file=sys.stderr)
            ok = False

    if ok:
        print("[precommit-gate] selfcheck OK: commit classifier (12 cases), "
              "-a detection (4), exit-code partition (3).")
    return ok


def main() -> None:
    argv = sys.argv[1:]
    H.reject_unknown_flags(argv, {"--selfcheck"})
    if "--selfcheck" in argv:
        raise SystemExit(0 if selfcheck() else 1)
    gate(H.read_payload())


if __name__ == "__main__":
    H.main_guarded(main)
