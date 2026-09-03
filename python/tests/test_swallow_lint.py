"""Tests for swallow_lint - including the red cases.

Every guard here is itself mutation-verified: for each thing the detector
must catch there is a test that FAILS if the detector goes blind to it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.swallow_lint import (
    VENDOR_DIRS,
    _is_vendor,
    check_source,
    main,
    selfcheck,
)


def test_flags_return_empty_dict():
    src = """
def f():
    try:
        risky()
    except Exception:
        return {}
"""
    assert len(check_source(src)) == 1


def test_flags_bare_except_pass():
    src = """
def f():
    try:
        risky()
    except:
        pass
"""
    assert len(check_source(src)) == 1


def test_flags_tuple_handler_containing_exception():
    src = """
def f():
    try:
        risky()
    except (ValueError, Exception):
        return None
"""
    assert len(check_source(src)) == 1


def test_flags_continue_in_loop():
    src = """
def f(items):
    for i in items:
        try:
            risky(i)
        except Exception:
            continue
"""
    assert len(check_source(src)) == 1


def test_logged_swallow_is_clean():
    src = """
def f():
    try:
        risky()
    except Exception as exc:
        log.warning(f"degraded: {exc}")
        return {}
"""
    assert check_source(src) == []


def test_reraise_is_clean():
    src = """
def f():
    try:
        risky()
    except Exception:
        cleanup()
        raise
"""
    assert check_source(src) == []


def test_narrow_handler_is_clean():
    # A narrow catch that returns empty is a judgment call, not a swallow of
    # the world - the guard only polices broad handlers.
    src = """
def f():
    try:
        risky()
    except KeyError:
        return {}
"""
    assert check_source(src) == []


def test_custom_degrade_call_is_clean():
    src = """
def f():
    try:
        risky()
    except Exception:
        mark_degraded("f")
        return {}
"""
    assert check_source(src, extra_calls={"mark_degraded"}) == []


def test_handler_doing_real_work_is_clean():
    src = """
def f():
    try:
        risky()
    except Exception:
        result = fallback_computation()
        return result
"""
    assert check_source(src) == []


def test_selfcheck_passes():
    assert selfcheck()


def test_baseline_ratchet_flow(tmp_path, monkeypatch):
    """End to end: baseline freezes today, a new swallow beyond it fails."""
    monkeypatch.chdir(tmp_path)
    mod = tmp_path / "m.py"
    mod.write_text(
        "def f():\n    try:\n        g()\n    except Exception:\n        return {}\n"
    )
    baseline = tmp_path / "swallow_baseline.json"

    assert main([str(mod), "--update-baseline", "--baseline", str(baseline)]) == 0
    assert json.loads(baseline.read_text()) == {"m.py": 1}

    # At the baseline: green.
    assert main([str(mod), "--baseline", str(baseline)]) == 0

    # One MORE swallow: red. This is the mutation case for the ratchet.
    mod.write_text(
        mod.read_text()
        + "def h():\n    try:\n        g()\n    except Exception:\n        return []\n"
    )
    assert main([str(mod), "--baseline", str(baseline)]) == 1


# ── vendor trees: the guard must not be buried by findings nobody can fix ────
# Field report from an adopting repo: pointed at the project root, the walk
# descended into `.venv` and returned ~80 third-party swallows around the one
# real finding in `app/`. The guard was switched off that afternoon - not
# because it was wrong, but because its signal was unreadable. A guard whose
# output nobody reads has stopped guarding (2.1).


def _plant_vendor_tree(root: Path) -> Path:
    """One real swallow in app/, three inside a virtualenv."""
    swallow = "def f():\n    try:\n        g()\n    except Exception:\n        return {}\n"
    (root / "app").mkdir(parents=True)
    (root / "app" / "real.py").write_text(swallow)
    vendor = root / ".venv" / "lib" / "python3.11" / "site-packages" / "pkg"
    vendor.mkdir(parents=True)
    for i in range(3):
        (vendor / f"v{i}.py").write_text(swallow)
    return root / "app" / "real.py"


def test_the_walk_skips_vendor_trees_and_still_finds_the_real_one(tmp_path, capsys):
    _plant_vendor_tree(tmp_path)
    rc = main([str(tmp_path), "--baseline", str(tmp_path / "none.json")])
    out = capsys.readouterr().out
    assert rc == 1, "the real swallow in app/ must still fail the gate"

    # The findings block - everything after the "NEW silent swallow(s)"
    # header - must name the real file and no vendor one. Asserting against
    # the whole of stdout would pass vacuously off the skip notice, which
    # legitimately contains vendor directory names.
    findings = out.split("NEW silent swallow(s)", 1)[1]
    assert "app/real.py" in findings
    assert "site-packages" not in findings, findings
    assert "v0.py" not in findings, findings


def test_the_skip_is_reported_never_silent(tmp_path, capsys):
    """2.4 applied to the guard itself: an exclusion the operator cannot see
    is 'OK' printed over a tree nothing read. Deleting the notice must fail
    this test even though the scan result is unchanged."""
    _plant_vendor_tree(tmp_path)
    main([str(tmp_path), "--baseline", str(tmp_path / "none.json")])
    out = capsys.readouterr().out
    assert "skipped 3 file(s)" in out, out
    assert "--include-vendor" in out, "the notice must name the way to override it"


def test_include_vendor_scans_everything(tmp_path, capsys):
    """The override is real, not decoration: with it, all four are found."""
    _plant_vendor_tree(tmp_path)
    rc = main([
        str(tmp_path), "--include-vendor", "--baseline", str(tmp_path / "none.json")
    ])
    out = capsys.readouterr().out
    assert rc == 1
    assert out.count("v0.py") >= 1 and out.count("v1.py") >= 1 and out.count("v2.py") >= 1
    assert "skipped" not in out


def test_an_explicitly_named_vendor_file_is_still_scanned(tmp_path):
    """Only the WALK excludes. Asking for a vendor path by name and getting a
    silent pass would be the same lie in the other direction."""
    _plant_vendor_tree(tmp_path)
    target = tmp_path / ".venv" / "lib" / "python3.11" / "site-packages" / "pkg" / "v0.py"
    assert main([str(target), "--baseline", str(tmp_path / "none.json")]) == 1


def test_is_vendor_judges_relative_to_the_named_root(tmp_path):
    """The asymmetry in one assertion: the same file is vendor when reached by
    walking the project, and first-party when the venv itself is the root."""
    f = tmp_path / ".venv" / "pkg" / "x.py"
    f.parent.mkdir(parents=True)
    f.write_text("")
    assert _is_vendor(f, tmp_path) is True
    assert _is_vendor(f, tmp_path / ".venv") is False


def test_vendor_list_excludes_dirs_that_are_often_real_source():
    """A too-greedy exclusion silently stops scanning the adopter's code -
    the failure mode this whole change is trying to avoid, inverted. `build`,
    `dist` and `env` are real package names in real projects."""
    for risky in ("build", "dist", "env", "src", "app", "lib", "test", "tests"):
        assert risky not in VENDOR_DIRS, risky
