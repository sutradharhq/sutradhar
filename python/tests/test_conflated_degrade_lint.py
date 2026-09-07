# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Tests for the conflated-degrade guard (R18-2).

`swallow_lint` catches an `except` that logs nothing. This catches the half
it structurally cannot see: the handler logs, and returns the same value a
legitimate "there is nothing here" path returns, so the caller cannot tell
them apart and every number downstream is computed over an unknown fraction
of reality under a green status.

The load-bearing cases here are the REFUSALS - the fixed shape passes, a
re-raise passes, and a same-named sibling does not steal the first one's
banked key - because a detector that flags everything is removed from CI
within a week and protects nothing after.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards import conflated_degrade_lint as cdl  # noqa: E402

CONFLATED = '''
def read_state(keys):
    if not keys:
        return {}
    try:
        return fetch(keys)
    except Exception as exc:
        log.warning("read failed: %s", exc)
        return {}
'''

DISTINGUISHABLE = '''
def read_state(keys):
    if not keys:
        return {}, True
    try:
        return fetch(keys), True
    except Exception as exc:
        log.warning("read failed: %s", exc)
        return {}, False
'''


# ── the detector discriminates ──────────────────────────────────────────────

def test_it_flags_the_conflation():
    found = cdl.find_conflated_degrades(CONFLATED, "a.py")
    assert [f.key for f in found] == ["a.py::read_state"]
    assert found[0].line == 2


def test_the_distinguishable_version_passes():
    """The point of the guard is not to ban the fail-safe value. `(value, ok)`
    keeps the same `{}` and adds the one bit the caller was missing."""
    assert cdl.find_conflated_degrades(DISTINGUISHABLE, "a.py") == []


def test_a_handler_that_reraises_is_ignored():
    src = '''
def read_state(keys):
    if not keys:
        return {}
    try:
        return fetch(keys)
    except Exception:
        raise
'''
    assert cdl.find_conflated_degrades(src, "a.py") == []


def test_a_handler_whose_value_no_normal_path_returns_is_ignored():
    """`{}` on failure and a real value otherwise is not a conflation - the
    caller can already tell. Flagging it would make the guard noise."""
    src = '''
def read_state(keys):
    try:
        return fetch(keys)
    except Exception:
        return {}
'''
    assert cdl.find_conflated_degrades(src, "a.py") == []


def test_different_falsy_values_do_not_conflate():
    """`{}` from the handler and `None` from the empty path ARE
    distinguishable, so the tags must not be collapsed into "falsy"."""
    src = '''
def read_state(keys):
    if not keys:
        return None
    try:
        return fetch(keys)
    except Exception:
        return {}
'''
    assert cdl.find_conflated_degrades(src, "a.py") == []


def test_a_method_carries_its_class_in_the_key():
    src = '''
class Store:
    def read(self):
        if not self.k:
            return []
        try:
            return fetch(self.k)
        except Exception:
            return []
'''
    assert [f.key for f in cdl.find_conflated_degrades(src, "a.py")] == [
        "a.py::Store.read"
    ]


def test_a_nested_def_carries_its_enclosing_function():
    src = '''
def outer():
    def inner(k):
        if not k:
            return 0
        try:
            return fetch(k)
        except Exception:
            return 0
    return inner
'''
    keys = [f.key for f in cdl.find_conflated_degrades(src, "a.py")]
    assert "a.py::outer.inner" in keys


def test_a_syntax_error_is_not_a_finding():
    assert cdl.find_conflated_degrades("def (:\n", "a.py") == []


# ── the key is an identity, not a position (R18-1) ──────────────────────────

def test_the_key_holds_no_line_number():
    found = cdl.find_conflated_degrades(CONFLATED, "a.py")
    assert ":2" not in found[0].key and found[0].key == "a.py::read_state"
    # ...and the line still reaches the reader.
    assert "a.py:2" in found[0].message


def test_lines_inserted_above_do_not_change_the_key():
    flat = cdl.find_conflated_degrades(CONFLATED, "a.py")
    shifted = cdl.find_conflated_degrades("# moved\n" * 7 + CONFLATED, "a.py")
    assert shifted[0].line != flat[0].line, "the fixture did not move"
    assert {f.key for f in shifted} == {f.key for f in flat}
    # Through the real seam: nothing new, nothing stale.
    new, fixed = cdl.compare(shifted, {f.key for f in flat})
    assert new == [] and fixed == []


def test_a_same_named_sibling_does_not_steal_the_first_key():
    """Adding a second `read` must leave the first one's banked entry alone:
    the set gains a member and loses none."""
    one = cdl.find_conflated_degrades(CONFLATED, "a.py")
    two = cdl.find_conflated_degrades(CONFLATED * 2, "a.py")
    assert [f.key for f in two] == ["a.py::read_state", "a.py::read_state#2"]
    assert {f.key for f in one} < {f.key for f in two}


def test_same_named_methods_on_different_classes_key_apart():
    src = '''
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
'''
    assert [f.key for f in cdl.find_conflated_degrades(src, "a.py")] == [
        "a.py::A.read", "a.py::B.read"
    ]


# ── the ratchet ─────────────────────────────────────────────────────────────

def test_compare_reports_a_new_conflation_and_a_separated_one():
    banked = {f.key for f in cdl.find_conflated_degrades(CONFLATED, "a.py")}
    two = cdl.find_conflated_degrades(CONFLATED + '''
def other_read(k):
    if not k:
        return None
    try:
        return fetch(k)
    except Exception:
        return None
''', "a.py")
    new, fixed = cdl.compare(two, banked)
    assert [f.key for f in new] == ["a.py::other_read"] and fixed == []

    # The guard-the-guard half: a banked entry that is no longer a finding
    # must be reported, or the floor silently stops meaning anything.
    new, fixed = cdl.compare(
        cdl.find_conflated_degrades(DISTINGUISHABLE, "a.py"), banked
    )
    assert new == [] and fixed == ["a.py::read_state"]


# ── the CLI, through the seam an adopter actually runs ──────────────────────

def _tree(tmp_path, body=CONFLATED, name="app.py"):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / name).write_text(body)
    return src


def test_the_cli_gates_records_and_holds(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = _tree(tmp_path)
    base = tmp_path / "b.json"

    assert cdl.main([str(src), "--baseline", str(base)]) == 1      # unbanked
    assert cdl.main([str(src), "--baseline", str(base),
                     "--update-baseline"]) == 0
    assert json.loads(base.read_text()) == ["src/app.py::read_state"]
    assert cdl.main([str(src), "--baseline", str(base)]) == 0      # at floor

    # An edit above the finding must not re-flag it. This is R18-1 asserted
    # end to end, on the guard that was ported with the fix.
    (src / "app.py").write_text('"""Added."""\nimport os\n' + CONFLATED)
    assert cdl.main([str(src), "--baseline", str(base)]) == 0


def test_the_cli_fails_when_a_banked_entry_is_fixed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = _tree(tmp_path)
    base = tmp_path / "b.json"
    cdl.main([str(src), "--baseline", str(base), "--update-baseline"])
    (src / "app.py").write_text(DISTINGUISHABLE)
    assert cdl.main([str(src), "--baseline", str(base)]) == 1


def test_an_unknown_flag_is_refused_with_two(tmp_path):
    assert cdl.main([str(tmp_path), "--selfchek"]) == 2


def test_no_path_is_refused_rather_than_assumed(tmp_path, capsys):
    """A default directory nobody named would report OK over a tree nothing
    read - the exact class of lie this guard exists to catch (2.4)."""
    assert cdl.main(["--baseline", str(tmp_path / "b.json")]) == 2
    assert "nothing was scanned" in capsys.readouterr().err


def test_a_blinded_detector_fails_the_cli(tmp_path, monkeypatch):
    """The wiring test: the path from "the detector went vacuous" to "CI goes
    red" is itself under test. A clean tree is green; the same clean tree
    with the detector blinded must go red, because the embedded selfcheck no
    longer finds its planted bad case."""
    monkeypatch.chdir(tmp_path)
    clean = _tree(tmp_path, body="x = 1\n")
    base = tmp_path / "b.json"
    assert cdl.main([str(clean), "--baseline", str(base)]) == 0
    monkeypatch.setattr(cdl, "find_conflated_degrades", lambda *a, **k: [])
    assert cdl.main([str(clean), "--baseline", str(base)]) == 1


def test_the_walk_skips_vendor_trees_and_says_so(tmp_path, monkeypatch, capsys):
    """B-2: ~80 third-party findings once buried the one real one and the
    guard was switched off that afternoon."""
    monkeypatch.chdir(tmp_path)
    src = _tree(tmp_path)
    vendor = src / ".venv" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "dep.py").write_text(CONFLATED)
    assert cdl.main([str(src), "--baseline", str(tmp_path / "b.json"),
                     "--update-baseline"]) == 0
    out = capsys.readouterr().out
    assert "skipped 1 file(s) under vendor" in out
    assert json.loads((tmp_path / "b.json").read_text()) == [
        "src/app.py::read_state"
    ]


def test_an_explicitly_named_vendor_path_is_still_scanned(tmp_path, monkeypatch):
    """Pointing the guard at a vendor tree on purpose must not print OK over
    a directory nothing read."""
    monkeypatch.chdir(tmp_path)
    vendor = tmp_path / ".venv" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "dep.py").write_text(CONFLATED)
    assert cdl.main([str(vendor), "--baseline", str(tmp_path / "b.json")]) == 1


def test_the_selfcheck_passes():
    assert cdl.selfcheck()


def test_the_selfcheck_names_what_it_exercised(capsys):
    """6.7: a silent exit 0 cannot be told from a check that never ran."""
    cdl.selfcheck()
    out = capsys.readouterr().out
    assert "conflated-degrade-lint" in out
    for claim in ("conflation caught", "re-raise passed", "keyed apart"):
        assert claim in out, out


@pytest.mark.parametrize("name,vacuous", [
    ("conflates", lambda *a, **k: False),
    ("functions_with_qualnames", lambda *a, **k: []),
])
def test_a_blinded_internal_reddens_the_selfcheck(monkeypatch, name, vacuous):
    """Mutation, committed: neither half of the detector may go vacuous
    without the selfcheck saying so."""
    monkeypatch.setattr(cdl, name, vacuous)
    assert not cdl.selfcheck()
