#!/usr/bin/env python3
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Guard: a failed read must not be spelled the same as an empty one.

Doctrine 2.4 says a failure states itself, and 2.7 says an ``except`` block
logs, degrades explicitly, or re-raises. ``swallow_lint.py`` catches the LOUD
half of that - a handler that logs nothing. This catches the quiet half it
structurally cannot see: a handler that DOES log, and returns the same value
some legitimate "there is nothing here" path in the same function returns.
The log line exists, the caller still cannot tell the two apart, and every
number computed downstream is computed over an unknown fraction of reality
under a green status.

*Scar: three instances in one private build thread, all found by hand and
none by a guard. A read that hit a corrupt key returned the same "no
baseline" value as a read that found nothing, so a partial corruption still
reported success while the affected records silently dropped a boundary
interval. An absent timestamp and an unreadable one both collapsed to an idle
state, and idle raises no alert. A failed lookup fail-safed to `{}`, which is
indistinguishable from "nothing to report", so one dependency blip made a
fleet-wide verdict read clean.*

WHAT IS FLAGGED: a function whose ``except`` handler returns a falsy literal
(``None`` / ``{}`` / ``[]`` / ``0`` / ``False`` / ``""``) that some
NON-exception path in the same function also returns.

**The fix is not "raise instead."** The fail-safe value is usually right -
that is why it was chosen. The silence is the defect. Make the two
distinguishable: return a ``(value, ok)`` pair, set a counter the caller
reads, or carry a status/reason it must look at. A guard that pushed every
one of these into a raise would be traded for an outage, and then removed.

RATCHET: a baseline of today's conflations, which may only shrink. A NEW
conflation fails the gate; a banked entry that has since been separated also
fails, with "bank it" - the floor drops monotonically and a silently-fixed
entry cannot linger as a hole nothing re-checks. A conflation that is real
and intended - two paths that genuinely mean the same thing to every caller,
such as "this was a notification, there is no reply" - stays in the baseline
with a comment at the site saying why, exactly as ``swallow_lint`` handles
the swallows a project means.

THE KEY is ``path::qualified_name`` and never a line number. The qualified
name carries the enclosing class for a method (``Cls.method``) and the
enclosing function for a nested def (``outer.inner``); a later same-named
sibling in one file gets ``#2``, ``#3`` in source order, so adding a second
``read`` never changes the first one's key. A baseline keyed on a position
re-flags what it already banked the first time anybody edits above it, and
the only quick way out is ``--update-baseline``, which banks the real new
findings too (R18-1, and see ``ratchet.py`` for the contract).

Usage:
    python conflated_degrade_lint.py src/                    # gate
    python conflated_degrade_lint.py src/ --update-baseline  # record the floor
    python conflated_degrade_lint.py src/ --base-baseline base.json  # no growth
    python conflated_degrade_lint.py --selfcheck             # prove it works

Exit 0 at or below the floor, 1 a new conflation or an unbanked fix, 2 the
check could not run: an unknown flag, no path, a duplicate key, or paths
that hold no Python file at all. 2 is not a pass. Named paths that held
nothing used to print ``OK (0 file(s) ...)`` and exit 0, which refused the
default directory nobody named and then accepted a named one nobody could
read (R21-2).

The ratchet is implemented here rather than imported from ``ratchet.py`` for
the same reason ``swallow_lint.py`` does it: these files are copy-in and land
in different directories in an adopter's tree, so a cross-module import would
break for them and not for us.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import NamedTuple

# Directory names that are never the adopter's own source, excluded from the
# WALK and not from an explicitly named path (see `_is_vendor`). Mirrors
# `swallow_lint.py` deliberately: a guard whose real findings are buried
# under third-party ones has been switched off by noise rather than by
# decision (B-2).
VENDOR_DIRS = frozenset({
    "__pycache__", ".venv", "venv", ".tox", ".nox", "node_modules",
    "site-packages", ".git", ".hg", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".eggs",
})


class Conflation(NamedTuple):
    """One function that cannot tell a failure from an absence.

    ``key`` is what the baseline stores and carries no position; ``line`` is
    where it is today, printed for the reader and never banked.
    """

    key: str
    line: int
    path: str
    qualname: str

    @property
    def message(self) -> str:
        return (
            f"{self.path}:{self.line} {self.qualname} returns the same value "
            f"on failure as on a legitimate empty result"
        )

    def __str__(self) -> str:
        return self.key


# ── the detector ────────────────────────────────────────────────────────────

def _falsy_literal(node: ast.AST | None) -> str | None:
    """A canonical tag for a falsy literal return, else None.

    Two returns conflate only when their tags match, so `{}` and `None` are
    different answers and are left alone.
    """
    if node is None:
        return "None"                       # a bare `return`
    if isinstance(node, ast.Constant) and node.value in (None, 0, False, ""):
        return repr(node.value)
    if isinstance(node, ast.Dict) and not node.keys:
        return "{}"
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)) and not node.elts:
        return "[]"
    return None


def _falsy_returns_in(node: ast.AST) -> set:
    """Falsy-literal return tags anywhere in this subtree."""
    return {
        tag
        for child in ast.walk(node)
        if isinstance(child, ast.Return)
        for tag in (_falsy_literal(child.value),)
        if tag is not None
    }


def conflates(fn) -> bool:
    """True when a handler's fail-safe value is also a normal return value."""
    handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
    handler_tags: set = set()
    for h in handlers:
        handler_tags |= _falsy_returns_in(h)
    if not handler_tags:
        return False
    handler_nodes = {id(x) for h in handlers for x in ast.walk(h)}
    normal_tags = {
        _falsy_literal(n.value)
        for n in ast.walk(fn)
        if isinstance(n, ast.Return) and id(n) not in handler_nodes
    } - {None}
    return bool(handler_tags & normal_tags)


def functions_with_qualnames(tree: ast.AST) -> list:
    """Every ``def`` in source order with its qualified name.

    ``Cls.method`` for a method, ``outer.inner`` for a nested def, then
    ``#2``, ``#3`` on any later duplicate of a qualified name already seen in
    this file - so a second ``read`` takes a new key and leaves the first
    one's alone.
    """
    out: list = []

    def visit(node: ast.AST, stack: tuple) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append((".".join(stack + (child.name,)), child))
                visit(child, stack + (child.name,))
            elif isinstance(child, ast.ClassDef):
                visit(child, stack + (child.name,))
            else:
                visit(child, stack)

    visit(tree, ())
    seen: dict = {}
    named: list = []
    for qual, fn in out:
        n = seen.get(qual, 0) + 1
        seen[qual] = n
        named.append((qual if n == 1 else f"{qual}#{n}", fn))
    return named


def find_conflated_degrades(source: str, path: str = "<src>") -> list:
    """One `Conflation` per function that conflates a failure with an
    absence. Raises NotJudged when the source does not parse: an empty list
    is a clean answer, and an unparsable file has not been given one."""
    tree = _parse(source)
    return [
        Conflation(f"{path}::{qual}", fn.lineno, path, qual)
        for qual, fn in functions_with_qualnames(tree)
        if conflates(fn)
    ]


def compare(found: list, base: set) -> tuple:
    """(new findings not banked, banked keys no longer found).

    The second half is the guard-the-guard: an entry that quietly stopped
    being a finding must leave the baseline, or the floor stops meaning
    anything and a regression re-enters under its cover.
    """
    keys = {f.key for f in found}
    new = sorted((f for f in found if f.key not in base), key=lambda f: f.key)
    fixed = sorted(b for b in base if b not in keys)
    return new, fixed


# ── selfcheck: every case here has failed for real ──────────────────────────

_BAD = '''
def read_state(keys):
    if not keys:
        return {}
    try:
        return fetch(keys)
    except Exception as exc:
        log.warning("read failed: %s", exc)
        return {}
'''

_GOOD = '''
def read_state(keys):
    if not keys:
        return {}, True
    try:
        return fetch(keys), True
    except Exception as exc:
        log.warning("read failed: %s", exc)
        return {}, False
'''

_RERAISES = '''
def read_state(keys):
    if not keys:
        return {}
    try:
        return fetch(keys)
    except Exception:
        raise
'''

_TWO_BAD = _BAD + '''
def other_read(keys):
    if not keys:
        return None
    try:
        return fetch(keys)
    except Exception:
        return None
'''

_SAME_NAMES = '''
class A:
    def read(self):
        if not self.k:
            return {}
        try:
            return fetch(self.k)
        except Exception:
            return {}

class B:
    def read(self):
        if not self.k:
            return {}
        try:
            return fetch(self.k)
        except Exception:
            return {}

def read():
    if not K:
        return {}
    try:
        return fetch(K)
    except Exception:
        return {}

def read():
    if not K:
        return {}
    try:
        return fetch(K)
    except Exception:
        return {}
'''


#: `main` runs the selfcheck before it scans, and the selfcheck drives `main`
#: to prove the CLI refuses an empty scan - two correct decisions that are
#: mutual recursion without this flag (R20-1).
_IN_SELFCHECK = False


def selfcheck() -> bool:
    """A known-good and a known-bad half for every claim this guard makes.

    An exit code is a claim about a process, not about a check (6.7), so
    each case below names what it exercised and the pass line lists them.
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
    import contextlib
    import io
    import tempfile

    problems: list = []

    # Through the CLI, in a pair: named paths holding no Python file are
    # refused with 2 and say so, and one clean file passes - otherwise the
    # refusal could be refusing everything and still look right (R21-2).
    def cli(args: list) -> tuple:
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

    # R24-23, in a pair: a file and a symlink to it are read once, so one
    # conflation is one finding (twice was a duplicate key, exit 2, and a
    # pass under the Action's skip); a link out of the scanned directory is
    # skipped and counted; the target alone is still found.
    with tempfile.TemporaryDirectory() as td:
        inside, elsewhere = Path(td) / "src", Path(td) / "elsewhere"
        inside.mkdir()
        elsewhere.mkdir()
        (inside / "reader.py").write_text(_BAD, encoding="utf-8")
        (elsewhere / "far.py").write_text(_BAD, encoding="utf-8")
        try:
            (inside / "link.py").symlink_to(inside / "reader.py")
            (inside / "out.py").symlink_to(elsewhere / "far.py")
            linked = True
        except OSError:
            linked = False  # no symlinks on this filesystem: nothing to pin
        if linked:
            got, files, _, outside, _, _ = scan([inside])
            if len(files) != 1 or len(got) != 1 or outside != 1:
                problems.append(
                    f"a file and a symlink to it, plus a link out of the "
                    f"scan: read {len(files)} file(s) for {len(got)} "
                    f"finding(s), {outside} skipped - expected 1, 1, 1"
                )
            got, files, _, _, _, _ = scan([inside / "reader.py"])
            if len(got) != 1:
                problems.append("the symlink's target alone lost its finding")

    bad = find_conflated_degrades(_BAD)
    if not bad:
        problems.append("a handler returning the same {} as the empty path "
                        "was not flagged")
    if find_conflated_degrades(_GOOD):
        problems.append("a (value, ok) pair - the fix - was flagged anyway")
    if find_conflated_degrades(_RERAISES):
        problems.append("a handler that re-raises was flagged")

    banked = {f.key for f in bad}

    # Lines inserted ABOVE a banked function must change nothing (R18-1).
    shifted = find_conflated_degrades("# moved\n" * 7 + _BAD)
    new, fixed = compare(shifted, banked)
    if new or fixed:
        problems.append(
            f"lines inserted above a banked function changed the verdict: "
            f"new={[f.key for f in new]} fixed={fixed}"
        )
    if bad and shifted and shifted[0].line == bad[0].line:
        problems.append("the fixture did not move; the line case is vacuous")

    # A genuinely new conflation still fails against the same baseline.
    new, fixed = compare(find_conflated_degrades(_TWO_BAD), banked)
    if [f.key for f in new] != ["<src>::other_read"] or fixed:
        problems.append(f"a new conflation was not reported: "
                        f"new={[f.key for f in new]} fixed={fixed}")

    # A banked entry that becomes distinguishable is reported for banking.
    new, fixed = compare(find_conflated_degrades(_GOOD), banked)
    if new or fixed != ["<src>::read_state"]:
        problems.append(f"a fixed entry was not reported: "
                        f"new={[f.key for f in new]} fixed={fixed}")

    # Same-named functions get distinct, deterministic keys.
    keys = [f.key for f in find_conflated_degrades(_SAME_NAMES)]
    if keys != ["<src>::A.read", "<src>::B.read", "<src>::read",
                "<src>::read#2"]:
        problems.append(f"qualified keys are wrong: {keys}")

    # B-64, in a pair: a key banked beyond the base branch's copy is a
    # finding, and the same baseline against an equal copy passes; an
    # unreadable base copy is could-not-run, never an empty floor. The
    # baseline is written by the scan itself, so the scan agrees with it
    # exactly and growth is the ONLY thing that can turn the first case red.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "bad.py").write_text(_BAD, encoding="utf-8")
        cur, base = root / "cur.json", root / "base.json"
        rc, said = cli([str(root), "--baseline", str(cur), "--update-baseline"])
        banked = cur.read_text(encoding="utf-8") if cur.exists() else ""
        if rc != 0 or "read_state" not in banked:
            problems.append(f"the growth fixture's baseline was not written: "
                            f"exit {rc}, {said!r}")
        args = [str(root), "--baseline", str(cur), "--base-baseline", str(base)]
        for base_text, want in (("[]", 1), (banked, 0), ("{}", 2)):
            base.write_text(base_text, encoding="utf-8")
            rc, said = cli(args)
            grew = "GREW against the base" in said
            if rc != want or grew != (want == 1):
                problems.append(f"the scan's own baseline against base copy "
                                f"{base_text.strip()[:40]!r} exited {rc} "
                                f"(growth named: {grew}), not {want}: {said!r}")

    # R24-27, two pairs: a byte-order mark does not hide a finding (the BOM
    # twin finds what the plain twin finds), and a file that does not parse
    # is NOT (lambda p: find_conflated_degrades(read_source(p)))D - never the empty list a clean file returns.
    with tempfile.TemporaryDirectory() as td:
        plain, bom, broken = (Path(td) / n for n in ("p.py", "b.py", "x.py"))
        plain.write_text(_BAD, encoding="utf-8")
        bom.write_bytes(b"\xef\xbb\xbf" + _BAD.encode("utf-8"))
        broken.write_text("def (:\n", encoding="utf-8")
        want = (lambda p: find_conflated_degrades(read_source(p)))(plain)
        try:
            got = (lambda p: find_conflated_degrades(read_source(p)))(bom)
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
            got = (lambda p: find_conflated_degrades(read_source(p)))(broken)
            problems.append(f"an unparsable file was judged, as {got!r}, "
                            f"instead of named as not judged")
        except NotJudged:
            pass

    for p in problems:
        print(f"[conflated-degrade-lint] SELFCHECK FAILED: {p}")
    if not problems:
        print(
            "[conflated-degrade-lint] selfcheck ok: conflation caught, "
            "(value, ok) passed, re-raise passed, keys unchanged by lines "
            "inserted above them, new conflation reported, separated entry "
            "reported for banking, same-named defs keyed apart, a directory "
            "with no Python file refused with exit 2, one clean file passed, "
            "a key banked beyond the base branch's copy flagged and an equal "
            "copy silent, "
            "a file and its symlink read once and a link out of the scan "
            "skipped, a BOM-prefixed conflation found as the plain one is, "
            "an unparsable file not judged"
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


def _is_vendor(path: Path, root: Path) -> bool:
    """True when ``path`` sits under a vendor directory BELOW ``root``.

    Judged relative to the root the caller named, so pointing the guard at a
    vendor tree on purpose still scans it; only the recursive walk excludes.
    """
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return any(
        part in VENDOR_DIRS or part.endswith(".egg-info")
        for part in rel.parts[:-1]
    )


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


def load_keys(path: Path) -> set:
    """A conflation baseline: a list of keys. Raises ValueError saying why it
    is not one, so a malformed file is "could not run", never an empty
    floor."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(data, list) or not all(isinstance(k, str) for k in data):
        raise ValueError(f"{path}: not a list of keys")
    return set(data)


def baseline_growth(current: set, base: set) -> list:
    """Keys ``current`` banks that ``base``, the base branch's copy, does
    not (B-64). Removed keys are the ratchet working and are not listed."""
    return sorted(current - base)


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


def scan(paths: list, include_vendor: bool = False) -> tuple:
    """(findings, files read, files skipped as vendor, symlinks skipped as
    leaving the scanned paths, [(file, why) not judged], symlinked
    directories not descended)."""
    found: list = []
    named, walked, linked_dirs, unjudged, skipped = _walk(
        paths, None if include_vendor else _is_vendor)
    files, outside = _read_once(named, walked, paths)
    for f in files:
        try:
            found.extend(find_conflated_degrades(read_source(f), _rel(f)))
        except NotJudged as exc:
            unjudged.append((f, str(exc)))
    return found, files, skipped, outside, unjudged, linked_dirs


_KNOWN_FLAGS = {
    "--baseline", "--base-baseline", "--selfcheck", "--update-baseline",
    "--include-vendor", "--help", "-h",
}

_HELP = (
    "usage: conflated_degrade_lint.py [PATH ...] [--baseline FILE]\n"
    "                                 [--base-baseline FILE]\n"
    "                                 [--update-baseline] [--include-vendor]\n"
    "                                 [--selfcheck]\n"
)


def main(argv: "list | None" = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # No arguments is a selfcheck, not a scan of some assumed directory: a
    # default path nobody named would report OK over a tree nothing read.
    if not argv or "--selfcheck" in argv:
        return 0 if selfcheck() else 1
    if "-h" in argv or "--help" in argv:
        print(_HELP)
        print(__doc__)
        return 0

    update = "--update-baseline" in argv
    include_vendor = "--include-vendor" in argv
    baseline_path = Path("conflated_degrade_baseline.json")
    base_path = None
    paths: list = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--baseline", "--base-baseline") and i + 1 >= len(argv):
            print(f"[conflated-degrade-lint] {a} needs a value",
                  file=sys.stderr)
            return 2
        if a == "--baseline":
            baseline_path = Path(argv[i + 1]); i += 2
        elif a == "--base-baseline":
            base_path = Path(argv[i + 1]); i += 2
        elif a.startswith("-"):
            # An unrecognised flag is refused, never ignored: a dropped
            # `--selfchek` would run the default and exit 0, which reads as
            # a pass and proves only that the module imported (R17-2).
            if a not in _KNOWN_FLAGS:
                print(f"[conflated-degrade-lint] unknown flag: {a}",
                      file=sys.stderr)
                return 2
            i += 1
        else:
            paths.append(Path(a)); i += 1

    if not paths:
        print("[conflated-degrade-lint] no path given and nothing was "
              "scanned; name a directory or run --selfcheck", file=sys.stderr)
        return 2

    if update and base_path is not None:
        print("[conflated-degrade-lint] --base-baseline checks a baseline and "
              "--update-baseline writes one; they are not combined.",
              file=sys.stderr)
        return 2

    if not selfcheck():
        return 1

    # B-64: both baselines are read before the scan, so a base copy that
    # cannot be read is could-not-run, not growth judged against nothing.
    grown: list = []
    if base_path is not None:
        try:
            base_keys = load_keys(base_path)
            current = load_keys(baseline_path) if baseline_path.exists() else set()
        except ValueError as exc:
            print(f"[conflated-degrade-lint] cannot compare the baseline with "
                  f"the base branch's copy: {exc}. Nothing was judged (2.9).",
                  file=sys.stderr)
            return 2
        grown = baseline_growth(current, base_keys)

    found, files, skipped, outside, unjudged, linked_dirs = scan(
        paths, include_vendor)
    _say_walk("conflated-degrade-lint", linked_dirs)
    if outside:
        print(
            f"[conflated-degrade-lint] skipped {outside} symlinked file(s) "
            f"whose target is outside the scanned path(s); name the target's "
            f"directory to scan it"
        )

    # Say what was NOT read. An exclusion the operator cannot see is the same
    # class of lie this guard exists to catch.
    if skipped:
        print(
            f"[conflated-degrade-lint] skipped {skipped} file(s) under vendor "
            f"directories ({', '.join(sorted(VENDOR_DIRS)[:4])}, ...); pass "
            f"--include-vendor to scan them"
        )

    # Zero files read is "could not measure", never "at the floor" (2.9),
    # and that holds for --update-baseline too: a floor recorded over
    # nothing is a floor of nothing (R21-2).
    if not files and not unjudged:
        states = ", ".join(
            f"{p} ({'does not exist' if not p.exists() else 'is not a .py file' if p.is_file() else 'holds no .py file'})"
            for p in paths
        )
        print(
            f"[conflated-degrade-lint] nothing was scanned: {states}"
            + (f"; the {skipped} .py file(s) found are all under vendor "
               f"directories, and --include-vendor scans them"
               if skipped else "")
            + ". This is not a pass (2.9). Name the directory that holds your "
            "Python source; a repository with no Python has nothing for this "
            "guard to read, so remove its CI step rather than keep a check "
            "that cannot run.",
            file=sys.stderr,
        )
        return 2

    keys = [f.key for f in found]
    if len(set(keys)) != len(keys):
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        print(
            f"[conflated-degrade-lint] INSTRUMENT ERROR: duplicate key(s) in "
            f"one scan, so a baseline cannot mean anything: {dupes}. Refusing "
            f"to judge (2.9 - could not measure is not did not fail).",
            file=sys.stderr,
        )
        return 2

    if update and unjudged:
        _say_unjudged("conflated-degrade-lint", unjudged, _rel, True)
        print("[conflated-degrade-lint] baseline NOT written: it would be a "
              "floor that silently leaves these files out.", file=sys.stderr)
        return 2
    if update:
        baseline_path.write_text(json.dumps(sorted(keys), indent=2) + "\n")
        print(
            f"[conflated-degrade-lint] baseline written: {baseline_path} "
            f"({len(keys)} conflation(s) across {len(files)} file(s))"
        )
        return 0

    base = set(json.loads(baseline_path.read_text())) if baseline_path.exists() else set()
    new, fixed = compare(found, base)
    # A banked entry in a file that was not judged is not "now
    # distinguishable": nobody looked. It stays banked, and the file is named.
    not_judged = {_rel(f) for f, _ in unjudged}
    fixed = [k for k in fixed if k.split("::", 1)[0] not in not_judged]

    code = _verdict(bool(new or fixed or grown), bool(unjudged))
    if grown:
        print(f"\n[conflated-degrade-lint] the baseline GREW against the base "
              f"branch's copy ({base_path}); a change cannot bank the "
              f"conflation it adds (2.1, B-64):\n")
        for k in grown:
            print(f"  {k}: added")
        print()
    if new:
        print(
            f"\n[conflated-degrade-lint] {len(new)} function(s) return the "
            f"SAME value on failure as on a legitimate empty result; the "
            f"caller cannot tell 'nothing there' from 'the read failed':\n"
        )
        for f in new:
            print(f"  {f.message}")
        print(
            "\nThe fail-safe VALUE is usually right; the silence is the "
            "defect. Return (value, ok), set a counter the caller reads, or "
            "carry a reason - do not simply raise.\n"
        )
    elif fixed:
        print(
            f"\n[conflated-degrade-lint] {len(fixed)} baselined conflation(s) "
            f"are now distinguishable; bank the lower floor with "
            f"--update-baseline:\n"
        )
        for k in fixed:
            print(f"  {k}")
    _say_unjudged("conflated-degrade-lint", unjudged, _rel, code == 2)
    if code:
        return code
    print(
        f"[conflated-degrade-lint] OK ({len(files)} file(s), {len(base)} "
        f"baselined conflation(s) - the ratchet only shrinks)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
