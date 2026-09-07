# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
#!/usr/bin/env python3
"""Guard: a stage that touches a path another agent owns is refused (7.3).

7.3 has said "one worktree per agent, stage only named files, never
`git add -A`" since the beginning, and the sentence prevented neither
collision that paid for it: an agent's explicit `git add <file>` captured
another session's unstaged mid-edits to the same file, and a `git add -A`
swept a second project's untracked work into a robustness commit twice. A
rule in a file cannot see a path. This can.

The mechanism 7.3 names is a **file-ownership manifest**: each parallel
agent declares the paths it owns before it starts, and a stage that touches
a path owned by somebody else is refused rather than committed and
apologised for afterwards. Round 17 adopted the sentence and owed the guard
(register item B-16); this is the guard.

## The manifest

One owner per line: a name, a colon, then the globs that owner owns. Blank
lines and `#` comments are ignored. A line that is neither is REFUSED - a
manifest read halfway is worse than no manifest, because an owner silently
dropped owns nothing and every path they hold then reads as unowned (2.9).
Repeating an owner on a later line adds to their globs.

    # .sutradhar-owners
    round-20-guards:  python/sutradhar_guards/* python/tests/*
    round-20-records: docs/rounds/ CHANGELOG.md

A glob is matched with `fnmatch` against the path relative to the repository
root, so `*` crosses `/` and `docs/*` is the whole subtree; a pattern ending
in `/` is shorthand for the same thing. Both are said here rather than left
to be discovered, because an ownership pattern that matches wider than its
author meant refuses work that was never anyone else's, and a guard that
refuses honest work is muted within the week.

## The three answers, and the fourth

  * a path owned by ANOTHER owner: refused, with the owner named, exit 1.
  * a path owned by THIS owner: allowed.
  * a path owned by NOBODY: allowed, and COUNTED. Unowned is a real and
    common state - most of a repository is unowned on any given day - but a
    skipped path that is not counted is an exclusion the operator cannot
    see, which is the shape 6.7 warns about. The number is printed on
    every run, green or red.
  * a path owned by this owner AND another: allowed, and reported as a
    shared claim. Two agents who both believe they own a file will collide
    exactly the way B-16 did, so the overlap is said out loud rather than
    resolved silently in favour of whoever ran first.

A missing manifest is an **instrument condition, not a violation.** This
guard is opt-in; a repository that has declared no ownership has nothing
here to refuse, and a gate that blocked every repository without a manifest
would be uninstalled the same afternoon (R14-2). It says so by name and
exits 0. That is the one place where "could not measure" is deliberately
spelled the same as "did not fail", and the printed line is the whole of
what keeps it honest - a silent 0 here would be the empty-200 lie.

Usage:
    python ownership_lint.py --owner round-20-guards
    python ownership_lint.py --owner alice --manifest .sutradhar-owners a.py
    python ownership_lint.py --selfcheck

With no paths named it reads `git diff --cached --name-only`: the stage is
the thing 7.3 is about, and the moment before a commit is the last one at
which a collision is still cheap.

Exit 0 nothing refused (or no manifest), 1 a path belongs to another owner,
2 the check could not run - no owner named, an unknown flag, an unreadable
manifest, git unavailable. 2 is never a pass.
"""
from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
from pathlib import Path

#: Looked for at the repository root when --manifest is not given.
DEFAULT_MANIFEST = ".sutradhar-owners"

#: The environment variable an agent harness can set once per session, so a
#: hook does not have to be told the owner on every invocation.
OWNER_ENV = "SUTRADHAR_OWNER"


class OwnershipError(Exception):
    """The check could not run. Never a verdict on anybody's stage."""


#: True while `selfcheck()` is driving `main()`. Every other lint here runs
#: its selfcheck from `main` before scanning, and this one's selfcheck goes
#: THROUGH `main` (2.3 - the real seam is the CLI, and a case that pokes
#: `audit` directly cannot see a broken argument parser). Without this flag
#: those two facts are mutual recursion, and the first run of this file was
#: exactly that: a RecursionError, which is an absence of a verdict rather
#: than a verdict (6.11).
_IN_SELFCHECK = False


# ── the manifest ────────────────────────────────────────────────────────────

def parse_manifest(text: str, source: str = "") -> dict:
    """``{owner: [glob, ...]}``. Refuses what it cannot read exactly.

    The refusal is the point. An earlier shape of this guard skipped any
    line it did not understand, which meant a typo in an owner's line
    removed that owner from the manifest and turned every path they held
    into an unowned one - the guard reporting green over exactly the
    collision it exists to refuse.
    """
    where = source or "<manifest>"
    owners: dict = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise OwnershipError(
                "{}:{}: {!r} is neither a comment nor an "
                "`<owner>: <glob> ...` line. A row that cannot be read is "
                "refused and not skipped: an owner dropped by a typo owns "
                "nothing, and every path they hold then reads as unowned."
                .format(where, lineno, line))
        name, _, rest = line.partition(":")
        name = name.strip()
        globs = rest.split()
        if not name:
            raise OwnershipError(
                "{}:{}: a glob list with no owner in front of it. There is "
                "nobody for this guard to name in a refusal."
                .format(where, lineno))
        if not globs:
            raise OwnershipError(
                "{}:{}: owner {!r} is declared and owns no path. An owner "
                "who owns nothing refuses nothing, which is a declaration "
                "that reads as protection and is not."
                .format(where, lineno, name))
        owners.setdefault(name, []).extend(globs)
    return owners


def read_manifest(path: Path) -> dict:
    """Parse the manifest at ``path``. Raises OwnershipError if unreadable."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise OwnershipError(
            "cannot read the manifest at {}: {}: {}. That is this guard "
            "failing, not your stage.".format(path, type(exc).__name__, exc)
        ) from None
    return parse_manifest(text, source=str(path))


# ── matching ────────────────────────────────────────────────────────────────

def _normalise(path: str) -> str:
    p = str(path).replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def _matches(rel: str, pattern: str) -> bool:
    pat = _normalise(pattern)
    if pat.endswith("/"):
        pat += "*"
    return fnmatch.fnmatchcase(rel, pat)


def owners_of(path: str, manifest: dict) -> list:
    """Every owner in ``manifest`` whose globs claim ``path``, sorted."""
    rel = _normalise(path)
    return sorted(name for name, globs in manifest.items()
                  if any(_matches(rel, g) for g in globs))


def audit(paths, manifest: dict, owner: str) -> tuple:
    """``(refused, owned, unowned)`` for ``owner`` over ``paths``.

    ``refused`` and ``owned`` are ``(path, [owners])`` pairs so a caller can
    print WHO to talk to; ``unowned`` is plain paths, and it is returned
    rather than dropped because a count nobody prints is an exclusion the
    operator cannot see.
    """
    refused: list = []
    owned: list = []
    unowned: list = []
    for p in paths:
        rel = _normalise(p)
        if not rel:
            continue
        holders = owners_of(rel, manifest)
        if not holders:
            unowned.append(rel)
        elif owner in holders:
            owned.append((rel, holders))
        else:
            refused.append((rel, holders))
    return refused, owned, unowned


# ── the stage ───────────────────────────────────────────────────────────────

def staged_paths(repo: Path) -> list:
    """`git diff --cached --name-only`, or an OwnershipError naming git.

    6.8: an error branch must say WHOSE failure it is. A guard that cannot
    reach git has learned nothing about anybody's stage, and must not be
    able to say otherwise.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "diff", "--cached", "--name-only"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise OwnershipError(
            "could not run git in {}: {}: {}. This guard failed; nothing was "
            "read about your stage.".format(repo, type(exc).__name__, exc)
        ) from None
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip() or "(no stderr)"
        raise OwnershipError(
            "`git diff --cached --name-only` exited {} in {}: {}. That is "
            "git's failure or this guard's, and either way it is not a "
            "verdict on any path.".format(proc.returncode, repo, err))
    out = proc.stdout.decode("utf-8", "replace")
    return [line.strip() for line in out.splitlines() if line.strip()]


# ── selfcheck: the guard must be shown to refuse, and to allow ──────────────

_MANIFEST = (
    "# two agents, one tree\n"
    "alice: python/guards/* README.md\n"
    "\n"
    "bob:   js/\n"
)


def selfcheck() -> bool:
    """Known-good and known-bad for every claim (6.7 - evidence in pairs).

    Shapes are checked before they are indexed. A selfcheck that raises has
    reported nothing at all and takes the rest of the run down with it
    (6.11), and this file's own mutation run is where that would happen.
    """
    global _IN_SELFCHECK
    if _IN_SELFCHECK:
        return True
    _IN_SELFCHECK = True
    try:
        return _selfcheck_body()
    finally:
        _IN_SELFCHECK = False


def _selfcheck_body() -> bool:
    import tempfile

    problems: list = []

    def fail(msg: str) -> None:
        problems.append(msg)

    manifest = parse_manifest(_MANIFEST, "<selfcheck>")
    if sorted(manifest) != ["alice", "bob"]:
        fail("the manifest parsed to {}, not two owners; every case below "
             "would be measuring nothing".format(sorted(manifest)))
        for p in problems:
            print("[ownership-lint] SELFCHECK FAILED: {}".format(p))
        return False

    # 1. THE CASE IT MUST FAIL ON: somebody else's path in my stage.
    refused, owned, unowned = audit(["python/guards/a.py"], manifest, "bob")
    if len(refused) != 1:
        fail("a path owned by alice was not refused for bob: refused={} "
             "owned={} unowned={}".format(refused, owned, unowned))
    elif refused[0][1] != ["alice"]:
        fail("the refusal did not name the owner to talk to: {}"
             .format(refused[0]))

    # 2. My own path is mine.
    refused, owned, unowned = audit(["python/guards/a.py"], manifest, "alice")
    if refused or len(owned) != 1:
        fail("alice's own path was not allowed: refused={} owned={}"
             .format(refused, owned))

    # 3. An unowned path is allowed AND counted, never silently dropped.
    refused, owned, unowned = audit(["docs/notes.md"], manifest, "alice")
    if refused or owned or unowned != ["docs/notes.md"]:
        fail("an unowned path was not allowed and counted: refused={} "
             "owned={} unowned={}".format(refused, owned, unowned))

    # 4. The trailing-slash subtree shorthand actually covers the subtree.
    refused, _, _ = audit(["js/probe/core.mjs"], manifest, "alice")
    if len(refused) != 1 or refused[0][1] != ["bob"]:
        fail("`bob: js/` did not claim js/probe/core.mjs: {}".format(refused))

    # 5. An exact filename claims that file and not its neighbours.
    if owners_of("README.md", manifest) != ["alice"]:
        fail("an exact path in the manifest did not claim its file")
    if owners_of("README.md.bak", manifest) != []:
        fail("an exact path in the manifest claimed a neighbouring file too")

    # 6. A shared claim is allowed and visible.
    shared = parse_manifest("alice: shared/*\nbob: shared/*\n", "<selfcheck>")
    refused, owned, _ = audit(["shared/x.py"], shared, "alice")
    if refused or len(owned) != 1 or owned[0][1] != ["alice", "bob"]:
        fail("a path claimed by two owners did not report both: refused={} "
             "owned={}".format(refused, owned))

    # 7. Unreadable manifest rows are REFUSED, not skipped.
    for bad, label in (
        ("alice python/guards/*\n", "a line with no colon"),
        (": python/guards/*\n", "a glob list with no owner"),
        ("carol:\n", "an owner who owns nothing"),
    ):
        try:
            parse_manifest(bad, "<selfcheck>")
        except OwnershipError:
            pass
        else:
            fail("{} was accepted; a half-read manifest reports green over "
                 "the collision it exists to refuse".format(label))

    # 8. Through the CLI (2.3): a missing manifest is an absent instrument
    #    and not a violation, and a real foreign path is exit 1. The runs
    #    are captured rather than printed - a passing selfcheck that prints
    #    its own planted "FAIL" line reads as a failure, and a verdict's
    #    word is part of its correctness (6.9). Captured is not discarded:
    #    each exit code is asserted WITH the text that must accompany it,
    #    because a silent 0 is the empty-200 lie this guard is about.
    import contextlib
    import io

    def cli(args) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue() + err.getvalue()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rc, said = cli(["--owner", "bob", "--repo", str(root),
                        "--manifest", str(root / "nope"), "python/guards/a.py"])
        if rc != 0:
            fail("a missing manifest exited {}, not 0; this guard is opt-in "
                 "and has nothing to refuse in a repository that declared no "
                 "ownership".format(rc))
        if "no ownership manifest" not in said:
            fail("a missing manifest exited 0 without saying nothing was "
                 "checked; a silent 0 there cannot be told from a clean "
                 "stage: {!r}".format(said))
        (root / DEFAULT_MANIFEST).write_text(_MANIFEST, encoding="utf-8")
        rc, said = cli(["--owner", "bob", "--repo", str(root),
                        "python/guards/a.py"])
        if rc != 1:
            fail("the CLI exited {} on a path owned by another owner, not 1"
                 .format(rc))
        elif "python/guards/a.py" not in said or "alice" not in said:
            fail("the CLI refused without naming the path and the owner to "
                 "hand it back to: {!r}".format(said))
        rc, said = cli(["--owner", "bob", "--repo", str(root),
                        "js/probe/core.mjs", "docs/notes.md"])
        if rc != 0:
            fail("the CLI exited {} on bob's own path plus an unowned one, "
                 "not 0".format(rc))
        elif "1 unowned" not in said:
            fail("the unowned path was allowed without being counted, which "
                 "is an exclusion the operator cannot see: {!r}".format(said))

    for p in problems:
        print("[ownership-lint] SELFCHECK FAILED: {}".format(p))
    if not problems:
        print(
            "[ownership-lint] selfcheck ok: a path owned by another owner "
            "refused and the owner named, the owner's own path allowed, an "
            "unowned path allowed and counted, a `dir/` subtree shorthand "
            "matched, an exact filename not matching its neighbour, a shared "
            "claim reported with both owners, three unreadable manifest rows "
            "refused rather than skipped, and through the CLI: a missing "
            "manifest exits 0 as an absent instrument while a foreign path "
            "exits 1"
        )
    return not problems


# ── CLI ─────────────────────────────────────────────────────────────────────

_KNOWN_FLAGS = {"--owner", "--manifest", "--repo", "--selfcheck",
                "--help", "-h"}

_HELP = (
    "usage: ownership_lint.py [--owner NAME] [--manifest FILE] [--repo DIR]\n"
    "                        [PATH ...] | --selfcheck\n"
    "\n"
    "Refuses any named path owned in the manifest by an owner other than\n"
    "--owner (or $" + OWNER_ENV + "). With no PATH it reads the stage:\n"
    "`git diff --cached --name-only`.\n"
    "\n"
    "Exit 0 nothing refused (or no manifest), 1 a foreign path, 2 the check\n"
    "could not run. 2 is not a pass.\n"
)


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or "--selfcheck" in argv:
        return 0 if selfcheck() else 1
    if "-h" in argv or "--help" in argv:
        print(_HELP)
        print(__doc__)
        return 0

    owner = os.environ.get(OWNER_ENV, "")
    manifest_arg = None
    repo = Path.cwd()
    paths: list = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--owner":
            if i + 1 >= len(argv):
                print("[ownership-lint] --owner needs a name", file=sys.stderr)
                return 2
            owner = argv[i + 1]; i += 2
        elif a == "--manifest":
            if i + 1 >= len(argv):
                print("[ownership-lint] --manifest needs a path",
                      file=sys.stderr)
                return 2
            manifest_arg = Path(argv[i + 1]); i += 2
        elif a == "--repo":
            if i + 1 >= len(argv):
                print("[ownership-lint] --repo needs a path", file=sys.stderr)
                return 2
            repo = Path(argv[i + 1]); i += 2
        elif a.startswith("-"):
            # Refused, never ignored: a dropped flag makes exit 0 a statement
            # about the import and nothing else (R17-2).
            if a not in _KNOWN_FLAGS:
                print("[ownership-lint] unknown flag: {}".format(a),
                      file=sys.stderr)
                return 2
            i += 1
        else:
            paths.append(a); i += 1

    if not owner.strip():
        print(
            "[ownership-lint] no owner: pass --owner NAME or set ${}. "
            "Without one there is nobody to compare the manifest against, "
            "and nothing was checked - which is not a pass (2.9)."
            .format(OWNER_ENV), file=sys.stderr)
        return 2

    if not selfcheck():
        return 1

    manifest_path = manifest_arg if manifest_arg is not None \
        else repo / DEFAULT_MANIFEST
    if not manifest_path.is_file():
        # Opt-in, and it says so. A silent 0 here would be the empty-200 lie.
        print(
            "[ownership-lint] no ownership manifest at {}. Nothing was "
            "checked: this guard is opt-in, and a repository that has "
            "declared no ownership has no foreign path for it to refuse. "
            "Write one (`<owner>: <glob> ...`, one owner per line) to turn "
            "it on.".format(manifest_path))
        return 0

    try:
        manifest = read_manifest(manifest_path)
        named = list(paths)
        if not named:
            named = staged_paths(repo)
    except OwnershipError as exc:
        print("[ownership-lint] {}".format(exc), file=sys.stderr)
        return 2

    if not manifest:
        print(
            "[ownership-lint] the manifest at {} declares no owner. An empty "
            "manifest and a satisfied one look identical from here, so this "
            "is a refusal rather than a pass (2.9).".format(manifest_path),
            file=sys.stderr)
        return 2

    if not named:
        print(
            "[ownership-lint] nothing staged in {} and no path named - "
            "nothing was checked. Not a finding, and not a pass either."
            .format(repo))
        return 0

    refused, owned, unowned = audit(named, manifest, owner)
    shared = [(p, hs) for p, hs in owned if len(hs) > 1]

    print("[ownership-lint] owner {!r}, manifest {} ({} owner(s)), {} "
          "path(s) checked".format(owner, manifest_path, len(manifest),
                                   len(named)))
    print("[ownership-lint] {} yours, {} unowned, {} owned by somebody else"
          .format(len(owned), len(unowned), len(refused)))
    for path, holders in shared:
        print("[ownership-lint] shared claim: {} is owned by {} as well as "
              "by you - two agents who both believe they own a file collide "
              "exactly the way this guard exists to stop"
              .format(path, ", ".join(h for h in holders if h != owner)))

    if refused:
        print()
        for path, holders in refused:
            print("FAIL {}: owned by {}, not by {!r}. Hand it back, or agree "
                  "the change with them and move the glob - do not stage it."
                  .format(path, ", ".join(holders), owner), file=sys.stderr)
        print()
        print("[ownership-lint] {} path(s) belong to another owner. 7.3: an "
              "explicit `git add` on a shared tree is not protection, and "
              "this is the refusal that is.".format(len(refused)),
              file=sys.stderr)
        return 1

    print("[ownership-lint] OK - no path in this set belongs to another "
          "owner.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
