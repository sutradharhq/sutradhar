"""Tests for the framework-only gate.

The load-bearing cases are the DIRECTIONS: a stdlib-only guard passes, a
top-level third-party import is caught, and a lazy import inside a function is
NOT caught (the escape hatch envgate uses for pytest). A gate that only ever
said "clean" would pass this repo vacuously.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.framework_only import (
    DEFAULT_EXCLUDE,
    _import_roots,
    _origin_is_thirdparty,
    check,
    classify_import,
    find_dependency_manifests,
    find_nonstdlib_guard_imports,
    selfcheck,
)


def test_selfcheck_passes():
    assert selfcheck() is True


def test_the_repo_itself_is_framework_only():
    """The whole point: run the gate against this repository and it passes."""
    repo = Path(__file__).resolve().parents[2]
    assert check(repo, repo / "python" / "sutradhar_guards") == []


# ── import classification ────────────────────────────────────────────────────

def test_stdlib_third_party_and_missing_are_separated():
    assert classify_import("os", "sutradhar_guards") == "stdlib"
    assert classify_import("__does_not_exist__", "sutradhar_guards") == "missing"
    assert classify_import("sutradhar_guards", "sutradhar_guards") == "stdlib"


def test_origin_paths_classify_by_install_tree():
    assert _origin_is_thirdparty("/x/site-packages/requests/__init__.py") is True
    assert _origin_is_thirdparty("/x/dist-packages/foo.py") is True
    assert _origin_is_thirdparty("/usr/lib/python3.12/os.py") is False
    assert _origin_is_thirdparty(None) is False


def test_only_top_level_imports_count():
    """A lazy import inside a function is deferred and must not register -
    this is exactly how envgate carries pytest."""
    assert _import_roots("import os\nimport json\n") == {"os", "json"}
    assert _import_roots("import os\n\ndef f():\n    import requests\n") == {"os"}
    assert _import_roots("class C:\n    import requests\n") == set()
    # module-level try/if IS load-time and still counts
    assert _import_roots("try:\n    import cjson\nexcept ImportError:\n    cjson=None\n") == {"cjson"}
    assert _import_roots("from . import sibling\n") == set()


# ── guard-import scan ────────────────────────────────────────────────────────

def test_a_top_level_third_party_guard_import_is_caught(tmp_path):
    g = tmp_path / "sutradhar_guards"
    g.mkdir()
    (g / "ok.py").write_text("import os\nfrom pathlib import Path\n")
    (g / "bad.py").write_text("import __absent_dep__\n")
    flagged = {Path(v.path).name for v in find_nonstdlib_guard_imports(g)}
    assert "bad.py" in flagged and "ok.py" not in flagged


def test_a_lazy_third_party_guard_import_is_allowed(tmp_path):
    g = tmp_path / "sutradhar_guards"
    g.mkdir()
    (g / "lazy.py").write_text("import os\n\n\ndef run():\n    import __absent_dep__\n")
    assert find_nonstdlib_guard_imports(g) == []


# ── dependency manifests ─────────────────────────────────────────────────────

def test_a_dependency_manifest_in_the_surface_is_caught(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests\n")
    paths = {v.path for v in find_dependency_manifests(tmp_path, DEFAULT_EXCLUDE)}
    assert "requirements.txt" in paths


def test_a_manifest_under_examples_is_exempt(tmp_path):
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "package.json").write_text('{"dependencies":{"x":"1"}}')
    assert find_dependency_manifests(tmp_path, DEFAULT_EXCLUDE) == []
