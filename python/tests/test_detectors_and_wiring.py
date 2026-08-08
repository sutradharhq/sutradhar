"""Tests for the shipped detectors, plus the selfcheck WIRING tests.

The wiring tests answer a specific review point: "nothing proves the guard
fails". Each lint CLI runs its embedded selfcheck before scanning; these
tests blind the detector and assert the CLI exits nonzero - so the path
from "detector went vacuous" to "CI goes red" is itself under test.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards import interpolation_lint, swallow_lint
from sutradhar_guards.detectors import (
    find_order_by_without_limit,
    find_unresolved_relative_imports,
)


# ── import-integrity detector ───────────────────────────────────────────────

def _mkpkg(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "util.py").write_text("def helper():\n    return 1\nVALUE = 2\n")
    return pkg


def test_resolvable_imports_are_clean(tmp_path):
    pkg = _mkpkg(tmp_path)
    (pkg / "main.py").write_text("from .util import helper, VALUE\n")
    assert find_unresolved_relative_imports(pkg) == []


def test_missing_module_is_flagged(tmp_path):
    pkg = _mkpkg(tmp_path)
    (pkg / "main.py").write_text("from .nowhere import thing\n")
    v = find_unresolved_relative_imports(pkg)
    assert len(v) == 1 and "unresolved relative import" in v[0]


def test_missing_name_in_real_module_is_flagged(tmp_path):
    # The killer case: the module exists but the NAME does not - a NameError
    # a helper-level unit test can never see.
    pkg = _mkpkg(tmp_path)
    (pkg / "main.py").write_text("from .util import helper, renamed_away\n")
    v = find_unresolved_relative_imports(pkg)
    assert len(v) == 1 and "renamed_away" in v[0]


def test_submodule_import_from_package_is_clean(tmp_path):
    pkg = _mkpkg(tmp_path)
    sub = pkg / "adapters"
    sub.mkdir()
    (sub / "__init__.py").write_text("")
    (sub / "csv.py").write_text("X = 1\n")
    (pkg / "main.py").write_text("from .adapters import csv\n")
    assert find_unresolved_relative_imports(pkg) == []


# ── ORDER BY detector ───────────────────────────────────────────────────────

def test_unbounded_order_by_is_flagged():
    src = 'q = "SELECT * FROM readings ORDER BY ts DESC"\n'
    assert len(find_order_by_without_limit(src)) == 1


def test_bounded_order_by_is_clean():
    src = 'q = "SELECT * FROM readings ORDER BY ts DESC LIMIT 100"\n'
    assert find_order_by_without_limit(src) == []


def test_fstring_order_by_is_seen():
    src = 'q = f"SELECT * FROM r WHERE t = {t} ORDER BY ts"\n'
    assert len(find_order_by_without_limit(src)) == 1


# ── selfcheck wiring: a blinded detector must fail the CLI ──────────────────

def test_blinded_swallow_detector_fails_the_cli(tmp_path, monkeypatch):
    clean = tmp_path / "clean.py"
    clean.write_text("x = 1\n")
    # Sanity: with a working detector the scan of a clean file is green.
    assert swallow_lint.main([str(clean), "--baseline", str(tmp_path / "b.json")]) == 0
    # Blind the detector: the CLI must go red on the SAME clean input,
    # because its embedded selfcheck no longer finds the planted bad case.
    monkeypatch.setattr(swallow_lint, "check_source", lambda *a, **k: [])
    assert swallow_lint.main([str(clean), "--baseline", str(tmp_path / "b.json")]) == 1


def test_blinded_interpolation_detector_fails_the_cli(tmp_path, monkeypatch):
    clean = tmp_path / "clean.py"
    clean.write_text("x = 1\n")
    assert interpolation_lint.main([str(clean), "--keywords", "sql"]) == 0
    monkeypatch.setattr(interpolation_lint, "check_source", lambda *a, **k: [])
    assert interpolation_lint.main([str(clean), "--keywords", "sql"]) == 1


# ── class ratchet: no package export may shadow a submodule ─────────────────

def test_no_export_shadows_a_submodule():
    """A package attribute with the same name as a submodule makes
    `sutradhar_guards.X` mean the export or the module depending on import
    order - a bug that only appears when a *second* test file imports things
    in a different sequence.

    Scar: `__init__` re-exported the `budget` context manager from the
    `budget` module. test_budget.py passed alone and five of its tests
    failed in the full suite. This walks every submodule instead of pinning
    the one instance (doctrine 2.1)."""
    import importlib
    import pkgutil

    import sutradhar_guards

    shadowed = []
    for info in pkgutil.iter_modules(sutradhar_guards.__path__):
        exported = getattr(sutradhar_guards, info.name, None)
        if exported is None:
            continue
        module = importlib.import_module(f"sutradhar_guards.{info.name}")
        if exported is not module:
            shadowed.append(
                f"sutradhar_guards.{info.name} resolves to "
                f"{type(exported).__name__} {exported!r}, not the submodule"
            )
    assert not shadowed, "\n".join(shadowed)
