import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.claim_check import extract_numbers, ground_claims, selfcheck
from sutradhar_guards.golden import GoldenError, GoldenGate


# ── claim check ─────────────────────────────────────────────────────────────

def test_extracts_currency_shorthand():
    nums = extract_numbers("recovered ₹2.1Cr and saved ₹5L this quarter")
    assert {(n["value"], n["unit"]) for n in nums} == {
        (21_000_000.0, "INR"), (500_000.0, "INR"),
    }


def test_extracts_percent_and_units():
    nums = extract_numbers("losses fell to 12.4% on 1,240 kWh")
    assert {(n["value"], n["unit"]) for n in nums} == {
        (12.4, "%"), (1240.0, "kWh"),
    }


def test_grounded_claim_passes():
    wit = [{"value": 12.4, "unit": "%"}]
    assert ground_claims("Losses fell to 12.4%.", wit) == []


def test_invented_number_is_flagged():
    wit = [{"value": 12.4, "unit": "%"}]
    bad = ground_claims("Losses fell to 12.4% saving ₹7.7Cr.", wit)
    assert len(bad) == 1 and bad[0]["unit"] == "INR"


def test_unit_blind_grounding_is_refused():
    # The incident case: 12.4 MW must NOT ground against a witnessed 12.4%.
    wit = [{"value": 12.4, "unit": "%"}]
    bad = ground_claims("Peak demand hit 12.4 MW.", wit)
    assert len(bad) == 1


def test_empty_witness_set_flags_everything():
    assert len(ground_claims("Revenue rose ₹5L.", [])) == 1


def test_tolerance_is_relative():
    wit = [{"value": 1000.0, "unit": "kWh"}]
    assert ground_claims("used 1,004 kWh", wit, rel_tol=0.005) == []
    assert len(ground_claims("used 1,010 kWh", wit, rel_tol=0.005)) == 1


def test_bare_years_are_not_claims():
    assert extract_numbers("in 2026 the plan holds") == []


def test_claim_check_selfcheck():
    assert selfcheck()


# ── golden gate ─────────────────────────────────────────────────────────────

def test_golden_roundtrip(tmp_path, monkeypatch):
    g = GoldenGate(tmp_path / "g.json")
    monkeypatch.setenv("GOLDEN_UPDATE", "1")
    monkeypatch.setenv("GOLDEN_REASON", "initial baseline")
    g.check({"a": {"loss_pct": 12.41}, "n": 3})
    monkeypatch.delenv("GOLDEN_UPDATE")

    g.check({"a": {"loss_pct": 12.411}, "n": 3})  # inside 0.1% tolerance

    with pytest.raises(GoldenError, match="outside the declared tolerance"):
        g.check({"a": {"loss_pct": 13.0}, "n": 3})


def test_golden_missing_and_new_keys_fail(tmp_path, monkeypatch):
    g = GoldenGate(tmp_path / "g.json")
    monkeypatch.setenv("GOLDEN_UPDATE", "1")
    monkeypatch.setenv("GOLDEN_REASON", "baseline")
    g.check({"a": 1.0})
    monkeypatch.delenv("GOLDEN_UPDATE")

    with pytest.raises(GoldenError, match="missing from computed"):
        g.check({})
    with pytest.raises(GoldenError, match="NEW key"):
        g.check({"a": 1.0, "b": 2.0})


def test_rebaseline_without_reason_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLDEN_UPDATE", "1")
    monkeypatch.delenv("GOLDEN_REASON", raising=False)
    with pytest.raises(GoldenError, match="GOLDEN_REASON"):
        GoldenGate(tmp_path / "g.json").check({"a": 1.0})


def test_missing_golden_file_is_an_error_not_a_pass(tmp_path):
    with pytest.raises(GoldenError, match="no golden file"):
        GoldenGate(tmp_path / "never_recorded.json").check({"a": 1.0})
