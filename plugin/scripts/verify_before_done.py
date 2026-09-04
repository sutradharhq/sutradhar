#!/usr/bin/env python3
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Stop hook: before the turn ends, ask whether the guard on HEAD is real.

    hooks/hooks.json -> Stop (no matcher; Stop takes none)

Doctrine 2.2 says a guard never shown to fail is decoration. `ci/guards.yml`
already checks it per pull request by reading a `Guard-cmd:` trailer off the
commit message. This runs the same check at the end of the turn that wrote
the commit, which is the last moment it is cheap to fix.

    Guard-cmd: python -m pytest tests/test_billing.py -q

| HEAD                              | verdict      | what happens                  |
|-----------------------------------|--------------|-------------------------------|
| trailer, guard goes red on revert | VERIFIED     | silence                       |
| trailer, guard stays green        | DECORATION   | `decision: "block"` + reason  |
| trailer, verifier could not tell  | INCONCLUSIVE | said by name, stop proceeds   |
| no trailer, prod + test both moved| -            | a reminder, never a block     |
| anything else                     | -            | silence                       |

**INCONCLUSIVE is never reported as a pass** (2.9). It is also not a block:
its usual causes - dirty tree, merge commit, no git - are conditions the
agent cannot fix by working longer, and a Stop block that cannot be
satisfied is a loop the harness has to break. So it is named, out loud, to
the user.

**Silence is the default.** This event fires on every turn, so anything it
says on a turn where nothing happened is noise, and a noisy gate is a
removed gate (R14-2). It speaks only about a HEAD that carries a trailer or
mixes production and test files, and only ONCE per commit per session: a
marker under the system temp directory (never the user's repo) records that
this HEAD was reported, which also means a DECORATION verdict can block at
most once and can never drive the harness's 8-continuation cap.

    python3 verify_before_done.py --selfcheck   # planted cases, no stdin needed

The design note is docs/design/agent-loop-hooks.md.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import _hooklib as H
except Exception as exc:  # pragma: no cover - exercised by the import mutant
    sys.stderr.write(f"[sutradhar-hooks] instrument failure: cannot import "
                     f"_hooklib: {type(exc).__name__}: {exc}\n")
    sys.stdout.write(
        '{"systemMessage": "[sutradhar-hooks] instrument failure: cannot import '
        '_hooklib. Nothing was blocked - this is the hook failing."}')
    raise SystemExit(0)

VERIFIED, DECORATION, INCONCLUSIVE = "VERIFIED", "DECORATION", "INCONCLUSIVE"
# verify_guard's documented tri-state. Its exit 2 is a VERDICT ("I could not
# tell"), unlike every other guard here, where 2 is a usage error. A single
# shared table would get one of the two backwards, silently.
VERIFY_CODES = {0: H.GREEN, 1: H.RED, 2: H.SKIPPED}
VERDICT_OF = {H.GREEN: VERIFIED, H.RED: DECORATION, H.SKIPPED: INCONCLUSIVE}

#: Seconds for one `verify_guard` run. It builds a worktree and runs a test
#: suite twice by design, so this is generous - but bounded, because a Stop
#: hook that hangs is worse than one that answers INCONCLUSIVE.
VERIFY_TIMEOUT_S = 180

TRAILER = re.compile(r"^\s*Guard-cmd:\s*(.+?)\s*$", re.MULTILINE)

_TEST_HINTS = ("test", "tests", "spec", "specs", "__tests__", "cypress", "e2e")
_SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go",
                    ".rs", ".java", ".rb", ".kt", ".swift", ".c", ".cc", ".cpp",
                    ".h", ".hpp", ".cs", ".php", ".scala", ".sh"}


def looks_like_test(path: str) -> bool:
    p = Path(path)
    if any(part.lower() in _TEST_HINTS for part in p.parts[:-1]):
        return True
    stem = p.stem.lower()
    return (stem.startswith("test_") or stem.endswith("_test")
            or ".test" in p.name.lower() or ".spec" in p.name.lower()
            or stem.endswith("test") and p.suffix in _SOURCE_SUFFIXES)


def split_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    """(production source, test source). Docs and config are neither."""
    prod, test = [], []
    for path in paths:
        if Path(path).suffix not in _SOURCE_SUFFIXES:
            continue
        (test if looks_like_test(path) else prod).append(path)
    return prod, test


def guard_cmd_of(message: str) -> str:
    found = TRAILER.findall(message)
    return found[-1].strip() if found else ""


def _marker(session: str, repo: str, sha: str) -> Path | None:
    """Where we record 'this HEAD was already reported this session'.

    The system temp directory, never the repo: a gate with side effects in
    somebody's working tree is a merge conflict waiting for a bad afternoon.
    Returns None when the marker cannot be created, and the caller then does
    the work again rather than skipping it - re-reporting is a cost, not a
    lie.

    The repository path is part of the key. Keyed on `(session, sha)` alone,
    two checkouts that share a commit - a clone, a worktree, a fork, or the
    identical fixture repos this hook's own tests build - suppress each
    other's report, and the second one goes silent while looking exactly
    like a pass (R15-1, found by the test that expected a message).
    """
    key = hashlib.sha256(f"{session}\0{repo}\0{sha}".encode()).hexdigest()[:32]
    try:
        base = Path(tempfile.gettempdir()) / "sutradhar-hooks"
        base.mkdir(parents=True, exist_ok=True)
        return base / key
    except OSError:
        return None


def already_reported(mark: Path | None) -> bool:
    return bool(mark and mark.exists())


def record(mark: Path | None) -> None:
    if mark is None:
        return
    try:
        mark.write_text("reported\n")
    except OSError as exc:
        # A marker we could not write costs a repeat, not a wrong answer - but
        # it is still said out loud, because "the same message every turn" has
        # a cause and a silent one is unfindable.
        sys.stderr.write(f"{H.MARKER} could not record {mark}: "
                         f"{type(exc).__name__}: {exc}\n")


def verify(root: Path, guard_cmd: str) -> tuple[str, str]:
    """(verdict, the verifier's own text). Never a verdict we invented."""
    gdir = H.guard_dir()
    py = sys.executable or "python3"
    run = H.run_guard(
        "verify_guard",
        [py, str(gdir / "verify_guard.py"), "--repo", str(root),
         "--commit", "HEAD", "--guard-cmd", guard_cmd],
        root, VERIFY_CODES, timeout=VERIFY_TIMEOUT_S)
    if run.status == H.INSTRUMENT:
        # The verifier could not be run. That is not "the guard is fine", and
        # it is not "the guard is decoration" either.
        return INCONCLUSIVE, (f"verify_guard could not be run, so nothing was "
                              f"measured: {run.detail}")
    return VERDICT_OF[run.status], run.detail


def check(payload: dict) -> None:
    if payload.get("stop_hook_active"):
        # Already continuing because of a Stop hook. Doing work here is how a
        # hook earns the harness's 8-continuation override.
        H.allow_silently()

    cwd = payload.get("cwd") or os.getcwd()
    try:
        root = Path(H.git(cwd, "rev-parse", "--show-toplevel").strip())
        sha = H.git(cwd, "rev-parse", "HEAD").strip()
        message = H.git(cwd, "log", "-1", "--format=%B")
        touched = [p for p in H.git(cwd, "show", "--name-only", "--format=",
                                    "HEAD").splitlines() if p.strip()]
    except H.InstrumentFailure:
        # No repo, no commits, no HEAD: there is nothing to verify and no
        # claim to make. This fires every turn, so it says nothing.
        H.allow_silently()
        return

    mark = _marker(str(payload.get("session_id") or ""), str(root), sha)
    if already_reported(mark):
        H.allow_silently()

    guard_cmd = guard_cmd_of(message)
    if not guard_cmd:
        prod, test = split_paths(touched)
        if prod and test:
            record(mark)
            H.allow_with_message(
                f"{H.MARKER} HEAD ({sha[:8]}) moves production and test files "
                f"together but carries no `Guard-cmd:` trailer, so nothing can "
                f"check that the test goes red without the fix (doctrine 2.2). "
                f"This is a reminder, not a block. Add a trailer like:\n"
                f"  Guard-cmd: python -m pytest {test[0]} -q\n"
                f"Production: {', '.join(prod[:5])}"
                + (" ..." if len(prod) > 5 else ""))
        H.allow_silently()

    verdict, detail = verify(root, guard_cmd)
    record(mark)

    if verdict == DECORATION:
        H.emit({"decision": "block", "reason": H.cap(
            f"{H.MARKER} verify_guard says the guard on HEAD ({sha[:8]}) is "
            f"DECORATION: it stayed green with the production fix reverted, so "
            f"it has never been shown to fail (doctrine 2.2).\n\n{detail}\n\n"
            f"Guard-cmd: {guard_cmd}\nMake the guard fail without the fix, then "
            f"finish. Reverting the guard is also an answer - a test that cannot "
            f"fail is worse than no test, because it reads as coverage.", 9000)})

    if verdict == INCONCLUSIVE:
        H.allow_with_message(
            f"{H.MARKER} verify_guard returned INCONCLUSIVE for HEAD ({sha[:8]}) "
            f"- it could not tell whether the guard is real. This is NOT a pass "
            f"(doctrine 2.9); the check did not run to a verdict.\n{detail}\n"
            f"Guard-cmd: {guard_cmd}\nUsual causes: a dirty tree, a merge commit, "
            f"or a setup step the worktree needs. Re-run it yourself once the "
            f"tree is clean to get an answer.")

    H.allow_silently()


# ── selfcheck ───────────────────────────────────────────────────────────────

def selfcheck() -> bool:
    """Prove the trailer reader, the production/test split and the verdict
    partition can each fail. Every case has a negative side (doctrine 6.7)."""
    ok = True
    trailers = [
        ("fix\n\nGuard-cmd: pytest -q tests/x.py\n", "pytest -q tests/x.py"),
        ("fix\n\nGuard-cmd:   npm test  \n", "npm test"),
        ("fix\n\nGuard-cmd: a\nGuard-cmd: b\n", "b"),
        ("no trailer here\n", ""),
        ("mentions Guard-cmd in prose but not as a trailer\n", ""),
    ]
    for message, want in trailers:
        got = guard_cmd_of(message)
        if got != want:
            print(f"[verify-before-done] SELFCHECK FAILED: guard_cmd_of "
                  f"{message!r} = {got!r}, want {want!r}", file=sys.stderr)
            ok = False

    prod, test = split_paths([
        "app/billing.py", "tests/test_billing.py", "src/ui/Form.tsx",
        "src/ui/Form.test.tsx", "cypress/e2e/route.cy.ts", "README.md",
        "docs/design/x.md", "pkg/store_test.go",
    ])
    if sorted(prod) != ["app/billing.py", "src/ui/Form.tsx"]:
        print(f"[verify-before-done] SELFCHECK FAILED: production split = {prod}",
              file=sys.stderr)
        ok = False
    if len(test) != 4:
        print(f"[verify-before-done] SELFCHECK FAILED: test split = {test}",
              file=sys.stderr)
        ok = False

    for code, want in ((0, VERIFIED), (1, DECORATION), (2, INCONCLUSIVE)):
        run = H.run_guard("planted", [sys.executable, "-c", f"raise SystemExit({code})"],
                          Path.cwd(), VERIFY_CODES)
        if VERDICT_OF.get(run.status) != want:
            print(f"[verify-before-done] SELFCHECK FAILED: verify_guard exit {code} "
                  f"read as {run.status}, want {want}", file=sys.stderr)
            ok = False
    stray = H.run_guard("planted", [sys.executable, "-c", "raise SystemExit(5)"],
                        Path.cwd(), VERIFY_CODES)
    if stray.status != H.INSTRUMENT:
        print("[verify-before-done] SELFCHECK FAILED: exit 5 became "
              f"{stray.status}, not an instrument failure", file=sys.stderr)
        ok = False

    same = _marker("s", "/a/repo", "abc"), _marker("s", "/b/repo", "abc")
    if all(same) and same[0] == same[1]:
        print("[verify-before-done] SELFCHECK FAILED: two checkouts sharing a "
              "commit share a marker, so the second one goes silent while "
              "looking like a pass (R15-1).", file=sys.stderr)
        ok = False

    if ok:
        print("[verify-before-done] selfcheck OK: trailer reader (5 cases), "
              "production/test split (8 paths), verdict partition (4), "
              "marker key (1).")
    return ok


def main() -> None:
    argv = sys.argv[1:]
    H.reject_unknown_flags(argv, {"--selfcheck"})
    if "--selfcheck" in argv:
        raise SystemExit(0 if selfcheck() else 1)
    check(H.read_payload())


if __name__ == "__main__":
    H.main_guarded(main)
