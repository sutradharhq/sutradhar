# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
#!/usr/bin/env python3
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
    python conflated_degrade_lint.py --selfcheck             # prove it works

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
    """One `Conflation` per function that conflates a failure with an absence."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
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


def selfcheck() -> bool:
    """A known-good and a known-bad half for every claim this guard makes.

    An exit code is a claim about a process, not about a check (6.7), so
    each case below names what it exercised and the pass line lists them.
    """
    problems: list = []

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

    for p in problems:
        print(f"[conflated-degrade-lint] SELFCHECK FAILED: {p}")
    if not problems:
        print(
            "[conflated-degrade-lint] selfcheck ok: conflation caught, "
            "(value, ok) passed, re-raise passed, keys unchanged by lines "
            "inserted above them, new conflation reported, separated entry "
            "reported for banking, same-named defs keyed apart"
        )
    return not problems


# ── CLI ─────────────────────────────────────────────────────────────────────

def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(Path.cwd()))
    except ValueError:
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


def scan(paths: list, include_vendor: bool = False) -> tuple:
    """(findings, files read, files skipped as vendor)."""
    found: list = []
    files: list = []
    skipped = 0
    for root in paths:
        if root.is_file() and root.suffix == ".py":
            files.append(root)
            continue
        for f in sorted(root.rglob("*.py")):
            if not include_vendor and _is_vendor(f, root):
                skipped += 1
                continue
            files.append(f)
    for f in files:
        found.extend(find_conflated_degrades(
            f.read_text(encoding="utf-8", errors="replace"), _rel(f)
        ))
    return found, files, skipped


_KNOWN_FLAGS = {
    "--baseline", "--selfcheck", "--update-baseline", "--include-vendor",
    "--help", "-h",
}

_HELP = (
    "usage: conflated_degrade_lint.py [PATH ...] [--baseline FILE]\n"
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
    paths: list = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--baseline":
            baseline_path = Path(argv[i + 1]); i += 2
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

    if not selfcheck():
        return 1

    found, files, skipped = scan(paths, include_vendor)

    # Say what was NOT read. An exclusion the operator cannot see is the same
    # class of lie this guard exists to catch.
    if skipped:
        print(
            f"[conflated-degrade-lint] skipped {skipped} file(s) under vendor "
            f"directories ({', '.join(sorted(VENDOR_DIRS)[:4])}, ...); pass "
            f"--include-vendor to scan them"
        )

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

    if update:
        baseline_path.write_text(json.dumps(sorted(keys), indent=2) + "\n")
        print(
            f"[conflated-degrade-lint] baseline written: {baseline_path} "
            f"({len(keys)} conflation(s) across {len(files)} file(s))"
        )
        return 0

    base = set(json.loads(baseline_path.read_text())) if baseline_path.exists() else set()
    new, fixed = compare(found, base)

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
        return 1
    if fixed:
        print(
            f"\n[conflated-degrade-lint] {len(fixed)} baselined conflation(s) "
            f"are now distinguishable; bank the lower floor with "
            f"--update-baseline:\n"
        )
        for k in fixed:
            print(f"  {k}")
        return 1
    print(
        f"[conflated-degrade-lint] OK ({len(files)} file(s), {len(base)} "
        f"baselined conflation(s) - the ratchet only shrinks)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
