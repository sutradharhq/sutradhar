"""Ready-made detectors for the Ratchet library.

Class detectors with proven records, shipped so a new project's first
ratchet costs five minutes instead of an afternoon. Wire them per
docs/backend.md:

    def test_relative_imports_resolve():
        Ratchet("tests/baselines/imports.json").assert_only_shrinks(
            find_unresolved_relative_imports("src/app")
        )

The import-integrity detector is the single highest-yield ratchet from our
build record: written after a manual sweep, it immediately found three
defects the sweep had missed, and kept finding new ones as the codebase
grew (a helper-level unit test structurally cannot see a handler's broken
import - this walks every module without executing any).

Every detector returns `Violation(key, message)`. The KEY is the file plus
the normalised matched text (`src/a.py::from .util import helper`), with
`#2`, `#3` in source order for a repeat of the same text in one file; the
LINE NUMBER lives in the message and never in the key. A key that moved
with the code re-flagged banked findings on every unrelated edit above them,
and the only quick way out was `--update-baseline` - which banks the real
new findings too. See `ratchet.py` for the contract and its scar.
"""
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import NamedTuple


class Violation(NamedTuple):
    """(stable key, human-readable message).

    Defined here rather than imported from `ratchet.py` on purpose: these
    files are copy-in and land in different directories in an adopter's
    tree, so a cross-module import would break for them and not for us -
    the same reasoning that keeps `rounds.py` and `budget.py` carrying one
    frontmatter parser each. A ratchet banks `.key` and prints `.message`;
    `str()` gives the key, so a plain-string caller still works.
    """

    key: str
    message: str = ""

    def __str__(self) -> str:
        return self.key


def _numbered(key: str, seen: dict) -> str:
    """`key`, then `key#2`, `key#3` for later repeats in source order.

    So a second identical match never renames the first one's entry: the
    one that was there keeps its key, and only the new one is new.
    """
    n = seen.get(key, 0) + 1
    seen[key] = n
    return key if n == 1 else f"{key}#{n}"


def _parse_source(source: str) -> tuple:
    """(tree, None), or (None, why) when there is no tree.

    One leading U+FEFF is dropped first: it is what a byte-order mark
    becomes when a caller decodes the file as `utf-8`, the interpreter
    drops it before it runs the file, and the parser refuses it as a
    character (R25-2, the R24-27 class). Every parse failure the lints
    name as not judged is caught here - a NUL byte is a ValueError on
    3.9 and a SyntaxError later - so the instrument reports instead of
    crashing (6.11), and the caller turns `why` into a violation, never
    into the empty list a clean file returns (2.9).
    """
    if source.startswith("\ufeff"):
        source = source[1:]
    try:
        return ast.parse(source), None
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        if isinstance(exc, SyntaxError):
            at = f" at line {exc.lineno}" if exc.lineno else ""
            return None, f"SyntaxError{at}: {exc.msg}"
        return None, f"{type(exc).__name__}: {exc}"


def _parse_file(py: Path) -> tuple:
    """`_parse_source` over a file read as the interpreter reads it.

    `utf-8-sig`, the encoding swallow, interpolation and conflated-degrade
    moved to in R24-27: a BOM-prefixed file is one Python imports and runs,
    so it is judged, not reported as unparsable. A file that cannot be read
    at all comes back as (None, why) like one that cannot be parsed.
    """
    try:
        source = py.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return None, f"could not be read ({type(exc).__name__}: {exc.strerror or exc})"
    return _parse_source(source)


def _import_text(node: ast.ImportFrom, only: str | None = None) -> str:
    """`from ..pkg.mod import a, b` - the matched text, normalised.

    Position-free by construction, which is the whole point: this is what
    the baseline stores.
    """
    names = [only] if only else [a.name for a in node.names]
    return (
        f"from {'.' * node.level}{node.module or ''} import {', '.join(names)}"
    )


def find_unresolved_relative_imports(package_root: str | Path) -> list[Violation]:
    """Every ``from .x import y`` in the package must resolve.

    Checks that the target MODULE exists on disk, and - when the target
    module parses - that each imported NAME is actually defined in it
    (top-level def/class/assignment/import/star-export). Returns
    ``Violation(key, message)``: the key is ``path::from .x import y`` and
    carries no line number, the message carries the line.
    """
    root = Path(package_root).resolve()
    violations: list[Violation] = []

    for py in sorted(root.rglob("*.py")):
        if "__pycache__" in str(py):
            continue
        seen: dict = {}
        tree, why = _parse_file(py)
        if tree is None:
            violations.append(Violation(
                f"{py}::does not parse",
                f"{py}: does not parse, so its imports were not judged: {why}",
            ))
            continue
        imports = sorted(
            (n for n in ast.walk(tree)
             if isinstance(n, ast.ImportFrom) and n.level != 0),
            key=lambda n: (n.lineno, n.col_offset),
        )
        for node in imports:
            # Resolve the base directory for `from ..mod import name`.
            base = py.parent
            for _ in range(node.level - 1):
                base = base.parent
            target = base / node.module.replace(".", "/") if node.module else base
            mod_file = target.with_suffix(".py")
            pkg_init = target / "__init__.py"
            if mod_file.exists():
                _check_names(py, node, mod_file, violations, seen,
                             is_package_dir=None)
            elif pkg_init.exists():
                _check_names(py, node, pkg_init, violations, seen,
                             is_package_dir=target)
            else:
                violations.append(Violation(
                    _numbered(f"{py}::{_import_text(node)}", seen),
                    f"{py}:{node.lineno}: unresolved relative import "
                    f"'{'.' * node.level}{node.module or ''}'",
                ))
    return violations


def _module_exports(mod_file: Path) -> set[str] | None:
    """Top-level names a module defines. None = names unknowable (skip).

    Two causes share the None on purpose - the module does not parse, or it
    star-re-exports - and that conflation is banked, not fixed (R24-6): to
    the one caller both mean "the names cannot be checked", and the parse
    failure is not silent, because the walk in
    find_unresolved_relative_imports reports every file under the root that
    does not parse as its own `::does not parse` violation in the same list.
    The residual - a relative import climbing above the scanned root to a
    module that does not parse - is recorded as deferred in round 24.
    """
    tree, _why = _parse_file(mod_file)
    if tree is None:
        return None
    names: set[str] = set()
    star = False
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            names.add(n.target.id)
        elif isinstance(n, ast.ImportFrom):
            if any(a.name == "*" for a in n.names):
                star = True
            names.update(a.asname or a.name for a in n.names if a.name != "*")
        elif isinstance(n, ast.Import):
            names.update((a.asname or a.name).split(".")[0] for a in n.names)
    if star:
        return None  # re-export surface unknowable without following the star
    return names


def _check_names(src: Path, node: ast.ImportFrom, mod_file: Path,
                 violations: list, seen: dict,
                 is_package_dir: Path | None) -> None:
    exports = _module_exports(mod_file)
    if exports is None:
        return
    for alias in node.names:
        if alias.name == "*":
            continue
        if alias.name in exports:
            continue
        # From a package, `from .pkg import submodule` is also valid.
        if is_package_dir is not None:
            sub = is_package_dir / alias.name
            if sub.with_suffix(".py").exists() or (sub / "__init__.py").exists():
                continue
        violations.append(Violation(
            _numbered(f"{src}::{_import_text(node, alias.name)}", seen),
            f"{src}:{node.lineno}: '{alias.name}' is not defined in "
            f"{mod_file.name}",
        ))


# ── unbounded ORDER BY ──────────────────────────────────────────────────────

_ORDER_RE = re.compile(r"\bORDER\s+BY\b", re.I)
_BOUND_RE = re.compile(r"\bLIMIT\b|\bFETCH\s+FIRST\b|\bTOP\s+\d", re.I)


def find_order_by_without_limit(
    source: str, path: str = "<src>"
) -> list[Violation]:
    """String literals containing ORDER BY with no LIMIT.

    Doctrine 2.6: ORDER BY on an unbounded result set is a memory bomb -
    the store materializes and sorts the whole set. This walks every string
    constant AND every f-string's literal parts, so query fragments built
    either way are seen. Queries that carry their bound in a separate
    fragment belong in the ratchet baseline with a comment.

    Returns ``Violation(key, message)``. The key is ``path::<normalised
    query text>`` - the query is what the baseline is about, and unlike its
    line it does not move when somebody edits the imports above it. Pass
    ``path`` so the key names the file; the line stays in the message.

    Source that does not parse returns one ``path::does not parse``
    violation, never the empty list a clean source returns (R25-2): the
    queries in it were not judged, and a ratchet must not read that as
    none. A leading U+FEFF - a byte-order mark decoded as `utf-8` - is
    dropped, as the interpreter drops it.
    """
    tree, why = _parse_source(source)
    if tree is None:
        return [Violation(
            f"{path}::does not parse",
            f"{path}: does not parse, so its queries were not judged: {why}",
        )]
    found: list = []
    # Constants INSIDE an f-string are also visited by ast.walk; skip them
    # so a hit is counted once, on the JoinedStr.
    in_fstring: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for v in node.values:
                in_fstring.add(id(v))
    for node in ast.walk(tree):
        if id(node) in in_fstring:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
        elif isinstance(node, ast.JoinedStr):
            text = "".join(
                v.value for v in node.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)
            )
        else:
            continue
        if _ORDER_RE.search(text) and not _BOUND_RE.search(text):
            found.append((node.lineno, " ".join(text.split())[:160]))
    # Numbered in SOURCE order, not in `ast.walk` order: walk is breadth
    # first, so a query nested one level deeper would otherwise take `#2`
    # from a query written above it.
    seen: dict = {}
    return [
        Violation(
            _numbered(f"{path}::{norm}", seen),
            f"{path}:{lineno}: ORDER BY with no LIMIT: {norm[:80]}",
        )
        for lineno, norm in sorted(found)
    ]


# ── helpers with a test and no caller ───────────────────────────────────────

_TEST_DIR_PARTS = frozenset({"test", "tests"})


def _is_test_file(py: Path, root: Path) -> bool:
    rel = py.relative_to(root)
    if any(part in _TEST_DIR_PARTS for part in rel.parts[:-1]):
        return True
    return (py.name.startswith("test_") or py.name.endswith("_test.py")
            or py.name == "conftest.py")


def _referenced_names(tree: ast.AST, skip: ast.AST | None = None) -> set[str]:
    """Every Name id and Attribute attr in `tree`, minus `skip`'s subtree.

    Attribute attrs are included so `units._helper()` from a test that did
    `from app import units` still counts as the alibi it is.
    """
    skipped = {id(n) for n in ast.walk(skip)} if skip is not None else set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def find_test_only_helpers(package_root: str | Path) -> list[Violation]:
    """Private helpers whose only callers are tests.

    Doctrine 8.2: a test is not a caller, and dead code with a test has an
    alibi. Flags a module-level ``_name`` function that at least one test
    file references and no production file does (its own body excluded, so
    recursion is not a caller). Deliberately narrow, because every wider
    net lies in the other direction: public names are an exported contract
    whose callers live outside the tree, decorated functions are reached
    through their decorator, and a name in ``__all__`` is public by
    declaration - all skipped. A helper nothing references at all is plain
    dead code for an ordinary linter, not this alibi class.

    Matching is by bare name across the tree, without import resolution: a
    production reference to the same name anywhere clears every helper
    carrying it, which errs toward silence, never toward a false flag. A
    production file that does not parse makes every "no production caller"
    claim unknowable, so it is reported as its own violation and no helper
    is flagged from that walk (2.9: could-not-measure is not a pass; the
    key differs from the import finder's parse key, so one baseline can
    bank both).

    Returns ``Violation(key, message)``: the key is ``path::def _name``,
    position-free; the line and the alibi test files live in the message.
    """
    root = Path(package_root).resolve()
    prod: list[tuple[Path, ast.AST]] = []
    tests: list[tuple[Path, ast.AST]] = []
    violations: list[Violation] = []
    unparsable_production = False

    for py in sorted(root.rglob("*.py")):
        if "__pycache__" in str(py):
            continue
        is_test = _is_test_file(py, root)
        tree, why = _parse_file(py)
        if tree is None:
            if not is_test:
                unparsable_production = True
                violations.append(Violation(
                    f"{py}::helper callers unknowable (does not parse)",
                    f"{py}: does not parse, so no production caller can be "
                    f"counted: {why}",
                ))
            continue
        (tests if is_test else prod).append((py, tree))

    if unparsable_production:
        return violations

    for py, tree in prod:
        exported: set[str] = set()
        for n in tree.body:
            targets = (n.targets if isinstance(n, ast.Assign)
                       else [n.target] if isinstance(n, ast.AnnAssign) else [])
            if any(isinstance(t, ast.Name) and t.id == "__all__"
                   for t in targets):
                for c in ast.walk(n):
                    if isinstance(c, ast.Constant) and isinstance(c.value, str):
                        exported.add(c.value)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = node.name
            if (not name.startswith("_") or name.startswith("__")
                    or node.decorator_list or name in exported):
                continue
            prod_refs = name in _referenced_names(tree, skip=node) or any(
                name in _referenced_names(t) for p, t in prod if p != py
            )
            alibis = sorted(
                p.relative_to(root).as_posix()
                for p, t in tests if name in _referenced_names(t)
            )
            if not prod_refs and alibis:
                violations.append(Violation(
                    f"{py}::def {name}",
                    f"{py}:{node.lineno}: {name} has a test and no "
                    f"production caller (referenced only from "
                    f"{', '.join(alibis[:3])}): a test is not a caller, "
                    f"and dead code with a test has an alibi",
                ))
    return violations


def selfcheck() -> bool:
    """Plant a known-bad input for each detector and demand it is found.

    This is `selfcheck_detector`'s own argument applied to the shipped
    detectors: a detector edited into vacuity - a broken regex, a renamed
    AST node - passes every real file forever and only a planted bad case
    catches it. The clean-input cases matter equally: a detector that flags
    everything is removed from CI within a week and protects nothing after.
    """
    import tempfile

    ok = True

    def _fail(msg: str) -> None:
        nonlocal ok
        print(f"[detectors] SELFCHECK FAILED: {msg}")
        ok = False

    if not find_order_by_without_limit('q = "SELECT * FROM t ORDER BY ts"'):
        _fail("uncapped ORDER BY in a plain string was not flagged")
    if not find_order_by_without_limit('q = f"SELECT * FROM {tbl} ORDER BY ts"'):
        _fail("uncapped ORDER BY inside an f-string was not flagged")
    if find_order_by_without_limit('q = "SELECT * FROM t ORDER BY ts LIMIT 100"'):
        _fail("ORDER BY carrying a LIMIT was flagged anyway")
    if find_order_by_without_limit('q = "SELECT * FROM t"'):
        _fail("a query with no ORDER BY at all was flagged")

    # A key that moves is a baseline that re-flags what it already banked.
    shifted = find_order_by_without_limit(
        "# pushed down\n" * 9 + 'q = "SELECT * FROM t ORDER BY ts"'
    )
    flat = find_order_by_without_limit('q = "SELECT * FROM t ORDER BY ts"')
    if not shifted or shifted[0].message == flat[0].message:
        _fail("the fixture did not move; the line-shift case is vacuous")
    elif {v.key for v in shifted} != {v.key for v in flat}:
        _fail("inserting lines above a violation changed its key")

    with tempfile.TemporaryDirectory() as td:
        pkg = Path(td) / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "real.py").write_text("VALUE = 1\n")

        (pkg / "good.py").write_text("from .real import VALUE\n")
        if find_unresolved_relative_imports(pkg):
            _fail("an import that resolves was reported as broken")

        (pkg / "bad_module.py").write_text("from .nope import thing\n")
        if not find_unresolved_relative_imports(pkg):
            _fail("an import of a missing MODULE was not flagged")
        (pkg / "bad_module.py").unlink()

        (pkg / "bad_name.py").write_text("from .real import MISSING\n")
        found = find_unresolved_relative_imports(pkg)
        if not found:
            _fail("an import of a missing NAME was not flagged")
        elif any(re.search(r":\d+", v.key) for v in found):
            _fail(f"a key carries a line number: {[v.key for v in found]}")

        (pkg / "bad_name.py").write_text("import os\nfrom .real import MISSING\n")
        moved = find_unresolved_relative_imports(pkg)
        if {v.key for v in moved} != {v.key for v in found}:
            _fail("an added import line above a violation changed its key")
        (pkg / "bad_name.py").unlink()

        # R25-2, two pairs: a byte-order mark neither invents a finding nor
        # hides one, and source that does not parse is never the empty list.
        bom = b"\xef\xbb\xbf"
        (pkg / "marked.py").write_bytes(bom + b"from .real import VALUE\n")
        if find_unresolved_relative_imports(pkg):
            _fail("a BOM-prefixed file with a resolving import was flagged")
        (pkg / "marked.py").write_bytes(bom + b"from .real import MISSING\n")
        if [v.key.split("::")[1] for v in find_unresolved_relative_imports(pkg)] \
                != ["from .real import MISSING"]:
            _fail("a BOM-prefixed file's unresolved import was not the one "
                  "finding")
    if find_order_by_without_limit("\ufeff" + 'q = "SELECT * FROM t"'):
        _fail("a BOM-prefixed source with no ORDER BY was flagged")
    if not find_order_by_without_limit("def (:\n"):
        _fail("source that does not parse returned the empty list a clean "
              "source returns")

    with tempfile.TemporaryDirectory() as td:
        app = Path(td)
        (app / "tests").mkdir()
        (app / "units.py").write_text(
            "def rollup(samples):\n    return len(samples)\n\n\n"
            "def _mean(samples):\n    return 1\n"
        )
        (app / "tests" / "test_units.py").write_text(
            "import units\n\n\ndef test_mean():\n"
            "    assert units._mean([]) == 1\n"
        )
        if not find_test_only_helpers(app):
            _fail("a private helper with a test and no production caller "
                  "was not flagged")
        (app / "units.py").write_text(
            "def rollup(samples):\n    return _mean(samples)\n\n\n"
            "def _mean(samples):\n    return 1\n"
        )
        if find_test_only_helpers(app):
            _fail("a helper with a production caller was flagged anyway")

    if ok:
        print(
            "[detectors] selfcheck ok: ORDER BY (string + f-string) caught, "
            "LIMIT respected, unresolved module and name both caught, keys "
            "unchanged by lines inserted above them, test-only helper "
            "flagged and a called one left alone, a BOM-prefixed file "
            "judged as the plain one is, unparsable source not clean"
        )
    return ok


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or "--selfcheck" in argv:
        return 0 if selfcheck() else 1
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    print(
        f"[detectors] unknown argument(s): {' '.join(argv)}\n"
        f"detectors is a library; its CLI exists to run --selfcheck.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
