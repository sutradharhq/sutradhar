# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
#!/usr/bin/env python3
"""Guard: flag f-strings that interpolate values into a query language.

The pattern this catches:

    f'SELECT * FROM t WHERE name = "{user_input}"'

String interpolation into SQL, SPARQL, Cypher, or any query DSL is a hole
even when the current value is a module constant: the PATTERN becomes the
vulnerability the moment someone parameterises it. This guard flags the
shape, so the fix is applied while the value is still safe.

An interpolation is considered SAFE when any of these hold:

  - it is wrapped in an escaping call at the site, for example
    ``f'... "{escape_literal(name)}" ...'`` (configurable with --safe-call)
  - it is a call to ``int()`` / ``float()`` / ``len()`` (cannot carry quotes)
  - its name ends in a numeric-typed suffix (``_count``, ``_id_int``, ...)
  - it appears in the allowlist file (names reviewed and vouched for)

Detection is AST-based: triple-quoted and single-line f-strings, implicit
concatenation, and multi-line expressions are all seen. By default only
interpolations inside a QUOTED literal position ``"{x}"`` are flagged (the
directly injectable position); ``--strict`` also flags bare interpolations
such as ``LIMIT {n}`` or URI positions.

Known limitation, stated honestly: ``str.format`` and ``%`` formatting are
not analyzed. If your codebase builds queries that way, migrate to f-strings
or extend the guard first.

Usage:
    python interpolation_lint.py src/ --keywords sql
    python interpolation_lint.py src/ --keywords sparql --safe-call my_escape
    python interpolation_lint.py --selfcheck
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

KEYWORD_PRESETS: dict[str, set[str]] = {
    "sql": {
        "SELECT", "INSERT", "UPDATE", "DELETE", "WHERE", "FROM",
        "JOIN", "GROUP BY", "ORDER BY", "HAVING",
    },
    "sparql": {
        "SELECT", "INSERT", "DELETE", "CONSTRUCT", "ASK", "DESCRIBE",
        "WHERE", "FILTER", "OPTIONAL", "GRAPH", "UNION",
    },
    "cypher": {"MATCH", "MERGE", "CREATE", "WHERE", "RETURN", "DETACH"},
}

DEFAULT_SAFE_CALLS = {
    "escape_literal", "sparql_literal", "sql_quote", "quote_literal",
    "int", "float", "len",
}

_NUMERIC_SUFFIX_RE = re.compile(
    r"_(?:seconds|count|kwh|percent|pct|ms|int|integer|float|num|id_int|days|hours|limit)$",
    re.I,
)


def _kw_regex(keywords: set[str]) -> re.Pattern[str]:
    alts = sorted((re.escape(k) for k in keywords), key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(alts) + r")\b")


def _expr_is_safe(node: ast.expr, safe_calls: set[str], allowlist: set[str]) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Call):
        f = node.func
        leaf = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        return leaf in safe_calls
    leaf_name = ""
    if isinstance(node, ast.Name):
        leaf_name = node.id
    elif isinstance(node, ast.Attribute):
        leaf_name = node.attr
    if leaf_name:
        if leaf_name in allowlist:
            return True
        if _NUMERIC_SUFFIX_RE.search(leaf_name):
            return True
    return False


def _quoted_position(before: str, after: str) -> bool:
    """True when the interpolation sits inside a quoted literal: ``"{x}"``."""
    b = before.rstrip()
    a = after.lstrip()
    return (b.endswith('"') and a.startswith('"')) or (
        b.endswith("'") and a.startswith("'")
    )


def check_source(
    source: str,
    keywords: set[str],
    safe_calls: set[str] | None = None,
    allowlist: set[str] | None = None,
    strict: bool = False,
) -> list[tuple[int, str]]:
    """Return (lineno, expr_source) for each risky interpolation."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    kw_re = _kw_regex(keywords)
    safe = DEFAULT_SAFE_CALLS | (safe_calls or set())
    allow = allowlist or set()
    hits: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        literal_text = "".join(
            v.value
            for v in node.values
            if isinstance(v, ast.Constant) and isinstance(v.value, str)
        )
        if not kw_re.search(literal_text):
            continue
        parts = node.values
        for idx, part in enumerate(parts):
            if not isinstance(part, ast.FormattedValue):
                continue
            before = (
                parts[idx - 1].value
                if idx > 0
                and isinstance(parts[idx - 1], ast.Constant)
                and isinstance(parts[idx - 1].value, str)
                else ""
            )
            after = (
                parts[idx + 1].value
                if idx + 1 < len(parts)
                and isinstance(parts[idx + 1], ast.Constant)
                and isinstance(parts[idx + 1].value, str)
                else ""
            )
            quoted = _quoted_position(before, after)
            if not quoted and not strict:
                continue
            if _expr_is_safe(part.value, safe, allow):
                continue
            try:
                expr_src = ast.unparse(part.value)
            except Exception:  # pragma: no cover - unparse is total on 3.9+
                expr_src = "<expr>"
            hits.append((part.value.lineno, expr_src))
    return hits


def check_file(path: Path, **kw) -> list[tuple[int, str]]:
    return check_source(path.read_text(encoding="utf-8", errors="replace"), **kw)


# ── selfcheck: the guard must be shown to fail ──────────────────────────────

_KNOWN_BAD = '''
def q(name):
    return f'SELECT * FROM t WHERE name = "{name}"'
'''

_KNOWN_GOOD = '''
def q(name, n_limit):
    a = f'SELECT * FROM t WHERE name = "{escape_literal(name)}"'
    b = f'SELECT * FROM t LIMIT {n_limit}'
    return a, b
'''


def selfcheck() -> bool:
    kws = KEYWORD_PRESETS["sql"]
    bad = check_source(_KNOWN_BAD, kws)
    good = check_source(_KNOWN_GOOD, kws)
    ok = len(bad) == 1 and len(good) == 0
    if not ok:
        print(f"[interpolation-lint] SELFCHECK FAILED: bad={bad} good={good}")
    else:
        print(
            "[interpolation-lint] selfcheck ok: interpolated query caught, "
            "parameterised query passed"
        )
    return ok


# ── CLI ─────────────────────────────────────────────────────────────────────

_KNOWN_FLAGS = {"--allowlist", "--keywords", "--safe-call", "--selfcheck", "--strict", "--help", "-h"}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--selfcheck" in argv:
        return 0 if selfcheck() else 1

    keywords: set[str] = set()
    safe_calls: set[str] = set()
    allowlist: set[str] = set()
    strict = "--strict" in argv
    paths: list[Path] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--keywords":
            for k in argv[i + 1].split(","):
                keywords |= KEYWORD_PRESETS.get(k.strip(), {k.strip().upper()})
            i += 2
        elif a == "--safe-call":
            safe_calls.add(argv[i + 1]); i += 2
        elif a == "--allowlist":
            allowlist |= set(json.loads(Path(argv[i + 1]).read_text())); i += 2
        elif a.startswith("--"):
            # An unrecognised flag must NOT be ignored. Silently
            # skipping it means a typo like `--selfchek` runs the
            # default scan and exits 0, which reads as a pass.
            if a not in _KNOWN_FLAGS:
                print(
                    f"[interpolation-lint] unknown flag: {a}", file=sys.stderr
                )
                return 2
            i += 1
        else:
            paths.append(Path(a)); i += 1
    if not keywords:
        keywords = KEYWORD_PRESETS["sql"] | KEYWORD_PRESETS["sparql"]
    if not paths:
        paths = [Path("src")]

    if not selfcheck():
        return 1

    py_files: list[Path] = []
    for root in paths:
        if root.is_file() and root.suffix == ".py":
            py_files.append(root)
        else:
            py_files.extend(
                f for f in root.rglob("*.py") if "__pycache__" not in str(f)
            )

    issues: list[tuple[Path, int, str]] = []
    for f in py_files:
        for lineno, expr in check_file(
            f, keywords=keywords, safe_calls=safe_calls,
            allowlist=allowlist, strict=strict,
        ):
            issues.append((f, lineno, expr))

    if issues:
        print(
            f"\n[interpolation-lint] {len(issues)} query interpolation risk(s) - "
            f"wrap with an escaping call at the site:\n"
        )
        for path, lineno, expr in issues:
            print(f"  {path}:{lineno}  {{{expr}}}")
        print()
        return 1

    print(f"[interpolation-lint] OK ({len(py_files)} files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
