"""framework_only - Sutradhar is a framework, and this keeps it one.

Sutradhar is a framework-harness, not a product-harness: a copy-in toolkit of
stdlib-only guards, a doctrine, and the agent workflow around them. It ships
no runtime and installs nothing. That is a promise a reader relies on, and a
promise in prose alone is the exact thing this framework distrusts - a rule
that lives only in a sentence gets dropped under deadline pressure. So the
promise is a gate.

Two properties, both mechanically checkable:

1. **The guards import the standard library only.** The shipped Python surface
   (`sutradhar_guards/*.py`) may import stdlib and its own package, nothing
   else. The first `import requests` is the moment the toolkit stops being
   copy-in and starts being pip-install, i.e. a product.

2. **The framework declares no dependencies.** No packaging or dependency
   manifest in the framework surface - no `requirements.txt`, `pyproject.toml`,
   `setup.py`, `package.json`, or lockfile. `examples/` is exempt: an example
   is allowed to be a real application with real dependencies; that is what it
   is for. Everything else is the framework, and the framework installs
   nothing.

Neither check decides what counts as "product code" - that is the ungameable
trap `budget.py` warns about, a definition either noisy or trivially satisfied.
These two check the properties that cannot be fudged: an import list and the
presence of a manifest. The day either has to change is the day someone is
turning the framework into a product, and this gate makes that a conscious
diff rather than a quiet drift.

    python framework_only.py .            # gate the repo (exit nonzero on drift)
    python framework_only.py . --guards python/sutradhar_guards
    python framework_only.py --selfcheck  # planted bad cases must be caught
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

# Packaging / dependency manifests. Their presence in the framework surface
# means the toolkit has taken on an install step; examples/ is exempt.
DEP_MANIFESTS = (
    "requirements.txt", "requirements-dev.txt", "setup.py", "setup.cfg",
    "pyproject.toml", "Pipfile", "poetry.lock",
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
)
_KNOWN_FLAGS = {"--guards", "--surface", "--selfcheck", "--help", "-h"}


class Violation:
    """One framework-only breach: a path and why it is a breach."""
    __slots__ = ("path", "why")

    def __init__(self, path: str, why: str) -> None:
        self.path = path
        self.why = why

    def __repr__(self) -> str:
        return f"{self.path}: {self.why}"


# ── import purity ────────────────────────────────────────────────────────────

class _TopLevelImports(ast.NodeVisitor):
    """Collect imports at MODULE scope only. A `def`/`class` boundary is
    opaque: an import inside a function is a lazy, deferred dependency (the
    escape hatch for optional integration - `envgate` imports pytest this way,
    firing only inside a pytest run where pytest is definitionally present),
    and it does not make the module require that package to be importable.
    Module-level `if`/`try`/`with`/`for` are still descended - a load-time
    import stays load-time however it is guarded."""

    def __init__(self) -> None:
        self.roots: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        pass  # do not recurse into function bodies

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        pass  # nor class bodies

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            self.roots.add(alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.level == 0 and node.module:  # skip `from . import x`
            self.roots.add(node.module.split(".")[0])


def _import_roots(source: str) -> set[str]:
    """Top-level package roots imported by a module (module scope only),
    skipping relative imports and `__future__`."""
    visitor = _TopLevelImports()
    visitor.visit(ast.parse(source))
    visitor.roots.discard("__future__")
    return visitor.roots


def _origin_is_thirdparty(origin: str | None) -> bool:
    """True when a module's resolved file sits in an installed-package tree.
    A pure helper so the site-packages branch is testable without installing
    anything."""
    if not origin:
        return False
    parts = Path(origin).parts
    return "site-packages" in parts or "dist-packages" in parts


def classify_import(root: str, own_package: str) -> str:
    """One of 'stdlib' | 'thirdparty' | 'missing'. `find_spec` locates the
    module without executing it; a root that will not resolve is 'missing'
    (a typo or an uninstalled dependency - either way not stdlib)."""
    if root == own_package:
        return "stdlib"  # the package importing itself is not a dependency
    try:
        spec = importlib.util.find_spec(root)
    except (ImportError, ValueError):
        return "missing"
    if spec is None:
        return "missing"
    if spec.origin in ("built-in", "frozen") or spec.origin is None:
        return "stdlib"
    return "thirdparty" if _origin_is_thirdparty(spec.origin) else "stdlib"


def find_nonstdlib_guard_imports(guards_dir: Path) -> list[Violation]:
    """Every non-stdlib import in the shipped Python guard surface."""
    own = guards_dir.name
    out: list[Violation] = []
    for py in sorted(guards_dir.glob("*.py")):
        try:
            roots = _import_roots(py.read_text(encoding="utf-8"))
        except (SyntaxError, OSError) as exc:
            out.append(Violation(str(py), f"could not parse: {exc}"))
            continue
        for root in sorted(roots):
            kind = classify_import(root, own)
            if kind == "thirdparty":
                out.append(Violation(str(py), f"imports third-party `{root}` - "
                                     f"the guards must be stdlib-only"))
            elif kind == "missing":
                out.append(Violation(str(py), f"imports `{root}`, which does not "
                                     f"resolve to the stdlib - a dependency or a typo"))
    return out


# ── no dependency manifest ───────────────────────────────────────────────────

def find_dependency_manifests(root: Path, exclude: tuple[str, ...]) -> list[Violation]:
    """Any packaging/dependency manifest in the framework surface. `exclude`
    names top-level directories that may carry manifests (examples, and VCS/
    tooling dirs) - an example is allowed to be a real application."""
    out: list[Violation] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name not in DEP_MANIFESTS:
            continue
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in exclude:
            continue
        out.append(Violation(str(rel), f"a `{path.name}` in the framework "
                             f"surface means an install step - the framework "
                             f"declares no dependencies (examples/ is exempt)"))
    return out


DEFAULT_EXCLUDE = ("examples", ".git", ".github", "node_modules", ".venv")


def check(repo: Path, guards_dir: Path) -> list[Violation]:
    return (find_nonstdlib_guard_imports(guards_dir)
            + find_dependency_manifests(repo, DEFAULT_EXCLUDE))


# ── selfcheck ────────────────────────────────────────────────────────────────

def selfcheck() -> bool:
    try:
        return _selfcheck_body()
    except Exception as exc:  # noqa: BLE001
        print(f"[framework_only] SELFCHECK FAILED: the selfcheck itself raised "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return False


def _selfcheck_body() -> bool:
    import tempfile

    ok = True

    # The thirdparty/stdlib classifier, tested on synthetic origins so the
    # site-packages branch needs nothing installed.
    if not _origin_is_thirdparty("/x/lib/python3.12/site-packages/requests/__init__.py"):
        print("[framework_only] SELFCHECK FAILED: a site-packages origin read "
              "as stdlib", file=sys.stderr)
        ok = False
    if _origin_is_thirdparty("/usr/lib/python3.12/os.py"):
        print("[framework_only] SELFCHECK FAILED: a stdlib origin read as "
              "third-party", file=sys.stderr)
        ok = False
    if classify_import("os", "sutradhar_guards") != "stdlib":
        print("[framework_only] SELFCHECK FAILED: `os` did not classify as stdlib",
              file=sys.stderr)
        ok = False
    if classify_import("__sutradhar_absent_module__", "sutradhar_guards") != "missing":
        print("[framework_only] SELFCHECK FAILED: an absent module did not "
              "classify as missing", file=sys.stderr)
        ok = False

    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)

        # A guard dir: one clean stdlib-only file, one importing an absent
        # module. The clean file must pass; the dirty one must be caught.
        guards = tmp / "sutradhar_guards"
        guards.mkdir()
        (guards / "clean.py").write_text("import os, json\nfrom pathlib import Path\n")
        (guards / "dirty.py").write_text("import __sutradhar_absent_module__\n")
        # The escape hatch: a lazy import inside a function is deferred and must
        # NOT be flagged - this is exactly how envgate carries pytest.
        (guards / "lazy.py").write_text(
            "import os\n\n\ndef run():\n    import __sutradhar_absent_module__\n    return __sutradhar_absent_module__\n")
        imports = find_nonstdlib_guard_imports(guards)
        flagged = {Path(v.path).name for v in imports}
        if "clean.py" in flagged:
            print("[framework_only] SELFCHECK FAILED: a stdlib-only guard was "
                  "flagged", file=sys.stderr)
            ok = False
        if "dirty.py" not in flagged:
            print("[framework_only] SELFCHECK FAILED: a guard importing an absent "
                  "module was NOT flagged - the import check is decoration",
                  file=sys.stderr)
            ok = False
        if "lazy.py" in flagged:
            print("[framework_only] SELFCHECK FAILED: a lazy import inside a "
                  "function was flagged - the deferred-integration escape hatch "
                  "is broken (this is how envgate carries pytest)", file=sys.stderr)
            ok = False

        # The surface: a planted requirements.txt must be caught; an identical
        # manifest under examples/ must be exempt.
        (tmp / "requirements.txt").write_text("requests==2.0\n")
        (tmp / "examples").mkdir()
        (tmp / "examples" / "requirements.txt").write_text("flask\n")
        manifests = find_dependency_manifests(tmp, DEFAULT_EXCLUDE)
        paths = {v.path for v in manifests}
        if "requirements.txt" not in paths:
            print("[framework_only] SELFCHECK FAILED: a requirements.txt in the "
                  "surface was NOT flagged - the manifest check is decoration",
                  file=sys.stderr)
            ok = False
        if any("examples" in p for p in paths):
            print("[framework_only] SELFCHECK FAILED: a manifest under examples/ "
                  "was flagged - examples are allowed to be real apps", file=sys.stderr)
            ok = False

    if ok:
        print("[framework_only] selfcheck ok: classifier separates stdlib from "
              "third-party and missing, guard-import and manifest checks each "
              "catch a planted breach, examples/ stays exempt")
    return ok


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--selfcheck" in argv:
        return 0 if selfcheck() else 1

    guards = "python/sutradhar_guards"
    positional: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--guards":
            guards = argv[i + 1]; i += 2
        elif argv[i] == "--surface":
            positional.append(argv[i + 1]); i += 2
        elif argv[i].startswith("--"):
            # An unrecognised flag is never ignored: a silent skip lets a typo
            # like `--selfchek` run the default scan and exit 0, reading as a pass.
            if argv[i] not in _KNOWN_FLAGS:
                print(f"[framework_only] unknown flag: {argv[i]}", file=sys.stderr)
                return 2
            i += 1
        else:
            positional.append(argv[i]); i += 1

    if not selfcheck():
        return 1

    repo = Path(positional[0] if positional else ".")
    guards_dir = Path(guards) if Path(guards).is_absolute() else repo / guards
    if not guards_dir.is_dir():
        print(f"[framework_only] no guard directory at {guards_dir}. Pass "
              f"--guards to point at the stdlib-only surface.", file=sys.stderr)
        return 2

    violations = check(repo, guards_dir)
    if violations:
        print(f"\n[framework_only] {len(violations)} breach(es) of the "
              f"framework-only promise:\n")
        for v in violations:
            print(f"  {v.path}\n    {v.why}")
        print("\nSutradhar is a framework, not a product (DOCTRINE.md preamble). "
              "If this change is deliberate, that is a framework-to-product "
              "decision - make it in the open, not by letting the gate rot.")
        return 1
    print("[framework_only] OK - guards are stdlib-only and the framework "
          "declares no dependencies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
