# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
#!/usr/bin/env python3
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

Usage:
    python swallow_lint.py src/                     # gate against baseline
    python swallow_lint.py src/ --update-baseline   # record today's floor
    python swallow_lint.py --selfcheck              # prove the detector works

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
    """Return line numbers of silent swallows in ``source``."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _is_broad_handler(node):
            if _handler_swallows(node, extra_calls or set()):
                hits.append(node.lineno)
    return hits


def check_file(path: Path, extra_calls: set[str] | None = None) -> list[int]:
    return check_source(
        path.read_text(encoding="utf-8", errors="replace"), extra_calls
    )


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


def selfcheck() -> bool:
    bad = check_source(_KNOWN_BAD)
    good = check_source(_KNOWN_GOOD)
    ok = len(bad) == 2 and len(good) == 0
    if not ok:
        print(f"[swallow-lint] SELFCHECK FAILED: bad={bad} good={good}")
    else:
        print(
            "[swallow-lint] selfcheck ok: silent swallow caught, handled "
            "exception passed"
        )
    return ok


# ── CLI ─────────────────────────────────────────────────────────────────────

def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(p)


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
    "--allow-call", "--baseline", "--selfcheck", "--update-baseline",
    "--include-vendor", "--help", "-h",
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--selfcheck" in argv:
        return 0 if selfcheck() else 1

    update = "--update-baseline" in argv
    include_vendor = "--include-vendor" in argv
    baseline_path = Path("swallow_baseline.json")
    extra_calls: set[str] = set()
    paths: list[Path] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--baseline":
            baseline_path = Path(argv[i + 1]); i += 2
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
    if not paths:
        paths = [Path("src")]

    if not selfcheck():
        return 1

    py_files: list[Path] = []
    skipped_vendor = 0
    for root in paths:
        if root.is_file() and root.suffix == ".py":
            py_files.append(root)
            continue
        for f in root.rglob("*.py"):
            if not include_vendor and _is_vendor(f, root):
                skipped_vendor += 1
                continue
            py_files.append(f)

    # Say what was NOT read. An exclusion the operator cannot see is the same
    # class of lie the guard exists to catch: "OK" over an unscanned tree.
    if skipped_vendor:
        print(
            f"[swallow-lint] skipped {skipped_vendor} file(s) under vendor "
            f"directories ({', '.join(sorted(VENDOR_DIRS)[:4])}, ...); "
            f"pass --include-vendor to scan them"
        )

    counts: dict[str, int] = {}
    lines_by_file: dict[str, list[int]] = {}
    for f in py_files:
        found = check_file(f, extra_calls)
        if found:
            counts[_rel(f)] = len(found)
            lines_by_file[_rel(f)] = found

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
        if counts.get(rel, 0) < allowed
    ]

    if regressions:
        print("\n[swallow-lint] NEW silent swallow(s) beyond baseline:\n")
        print("\n".join(regressions))
        print()
        return 1

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
