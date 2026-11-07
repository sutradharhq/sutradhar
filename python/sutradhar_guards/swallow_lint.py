#!/usr/bin/env python3
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Guard: flag exception handlers that silently swallow errors.

A "silent swallow" is an ``except`` handler that catches broadly
(``except:``, ``except Exception``, ``except BaseException``) and whose body
neither logs, nor re-raises, nor calls an explicit degrade function - yet
returns an empty value (``None``, ``[]``, ``{}``, ``""``, ``0``, ``False``)
or consists only of ``pass`` / ``continue``.

Why this matters: a swallowed exception converts an outage into a lie. The
incident that earned this guard: a fleet-wide datastore failure was
swallowed into ``{}``, which downstream code read as "an event-free fleet",
flipping a detector's verdict for every entity at once - under a green
status, cached for the full TTL.

This is a RATCHET, not a big bang. A per-file baseline records today's
swallow counts; the gate fails only when a file EXCEEDS its baseline (a new
silent swallow) or a non-baselined file introduces one. The baseline can
only shrink: fix a swallow, rerun ``--update-baseline``, and the floor
drops. You can adopt this on a codebase with hundreds of existing swallows
on day one and still never regress.

A baseline in the same diff as the code it excuses is no ratchet: a change
can add a swallow and record it in one step, and the gate reads its own new
floor. ``--base-baseline FILE`` names the base branch's copy of the baseline;
an entry the current baseline adds, or a count it raises, against that copy
is a finding (B-64, after Perplexity SPACE's archcheck). Lowering or removing
an entry is silent. The GitHub Action passes the base copy on pull requests.

Usage:
    python swallow_lint.py src/                     # gate against baseline
    python swallow_lint.py src/ --update-baseline   # record today's floor
    python swallow_lint.py src/ --base-baseline base.json  # also: no growth
    python swallow_lint.py --selfcheck              # prove the detector works

Exit 0 no swallow beyond the baseline, 1 a new swallow, 2 the check could
not run: an unknown flag, or paths that hold no Python file at all. 2 is not
a pass. A scan that read nothing used to print ``OK (0 files ...)`` and exit
0, so a CI step pointed at a directory with no Python in it - most often the
template's ``src/`` in a tree that keeps its code somewhere else - reported
green on every run and had checked nothing (R21-2). That is the lie this
guard exists to catch, told by the guard about itself.

The detector is AST-based: it sees bare ``except:``, tuple handlers that
include Exception, and bodies of any length. Intentional swallows (there
are legitimate ones: "metrics must never break the request") stay in the
baseline with a comment at the site explaining why.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

# Directory names that are never the adopter's own source. Excluded from the
# WALK (not from an explicitly named path - see _is_vendor). A guard whose
# real findings are buried under third-party ones has been switched off by
# noise rather than by decision: the scar is a repo where ~80 findings inside
# `.venv` hid the one in `app/`, and the guard was disabled that afternoon.
VENDOR_DIRS = frozenset({
    "__pycache__", ".venv", "venv", ".tox", ".nox", "node_modules",
    "site-packages", ".git", ".hg", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".eggs",
})

BROAD_TYPES = {"Exception", "BaseException"}
LOG_METHODS = {"warning", "error", "info", "debug", "exception", "critical", "log"}
# Function names that make a swallow explicit rather than silent. Extend with
# --allow-call NAME for project-specific degrade helpers.
DEGRADE_CALLS = {"degrade", "record_failure", "capture_exception"}

EMPTY_RETURNS = {None, "", 0, 0.0, False}


def _is_broad_handler(handler: ast.ExceptHandler) -> bool:
    """True for ``except:``, ``except Exception``, ``except (A, Exception)``."""
    t = handler.type
    if t is None:
        return True
    names = t.elts if isinstance(t, ast.Tuple) else [t]
    for n in names:
        leaf = n.attr if isinstance(n, ast.Attribute) else getattr(n, "id", "")
        if leaf in BROAD_TYPES:
            return True
    return False


def _is_empty_value(node: ast.expr | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Constant):
        v = node.value
        # NB: `v in EMPTY_RETURNS` would treat 0/False/"" via equality; that
        # is exactly what we want (all falsy empties), but None needs identity.
        return v is None or v in ("", 0, 0.0, False)
    if isinstance(node, (ast.List, ast.Tuple)) and not node.elts:
        return True
    if isinstance(node, ast.Dict) and not node.keys:
        return True
    return False


def _handler_swallows(handler: ast.ExceptHandler, extra_calls: set[str]) -> bool:
    has_log = False
    has_raise = False
    has_degrade = False
    has_empty_exit = False
    only_noise = True

    allowed_calls = DEGRADE_CALLS | extra_calls

    for stmt in handler.body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Raise):
                has_raise = True
            elif isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Attribute) and f.attr in LOG_METHODS:
                    has_log = True
                elif isinstance(f, ast.Name) and f.id in allowed_calls:
                    has_degrade = True
                elif isinstance(f, ast.Attribute) and f.attr in allowed_calls:
                    has_degrade = True

    for stmt in handler.body:
        if isinstance(stmt, (ast.Pass, ast.Continue)):
            has_empty_exit = True
        elif isinstance(stmt, ast.Return) and _is_empty_value(stmt.value):
            has_empty_exit = True
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            pass  # docstring / bare literal - noise
        else:
            only_noise = False

    if has_log or has_raise or has_degrade:
        return False
    if has_empty_exit:
        return True
    # A body of only noise statements (no return, no work) is a swallow too.
    return only_noise and len(handler.body) > 0


def check_source(source: str, extra_calls: set[str] | None = None) -> list[int]:
    """Return line numbers of silent swallows in ``source``. Raises
    NotJudged when it does not parse: no swallows is a clean answer, and an
    unparsable file has not been given one (R24-27)."""
    tree = _parse(source)
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _is_broad_handler(node):
            if _handler_swallows(node, extra_calls or set()):
                hits.append(node.lineno)
    return hits


def check_file(path: Path, extra_calls: set[str] | None = None) -> list[int]:
    return check_source(read_source(path), extra_calls)


# ── selfcheck: the guard must be shown to fail ──────────────────────────────
# A detector that cannot flag a planted known-bad case is decoration. Run
# with --selfcheck in CI so a future edit cannot silently lobotomize it.

_KNOWN_BAD = '''
def f():
    try:
        risky()
    except Exception:
        return {}

def g():
    try:
        risky()
    except:
        pass
'''

_KNOWN_GOOD = '''
def f():
    try:
        risky()
    except Exception as exc:
        log.warning(f"degraded: {exc}")
        return {}

def g():
    try:
        risky()
    except Exception:
        raise
'''


#: `main` runs the selfcheck before it scans, and the selfcheck drives `main`
#: to prove the CLI refuses an empty scan - two correct decisions that are
#: mutual recursion without this flag (R20-1, where `ownership_lint`'s first
#: run was a RecursionError rather than a verdict).
_IN_SELFCHECK = False


def selfcheck() -> bool:
    global _IN_SELFCHECK
    if _IN_SELFCHECK:
        return True
    _IN_SELFCHECK = True
    try:
        return _selfcheck_body()
    finally:
        _IN_SELFCHECK = False


def _selfcheck_body() -> bool:
    import contextlib
    import io
    import tempfile

    problems: list[str] = []
    bad = check_source(_KNOWN_BAD)
    good = check_source(_KNOWN_GOOD)
    if not (len(bad) == 2 and len(good) == 0):
        problems.append(f"bad={bad} good={good}")

    # Through the CLI, in a pair (6.7): a directory with no Python file must
    # be refused with 2 AND say so, and one clean file must pass, or the
    # refusal could be refusing everything and still look right.
    def cli(args: list[str]) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(args)
        return code, out.getvalue() + err.getvalue()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "README.md").write_text("no python here\n", encoding="utf-8")
        args = [str(root), "--baseline", str(root / "none.json")]
        rc, said = cli(args)
        if rc != 2 or "nothing was scanned" not in said:
            problems.append(
                f"a directory with no Python file exited {rc}, not 2 with a "
                f"'nothing was scanned' line; an OK over zero files is a pass "
                f"for a check that never ran: {said!r}"
            )
        (root / "clean.py").write_text("x = 1\n", encoding="utf-8")
        rc, said = cli(args)
        if rc != 0:
            problems.append(
                f"one clean file exited {rc}, not 0; the empty-scan refusal "
                f"would be refusing everything: {said!r}"
            )

    # B-64, in a pair: a baseline that grew against the base branch's copy
    # is a finding, and the same baseline against an equal copy passes, or
    # the growth check could be failing everything. An unreadable base copy
    # is could-not-run, never an empty floor that makes everything "added".
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "clean.py").write_text("x = 1\n", encoding="utf-8")
        cur, base = root / "cur.json", root / "base.json"
        cur.write_text('{"clean.py": 1}', encoding="utf-8")
        args = [str(root), "--baseline", str(cur), "--base-baseline", str(base)]
        for base_text, want in (("{}", 1), ('{"clean.py": 1}', 0),
                                ('{"clean.py": 0}', 1), ("not json", 2)):
            base.write_text(base_text, encoding="utf-8")
            rc, said = cli(args)
            if rc != want:
                problems.append(f"baseline {{'clean.py': 1}} against base "
                                f"copy {base_text!r} exited {rc}, not {want}: "
                                f"{said!r}")

    # R24-27, two pairs: a byte-order mark does not hide a finding (the BOM
    # twin finds what the plain twin finds), and a file that does not parse
    # is NOT check_fileD - never the empty list a clean file returns.
    with tempfile.TemporaryDirectory() as td:
        plain, bom, broken = (Path(td) / n for n in ("p.py", "b.py", "x.py"))
        plain.write_text(_KNOWN_BAD, encoding="utf-8")
        bom.write_bytes(b"\xef\xbb\xbf" + _KNOWN_BAD.encode("utf-8"))
        broken.write_text("def (:\n", encoding="utf-8")
        want = check_file(plain)
        try:
            got = check_file(bom)
        except NotJudged as exc:
            # A selfcheck that raises has reported nothing (6.11): the
            # failure is a named problem, never a traceback.
            got = f"not judged ({exc})"
        if not want or got != want:
            problems.append(
                f"a byte-order mark changed the verdict: plain {want}, "
                f"BOM-prefixed {got}"
            )
        try:
            got = check_file(broken)
            problems.append(f"an unparsable file was judged, as {got!r}, "
                            f"instead of named as not judged")
        except NotJudged:
            pass

    for p in problems:
        print(f"[swallow-lint] SELFCHECK FAILED: {p}")
    if not problems:
        print(
            "[swallow-lint] selfcheck ok: silent swallow caught, handled "
            "exception passed, a directory with no Python file refused with "
            "exit 2, one clean file passed, a baseline grown against the base "
            "branch's copy flagged and an equal one passed, a BOM-prefixed "
            "swallow found as the plain one is, an unparsable file not judged"
        )
    return not problems


# ── CLI ─────────────────────────────────────────────────────────────────────

def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(p)
    except (OSError, RuntimeError):
        # A symlink loop cannot be resolved; it is named by the path it was
        # reached at, because it is reported as not judged (R24-28).
        return str(p)


class NotJudged(Exception):
    """A file the walk reached and could not judge, with the reason (R24-27).

    Raised, never answered with an empty list: no findings is what a clean
    file returns, and a file that did not parse - a byte-order mark read as
    a character, a NUL byte, syntax newer than the running interpreter -
    used to return exactly that. Three bytes at the top of a file hid every
    finding in it under a pass (2.9 at file granularity).
    """


def _parse(source: str) -> "ast.AST":
    """The tree, or NotJudged saying why there is none."""
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        if isinstance(exc, SyntaxError):
            at = f" at line {exc.lineno}" if exc.lineno else ""
            why = f"SyntaxError{at}: {exc.msg}"
        else:
            why = f"{type(exc).__name__}: {exc}"
        raise NotJudged(f"does not parse under this Python ({why})") from None


def read_source(path: Path) -> str:
    """The file's text as the interpreter reads it. `utf-8-sig`, so a leading
    byte-order mark is dropped - Python imports such a file, and read as
    `utf-8` the mark reached the parser as a character it refuses (R24-27)."""
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise NotJudged(f"could not be read ({type(exc).__name__}: "
                        f"{exc.strerror or exc})") from None


def _walk(paths: list, vendor=None) -> tuple:
    """(named, walked, symlinked dirs, unjudged, vendor-skipped .py count).

    One walk, and nothing it passes over is silent (R24-28, R24-29). A
    directory named like `fixtures.py` is a directory, not a file to read.
    A symlink named `.py` that does not resolve - a loop, a dangling link -
    and a `.py` that is not a regular file - a FIFO would block the read -
    are unjudged with the reason, never a crash or a hang of the instrument. A
    symlinked directory is not descended (the walk never followed them) and
    is now returned so the caller says so. Files named on the command line
    are taken as named.
    """
    import os

    named: list = []
    walked: list = []
    linked_dirs: list = []
    unjudged: list = []
    skipped_vendor = 0
    for root in paths:
        if root.is_file() and root.suffix == ".py":
            named.append(root)
            continue
        for here, dirnames, filenames in os.walk(root):
            dirnames.sort()
            base = Path(here)
            for d in dirnames:
                p = base / d
                if os.path.islink(p) and not (vendor and vendor(p, root)):
                    linked_dirs.append(p)
            for name in sorted(filenames):
                if not name.endswith(".py"):
                    continue
                f = base / name
                if "__pycache__" in f.parts:
                    continue
                if vendor and vendor(f, root):
                    skipped_vendor += 1
                    continue
                if f.is_symlink():
                    try:
                        target = f.resolve(strict=True)
                    except (OSError, RuntimeError) as exc:
                        unjudged.append((f, f"is a symlink that does not "
                                            f"resolve ({type(exc).__name__})"))
                        continue
                    if target.is_dir():
                        linked_dirs.append(f)
                        continue
                    if not target.is_file():
                        unjudged.append((f, "is a symlink to something that "
                                            "is not a regular file"))
                        continue
                elif not f.is_file():
                    # A FIFO or socket named `.py`: reading it would block
                    # or fail, so it is named, never read (R24-28).
                    unjudged.append((f, "is not a regular file"))
                    continue
                walked.append(f)
    return named, walked, linked_dirs, unjudged, skipped_vendor


def load_counts(path: Path) -> dict:
    """A swallow baseline: ``{file: count}``. Raises ValueError saying why
    it is not one, so a malformed file is "could not run", never an empty
    floor."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(data, dict) or not all(
            isinstance(k, str) and type(v) is int and v >= 0
            for k, v in data.items()):
        raise ValueError(f"{path}: not an object of file -> count")
    return data


def baseline_growth(current: dict, base: dict) -> list:
    """What ``current`` allows beyond ``base``, the base branch's copy: an
    added entry or a raised count, one line each (B-64). Lowered and removed
    entries are the ratchet working and are not listed."""
    grown = []
    for rel, n in sorted(current.items()):
        was = base.get(rel)
        if was is None:
            grown.append(f"{rel}: added with {n}")
        elif n > was:
            grown.append(f"{rel}: raised from {was} to {n}")
    return grown


def _verdict(found: bool, unjudged: bool) -> int:
    """1 a finding, else 2 a file not judged, else 0 (R24-27). A finding is
    a verdict that holds whatever the unjudged files contain, and must not
    be lowered to 2: under the Action's `on-cannot-run: skip` a 2 is a pass,
    so one unparsable file beside a real finding would have hidden it."""
    return 1 if found else 2 if unjudged else 0


def _say_walk(tag: str, linked_dirs: list) -> None:
    if linked_dirs:
        shown = ", ".join(str(p) for p in linked_dirs[:5])
        more = f" and {len(linked_dirs) - 5} more" if len(linked_dirs) > 5 else ""
        print(f"[{tag}] did not descend {len(linked_dirs)} symlinked "
              f"director(ies): {shown}{more}; name the target directory to "
              f"scan it")


def _say_unjudged(tag: str, unjudged: list, show, decides: bool) -> None:
    """Name every file not judged. When it decides the exit (2), the last
    stderr line says so, because that is the line a caller quotes."""
    if not unjudged:
        return
    print(f"[{tag}] {len(unjudged)} file(s) NOT JUDGED - reached, not "
          f"checked, and not counted as clean (2.9):")
    for f, why in unjudged:
        print(f"  {show(f)}: {why}")
    if decides:
        names = ", ".join(show(f) for f, _ in unjudged[:3])
        print(f"[{tag}] could not judge {len(unjudged)} file(s) ({names}"
              f"{', ...' if len(unjudged) > 3 else ''}): this is not a pass "
              f"(2.9). Fix the file, remove it from the scanned paths, or "
              f"run the guard under a Python that parses it.",
              file=sys.stderr)


def _read_once(named: list, walked: list, roots: list) -> tuple:
    """(files to read, symlinks skipped because they leave the scan).

    A file reached twice - a symlink and its target, or two overlapping
    paths - is read once (R24-23). Read twice, its findings arrived twice,
    and in conflated_degrade_lint the duplicate key was an exit 2 that the
    Action's `on-cannot-run: skip` turned into a pass. Real files are taken
    before links, so a finding carries the file's own name. Files named on
    the command line are read as named. A symlinked file found by walking a
    directory, whose target lies outside every directory scanned, is
    skipped and counted rather than followed: the paths are the adopter's
    statement of what their source is, and a link out of them would let the
    tree under review choose what gets read.
    """
    dirs = [r.resolve() for r in roots if r.is_dir()]
    links = [f for f in walked if f.is_symlink()]
    ordered = ([(f, False) for f in named]
               + [(f, False) for f in walked if not f.is_symlink()]
               + [(f, True) for f in links])
    out: list = []
    seen: set = set()
    outside = 0
    for f, is_link in ordered:
        target = f.resolve()
        if is_link and not any(target == d or d in target.parents for d in dirs):
            outside += 1
            continue
        if target in seen:
            continue
        seen.add(target)
        out.append(f)
    return out, outside


def _is_vendor(path: Path, root: Path) -> bool:
    """True when ``path`` sits under a vendor directory BELOW ``root``.

    Judged relative to the root the caller named, so
    ``swallow_lint.py .venv/pkg`` still scans it - an explicitly named path is
    always honoured and only the recursive walk excludes. Without that
    asymmetry, pointing the guard at a vendor tree on purpose would print OK
    over a directory nothing had read (2.4).
    """
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return any(
        part in VENDOR_DIRS or part.endswith(".egg-info")
        for part in rel.parts[:-1]
    )


_KNOWN_FLAGS = {
    "--allow-call", "--baseline", "--base-baseline", "--selfcheck",
    "--update-baseline",
    "--include-vendor", "--help", "-h",
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--selfcheck" in argv:
        return 0 if selfcheck() else 1

    update = "--update-baseline" in argv
    include_vendor = "--include-vendor" in argv
    baseline_path = Path("swallow_baseline.json")
    base_path: "Path | None" = None
    extra_calls: set[str] = set()
    paths: list[Path] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--baseline", "--base-baseline", "--allow-call") and i + 1 >= len(argv):
            print(f"[swallow-lint] {a} needs a value", file=sys.stderr)
            return 2
        if a == "--baseline":
            baseline_path = Path(argv[i + 1]); i += 2
        elif a == "--base-baseline":
            base_path = Path(argv[i + 1]); i += 2
        elif a == "--allow-call":
            extra_calls.add(argv[i + 1]); i += 2
        elif a.startswith("--"):
            # An unrecognised flag must NOT be ignored. Silently
            # skipping it means a typo like `--selfchek` runs the
            # default scan and exits 0, which reads as a pass.
            if a not in _KNOWN_FLAGS:
                print(
                    f"[swallow-lint] unknown flag: {a}", file=sys.stderr
                )
                return 2
            i += 1
        else:
            paths.append(Path(a)); i += 1
    defaulted = not paths
    if not paths:
        paths = [Path("src")]

    if update and base_path is not None:
        print("[swallow-lint] --base-baseline checks a baseline and "
              "--update-baseline writes one; they are not combined.",
              file=sys.stderr)
        return 2

    if not selfcheck():
        return 1

    # B-64: read both baselines before scanning, so a base copy that cannot
    # be read stops the run as could-not-run instead of judging growth
    # against nothing.
    grown: list = []
    if base_path is not None:
        try:
            base_counts = load_counts(base_path)
            current = (load_counts(baseline_path)
                       if baseline_path.exists() else {})
        except ValueError as exc:
            print(f"[swallow-lint] cannot compare the baseline with the base "
                  f"branch's copy: {exc}. Nothing was judged (2.9).",
                  file=sys.stderr)
            return 2
        grown = baseline_growth(current, base_counts)

    named, walked, linked_dirs, unjudged, skipped_vendor = _walk(
        paths, None if include_vendor else _is_vendor)
    py_files, outside = _read_once(named, walked, paths)
    _say_walk("swallow-lint", linked_dirs)
    if outside:
        print(
            f"[swallow-lint] skipped {outside} symlinked file(s) whose target "
            f"is outside the scanned path(s); name the target's directory to "
            f"scan it"
        )

    # Say what was NOT read. An exclusion the operator cannot see is the same
    # class of lie the guard exists to catch: "OK" over an unscanned tree.
    if skipped_vendor:
        print(
            f"[swallow-lint] skipped {skipped_vendor} file(s) under vendor "
            f"directories ({', '.join(sorted(VENDOR_DIRS)[:4])}, ...); "
            f"pass --include-vendor to scan them"
        )

    # Zero files read is "could not measure", never "no new swallow" (2.9),
    # and that holds for --update-baseline too: a floor recorded over
    # nothing is a floor of nothing. Refused before either branch, with the
    # paths named and the sentence that says what to change (R21-2).
    if not py_files and not unjudged:
        states = ", ".join(
            f"{p} ({'does not exist' if not p.exists() else 'is not a .py file' if p.is_file() else 'holds no .py file'})"
            for p in paths
        )
        print(
            f"[swallow-lint] nothing was scanned: {states}"
            + ("; no path was given, so src/ was assumed" if defaulted else "")
            + (f"; the {skipped_vendor} .py file(s) found are all under vendor "
               f"directories, and --include-vendor scans them"
               if skipped_vendor else "")
            + ". This is not a pass (2.9). Name the directory that holds your "
            "Python source; a repository with no Python has nothing for this "
            "guard to read, so remove its CI step rather than keep a check "
            "that cannot run.",
            file=sys.stderr,
        )
        return 2

    counts: dict[str, int] = {}
    lines_by_file: dict[str, list[int]] = {}
    for f in py_files:
        try:
            found = check_file(f, extra_calls)
        except NotJudged as exc:
            unjudged.append((f, str(exc)))
            continue
        if found:
            counts[_rel(f)] = len(found)
            lines_by_file[_rel(f)] = found
    not_judged = {_rel(f) for f, _ in unjudged}

    if update and unjudged:
        # A floor recorded without these files would re-flag every swallow
        # in them as new the day they parse; refused, not written.
        _say_unjudged("swallow-lint", unjudged, _rel, True)
        print("[swallow-lint] baseline NOT written: it would be a floor "
              "that silently leaves these files out.", file=sys.stderr)
        return 2
    if update:
        baseline_path.write_text(
            json.dumps(dict(sorted(counts.items())), indent=2) + "\n"
        )
        print(
            f"[swallow-lint] baseline written: {baseline_path} "
            f"({sum(counts.values())} swallows across {len(counts)} files)"
        )
        return 0

    baseline: dict[str, int] = {}
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text())

    regressions: list[str] = []
    for rel, n in counts.items():
        allowed = baseline.get(rel, 0)
        if n > allowed:
            for lineno in lines_by_file[rel]:
                regressions.append(f"  {rel}:{lineno}")
            regressions.append(
                f"    -> {rel}: {n} swallow(s), baseline {allowed}. "
                f"Log, degrade explicitly, or raise; "
                f"--update-baseline only if genuinely intentional."
            )

    # The other half of the ratchet: a baselined file that improved should
    # bank the improvement, or the floor silently stops meaning anything.
    improved = [
        rel for rel, allowed in baseline.items()
        if counts.get(rel, 0) < allowed and rel not in not_judged
    ]

    code = _verdict(bool(regressions or grown), bool(unjudged))
    if regressions:
        print("\n[swallow-lint] NEW silent swallow(s) beyond baseline:\n")
        print("\n".join(regressions))
        print()
    if grown:
        print(f"\n[swallow-lint] the baseline GREW against the base branch's "
              f"copy ({base_path}); a change cannot raise the floor it is "
              f"judged against (2.1, B-64):\n")
        print("\n".join(f"  {g}" for g in grown))
        print("\nFix the swallow, or land the baseline change on its own "
              "where it is reviewed as one.\n")
    _say_unjudged("swallow-lint", unjudged, _rel, code == 2)
    if code:
        return code

    msg = (
        f"[swallow-lint] OK ({len(py_files)} files, "
        f"{sum(baseline.values())} baselined swallow(s) - ratchet only shrinks)"
    )
    if improved:
        msg += (
            f"\n[swallow-lint] {len(improved)} file(s) improved below baseline - "
            f"run --update-baseline to bank the lower floor: "
            + ", ".join(sorted(improved)[:5])
        )
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
