"""Ready-made detectors for the Ratchet library.

Two class detectors with proven records, shipped so a new project's first
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
"""
from __future__ import annotations

import ast
import re
from pathlib import Path


def find_unresolved_relative_imports(package_root: str | Path) -> list[str]:
    """Every ``from .x import y`` in the package must resolve.

    Checks that the target MODULE exists on disk, and - when the target
    module parses - that each imported NAME is actually defined in it
    (top-level def/class/assignment/import/star-export). Returns
    "file:line: message" strings for the ratchet.
    """
    root = Path(package_root).resolve()
    violations: list[str] = []

    for py in sorted(root.rglob("*.py")):
        if "__pycache__" in str(py):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            violations.append(f"{py}:{e.lineno}: does not parse: {e.msg}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level == 0:
                continue
            # Resolve the base directory for `from ..mod import name`.
            base = py.parent
            for _ in range(node.level - 1):
                base = base.parent
            target = base / node.module.replace(".", "/") if node.module else base
            mod_file = target.with_suffix(".py")
            pkg_init = target / "__init__.py"
            if mod_file.exists():
                _check_names(py, node, mod_file, violations, is_package_dir=None)
            elif pkg_init.exists():
                _check_names(py, node, pkg_init, violations, is_package_dir=target)
            else:
                violations.append(
                    f"{py}:{node.lineno}: unresolved relative import "
                    f"'{'.' * node.level}{node.module or ''}'"
                )
    return violations


def _module_exports(mod_file: Path) -> set[str] | None:
    """Top-level names a module defines. None = could not parse (skip)."""
    try:
        tree = ast.parse(mod_file.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
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
                 violations: list[str], is_package_dir: Path | None) -> None:
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
        violations.append(
            f"{src}:{node.lineno}: '{alias.name}' is not defined in "
            f"{mod_file.name}"
        )


# ── unbounded ORDER BY ──────────────────────────────────────────────────────

_ORDER_RE = re.compile(r"\bORDER\s+BY\b", re.I)
_BOUND_RE = re.compile(r"\bLIMIT\b|\bFETCH\s+FIRST\b|\bTOP\s+\d", re.I)


def find_order_by_without_limit(source: str) -> list[int]:
    """Line numbers of string literals containing ORDER BY with no LIMIT.

    Doctrine 2.6: ORDER BY on an unbounded result set is a memory bomb -
    the store materializes and sorts the whole set. This walks every string
    constant AND every f-string's literal parts, so query fragments built
    either way are seen. Queries that carry their bound in a separate
    fragment belong in the ratchet baseline with a comment.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    hits: list[int] = []
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
            hits.append(node.lineno)
    return hits
