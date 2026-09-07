# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
#!/usr/bin/env python3
"""Guard: flag values interpolated into a query language.

The three spellings this catches:

    f'SELECT * FROM t WHERE name = "{user_input}"'
    "SELECT * FROM t WHERE name = '%s'" % user_input
    "SELECT * FROM t WHERE name = '{}'".format(user_input)

String interpolation into SQL, SPARQL, Cypher, or any query DSL is a hole
even when the current value is a module constant: the PATTERN becomes the
vulnerability the moment someone parameterises it. This guard flags the
shape, so the fix is applied while the value is still safe.

The `%` and `.format()` halves are the same hole in an older spelling, and
they went unread here until round 16 found them by review (register item
B-20, `practice`: a detector gap nobody has yet paid for, so it strengthens
2.8's mechanism and founds nothing). The f-string beside them was caught
from the first day, which is the worst shape a lint can have - it looks
like coverage of the class and covers one dialect of it.

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
such as ``LIMIT {n}`` or URI positions. The same quoting and same-site
safety rules apply to all three spellings: ``'%s'`` and ``'{}'`` in a quoted
position are flagged, ``LIMIT %d`` and ``LIMIT {n}`` are not, and
``'{escape_literal(name)}'`` is clean whichever way it is written.

Known limitations, stated honestly, because a lint that looks total and is
not is worse than one whose edges are written down:

  - the format string has to be a LITERAL at the call site. ``QUERY %
    name``, where ``QUERY`` is a module constant, is not seen - there is no
    string here to read the query keywords out of.
  - a ``%`` or ``.format()`` whose arguments cannot be matched to their
    placeholders one for one (``"..." % params``, ``"...".format(**kw)``)
    is judged on ALL its arguments: safe only when every one of them is
    safe. That errs towards flagging, which is the direction a hole should
    be judged in.
  - no string with none of the configured query keywords in it is looked at
    at all, whatever operator is applied to it. That is what keeps ``"%d%%
    done" % pct`` and every other formatted message out of the report.

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
    r"_(?:seconds|count|bytes|percent|pct|ms|int|integer|float|num|id_int|days|hours|limit)$",
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


# ── the two older spellings (B-20) ──────────────────────────────────────────
#
# `"... = '%s'" % name` and `"... = '{}'".format(name)` are the same hole as
# the f-string beside them, and read exactly as safe to a guard that only
# knows `ast.JoinedStr`. Both are matched on the LITERAL at the call site: a
# format string held in a module constant is invisible here and is named as a
# limitation in the docstring rather than half-handled.

#: One `%`-conversion. `%%` is matched too and skipped by the caller - it is
#: a literal percent sign and consumes no argument, so counting it would
#: shift every positional index after it by one.
_PERCENT_SPEC = re.compile(
    r"%(?:\((?P<key>[^)]*)\))?[-#0 +]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlL]?"
    r"(?P<conv>[diouxXeEfFgGcrsa%])"
)

#: One `str.format` replacement field. `{{` and `}}` are matched so they are
#: skipped rather than read as an empty field.
_FORMAT_FIELD = re.compile(r"\{\{|\}\}|\{([^{}]*)\}")


def _string_literal(node: ast.expr) -> "str | None":
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _quoted_at(text: str, start: int, end: int) -> bool:
    return _quoted_position(text[:start], text[end:])


def _describe(expr: "ast.expr | None", fallback: ast.expr) -> tuple:
    """``(lineno, source)`` for the report, preferring the resolved arg."""
    node = expr if expr is not None else fallback
    try:
        src = ast.unparse(node)
    except Exception:  # pragma: no cover - unparse is total on 3.9+
        src = "<expr>"
    return node.lineno, src


def _judge(expr, everything, safe, allow):
    """True when this placeholder is SAFE and may be skipped.

    An argument that could not be matched to its placeholder is judged
    against every argument the call has: safe only if all of them are. A
    guard that resolved "cannot tell" to "clean" would report green on
    exactly the calls whose shape it could not read (2.9).
    """
    candidates = [expr] if expr is not None else list(everything)
    if not candidates:
        return True          # nothing is interpolated here at all
    return all(_expr_is_safe(c, safe, allow) for c in candidates)


def _percent_hits(node: ast.BinOp, kw_re, safe, allow, strict) -> list:
    text = _string_literal(node.left)
    if text is None or not kw_re.search(text):
        return []
    right = node.right
    if isinstance(right, ast.Tuple):
        positional, keyed = list(right.elts), {}
    elif isinstance(right, ast.Dict):
        positional = []
        keyed = {k.value: v for k, v in zip(right.keys, right.values)
                 if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    else:
        positional, keyed = [right], {}
    everything = positional + list(keyed.values())

    hits: list = []
    index = 0
    for m in _PERCENT_SPEC.finditer(text):
        if m.group("conv") == "%":
            continue
        key = m.group("key")
        if key is None:
            expr = positional[index] if index < len(positional) else None
            index += 1
        else:
            expr = keyed.get(key)
        if not _quoted_at(text, m.start(), m.end()) and not strict:
            continue
        if _judge(expr, everything, safe, allow):
            continue
        hits.append(_describe(expr, right))
    return hits


def _format_hits(node: ast.Call, kw_re, safe, allow, strict) -> list:
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "format"):
        return []
    text = _string_literal(func.value)
    if text is None or not kw_re.search(text):
        return []
    args = list(node.args)
    named = {kw.arg: kw.value for kw in node.keywords if kw.arg}
    everything = args + [kw.value for kw in node.keywords]

    hits: list = []
    auto = 0
    for m in _FORMAT_FIELD.finditer(text):
        field = m.group(1)
        if field is None:
            continue                                    # `{{` or `}}`
        name = re.split(r"[!:]", field, maxsplit=1)[0]
        root = re.split(r"[.\[]", name, maxsplit=1)[0]
        if root == "":
            expr = args[auto] if auto < len(args) else None
            auto += 1
        elif root.isdigit():
            i = int(root)
            expr = args[i] if i < len(args) else None
        else:
            expr = named.get(root)
        if not _quoted_at(text, m.start(), m.end()) and not strict:
            continue
        if _judge(expr, everything, safe, allow):
            continue
        hits.append(_describe(expr, func.value))
    return hits


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
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            hits.extend(_percent_hits(node, kw_re, safe, allow, strict))
            continue
        if isinstance(node, ast.Call):
            hits.extend(_format_hits(node, kw_re, safe, allow, strict))
            continue
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

_KNOWN_BAD_PERCENT = '''
def q(name):
    return "SELECT * FROM t WHERE name = '%s'" % name
'''

_KNOWN_BAD_FORMAT = '''
def q(name):
    return "SELECT * FROM t WHERE name = '{}'".format(name)
'''

_KNOWN_GOOD = '''
def q(name, n_limit):
    a = f'SELECT * FROM t WHERE name = "{escape_literal(name)}"'
    b = f'SELECT * FROM t LIMIT {n_limit}'
    return a, b
'''

#: The false-positive surface, which is the half that decides whether a lint
#: survives its first week. Every one of these applies `%` or `.format()` to
#: a string that is not a query, or to a query in a position that is not
#: injectable, or with the escaping call already at the site.
_KNOWN_GOOD_OTHER_SPELLINGS = '''
def messages(pct, name, page, table):
    a = "%d%% done" % pct
    b = "hello, '{}'".format(name)
    c = "SELECT * FROM t LIMIT %d" % page
    g = "SELECT * FROM t LIMIT {}".format(page)
    d = "SELECT * FROM t WHERE n = '%s'" % escape_literal(name)
    e = "SELECT * FROM t WHERE n = '{}'".format(sql_quote(name))
    f = "SELECT * FROM t WHERE n = '%(k)s'" % {"k": int(name)}
    return a, b, c, d, e, f, g
'''


def selfcheck() -> bool:
    """Known-bad and known-good for each of the three spellings (6.7).

    The negative half carries as much weight as the positive one here: a
    detector that flagged every `%` would be deleted from CI inside a week,
    and every hole it could have caught leaves with it.
    """
    kws = KEYWORD_PRESETS["sql"]
    problems: list = []

    for label, source, want in (
        ("f-string into a quoted query position", _KNOWN_BAD, 1),
        ("`%`-format into a quoted query position", _KNOWN_BAD_PERCENT, 1),
        ("`.format()` into a quoted query position", _KNOWN_BAD_FORMAT, 1),
        ("escaped and unquoted f-string positions", _KNOWN_GOOD, 0),
        ("`%` and `.format()` on strings that are not injectable queries",
         _KNOWN_GOOD_OTHER_SPELLINGS, 0),
    ):
        got = check_source(source, kws)
        if len(got) != want:
            problems.append(
                f"{label}: {len(got)} finding(s), expected {want}: {got}"
            )

    # The report has to name the expression, or the reader cannot act on it.
    # Checked after the count above, so a detector returning nothing produces
    # a verdict rather than an IndexError (6.11).
    for label, source in (("%", _KNOWN_BAD_PERCENT),
                          (".format", _KNOWN_BAD_FORMAT)):
        got = check_source(source, kws)
        if len(got) == 1 and got[0][1] != "name":
            problems.append(
                f"the {label} finding named {got[0][1]!r} and not the "
                f"argument being interpolated"
            )

    for p in problems:
        print(f"[interpolation-lint] SELFCHECK FAILED: {p}")
    if not problems:
        print(
            "[interpolation-lint] selfcheck ok: interpolated query caught in "
            "all three spellings (f-string, `%`, `.format()`) with the "
            "argument named, and left alone when escaped at the site, in an "
            "unquoted position, or in a string carrying no query keyword"
        )
    return not problems


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
