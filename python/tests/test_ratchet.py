import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.envgate import EnvGate, audit_skip_gates
from sutradhar_guards.ratchet import Ratchet, RatchetError, selfcheck_detector


def test_new_violation_fails(tmp_path):
    r = Ratchet(tmp_path / "b.json")
    r.assert_only_shrinks(["a.py:10"], update=True)
    with pytest.raises(RatchetError, match="NEW violation"):
        r.assert_only_shrinks(["a.py:10", "b.py:20"])


def test_stale_entry_fails_until_banked(tmp_path):
    """The guard-the-guard case: a fixed violation must leave the baseline."""
    r = Ratchet(tmp_path / "b.json")
    r.assert_only_shrinks(["a.py:10", "b.py:20"], update=True)
    with pytest.raises(RatchetError, match="no longer violations"):
        r.assert_only_shrinks(["a.py:10"])
    # Bank it, then green.
    r.assert_only_shrinks(["a.py:10"], update=True)
    r.assert_only_shrinks(["a.py:10"])


def test_at_baseline_is_green(tmp_path):
    r = Ratchet(tmp_path / "b.json")
    r.assert_only_shrinks(["x"], update=True)
    r.assert_only_shrinks(["x"])


def test_empty_baseline_missing_file_flags_everything(tmp_path):
    r = Ratchet(tmp_path / "does_not_exist.json")
    with pytest.raises(RatchetError, match="NEW violation"):
        r.assert_only_shrinks(["a.py:1"])


def test_count_mode_grow_and_shrink(tmp_path):
    r = Ratchet(tmp_path / "c.json")
    r.assert_counts_only_shrink({"a.py": 2}, update=True)
    r.assert_counts_only_shrink({"a.py": 2})
    with pytest.raises(RatchetError, match="NEW"):
        r.assert_counts_only_shrink({"a.py": 3})
    with pytest.raises(RatchetError, match="no longer"):
        r.assert_counts_only_shrink({"a.py": 1})


def test_env_var_triggers_update(tmp_path, monkeypatch):
    monkeypatch.setenv("RATCHET_UPDATE", "1")
    r = Ratchet(tmp_path / "b.json")
    r.assert_only_shrinks(["fresh"])  # would fail without update mode
    monkeypatch.delenv("RATCHET_UPDATE")
    r.assert_only_shrinks(["fresh"])


def test_selfcheck_detector_red_on_blind_detector():
    with pytest.raises(RatchetError, match="selfcheck failed"):
        selfcheck_detector(lambda src: [], "obviously bad input")
    selfcheck_detector(lambda src: ["hit"], "obviously bad input")


# ── envgate ─────────────────────────────────────────────────────────────────

def test_audit_flags_env_var_nothing_sets(tmp_path):
    (tmp_path / "ci.yml").write_text("env:\n  FULL_STACK: '1'\n")
    gates = [
        EnvGate("requires_full_stack", "FULL_STACK"),
        EnvGate("requires_gpu", "GPU_TIER"),
    ]
    missing = audit_skip_gates(gates, ["ci.yml"], root=tmp_path)
    assert missing == ["GPU_TIER"]


def test_audit_fails_loudly_when_no_files_match(tmp_path):
    missing = audit_skip_gates(
        [EnvGate("m", "SOME_VAR")], ["nonexistent/*.yml"], root=tmp_path
    )
    assert missing and "no files matched" in missing[0]
