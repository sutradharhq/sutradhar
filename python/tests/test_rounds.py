"""Tests for the flight recorder.

The load-bearing tests here are the ones about REFUSAL: that the stop rule
will not say "rest" while HIGH findings are landing, and that attribution
will not name deletion candidates on thin data. A reporter that always
produces a confident answer is worse than no reporter, because doctrine 8.1
would then delete rules on the strength of a quiet week.
"""
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.rounds import (
    MIN_ROUNDS_FOR_ATTRIBUTION,
    RoundError,
    doctrine_rule_ids,
    load_rounds,
    parse_round,
    report,
    residual_register,
    rule_attribution,
    sample_floors,
    selfcheck,
    stop_rule,
)

HEAD = "| id | severity | rule | found-by | status | summary |\n|---|---|---|---|---|---|\n"


def _round(n, rows="", date=None):
    return f"# Round {n} - {date or f'2026-01-{n:02d}'}\n\nLenses: scale\n\n{HEAD}{rows}"


def _plant(d, n, rows="", date=None):
    (d / f"round-{n:03d}.md").write_text(_round(n, rows, date))


# ── parsing ─────────────────────────────────────────────────────────────────

def test_parses_heading_lenses_and_findings():
    r = parse_round(_round(7, "| R7-1 | high | 2.7 | swallow-lint | fixed | swallowed read |\n"))
    assert r.number == 7 and r.date == "2026-01-07"
    assert r.lenses == ["scale"]
    assert len(r.findings) == 1
    f = r.findings[0]
    assert (f.id, f.severity, f.rule, f.status) == ("R7-1", "high", "2.7", "fixed")


def test_an_em_dash_heading_is_accepted():
    assert parse_round(f"# Round 3 — 2026-02-02\n\n{HEAD}").number == 3


def test_a_dash_rule_means_no_rule_cited():
    r = parse_round(_round(1, "| R1-1 | low | - | ad hoc | fixed | thing |\n"))
    assert r.findings[0].rule == ""


def test_an_empty_table_is_a_valid_round():
    """'We looked and found nothing' must be recordable, and must be
    distinguishable from 'nobody wrote it down'."""
    r = parse_round(_round(4))
    assert r.findings == [] and r.number == 4


@pytest.mark.parametrize("text,why", [
    ("Lenses: x\n\n" + HEAD, "no heading"),
    ("# Round 9 - 2026-01-01\n\njust prose\n", "no findings table"),
    (_round(9, "| R9-1 | critical | 2.7 | x | fixed | y |\n"), "bad severity"),
    (_round(9, "| R9-1 | high | 2.7 | x | pending | y |\n"), "bad status"),
    (_round(9, "| R9-1 | high | 2.7 |\n"), "wrong cell count"),
    (_round(9, "| R9-1 | high | 2.7 | x | fixed | a |\n| R9-1 | low | 2.7 | x | fixed | b |\n"),
     "duplicate id within the round"),
])
def test_malformed_records_are_refused(text, why):
    with pytest.raises(RoundError):
        parse_round(text, source="<test>")


def test_duplicate_round_numbers_are_refused(tmp_path):
    _plant(tmp_path, 1)
    (tmp_path / "also-one.md").write_text(_round(1))
    with pytest.raises(RoundError, match="more than once"):
        load_rounds(tmp_path)


def test_table_parser_never_half_reads_a_record():
    """Property (doctrine 1.3): for any input, parse_round returns a Round
    whose findings are all well-formed, or raises RoundError. Never a
    partially-populated register."""
    rng = random.Random(20260808)
    fragments = ["| a | b | c |\n", "|---|\n", HEAD, "# Round 2 - 2026-01-01\n",
                 "| R1 | high | 2.7 | x | fixed | s |\n", "\n", "text\n", "|\n", "||\n"]
    for _ in range(2000):
        text = "".join(rng.choice(fragments) for _ in range(rng.randint(0, 8)))
        try:
            r = parse_round(text)
        except RoundError:
            continue
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"parser raised {type(exc).__name__} on {text!r}")
        for f in r.findings:
            assert f.severity in ("high", "med", "low")
            assert f.status in ("fixed", "deferred", "closed")


# ── the stop rule (8.3) ─────────────────────────────────────────────────────

def test_stop_rule_needs_two_rounds(tmp_path):
    _plant(tmp_path, 1)
    assert stop_rule(load_rounds(tmp_path))[0] == "INSUFFICIENT"


def test_stop_rule_continues_while_high_findings_land(tmp_path):
    _plant(tmp_path, 1)
    _plant(tmp_path, 2, "| R2-1 | high | 2.7 | x | fixed | y |\n")
    assert stop_rule(load_rounds(tmp_path))[0] == "CONTINUE"


def test_stop_rule_rests_after_two_clean_rounds(tmp_path):
    _plant(tmp_path, 1, "| R1-1 | high | 2.7 | x | fixed | y |\n")
    _plant(tmp_path, 2, "| R2-1 | low | 3.5 | x | fixed | y |\n")
    _plant(tmp_path, 3)
    verdict, why = stop_rule(load_rounds(tmp_path))
    assert verdict == "REST" and "converged" in why


def test_a_closed_row_does_not_count_as_a_new_finding(tmp_path):
    """Bookkeeping that closes an old deferral must not read as fresh
    trouble, or the stop rule never rests."""
    _plant(tmp_path, 1, "| R1-1 | high | 2.7 | x | deferred | y |\n")
    _plant(tmp_path, 2, "| R1-1 | high | 2.7 | x | closed | y |\n")
    _plant(tmp_path, 3)
    assert stop_rule(load_rounds(tmp_path))[0] == "REST"


# ── the residual register ───────────────────────────────────────────────────

def test_a_deferral_stays_open_until_closed(tmp_path):
    _plant(tmp_path, 1, "| R1-1 | med | 2.6 | x | deferred | uncapped sweep |\n")
    _plant(tmp_path, 2)
    assert [f.id for f in residual_register(load_rounds(tmp_path))] == ["R1-1"]
    _plant(tmp_path, 3, "| R1-1 | med | 2.6 | x | closed | cap shipped |\n")
    assert residual_register(load_rounds(tmp_path)) == []


def test_a_deferral_closed_by_a_later_fix_also_clears(tmp_path):
    _plant(tmp_path, 1, "| R1-1 | med | 2.6 | x | deferred | y |\n")
    _plant(tmp_path, 2, "| R1-1 | med | 2.6 | x | fixed | y |\n")
    assert residual_register(load_rounds(tmp_path)) == []


# ── attribution (8.1) ───────────────────────────────────────────────────────

def test_attribution_counts_saves_and_finds_uncited_rules(tmp_path):
    _plant(tmp_path, 1, "| R1-1 | high | 2.7 | x | fixed | y |\n"
                        "| R1-2 | low | 2.7 | x | fixed | z |\n")
    a = rule_attribution(load_rounds(tmp_path), {"2.7", "5.2"})
    assert a["saves"] == {"2.7": 2}
    assert a["never_cited"] == ["5.2"]


def test_a_relisted_deferral_is_attributed_once(tmp_path):
    """Round 2 re-listing round 1's open deferral is bookkeeping, not a save.
    Counting it twice would make a rule look better the longer its finding
    stays unfixed - and did, in this repo's own rounds 1 and 2."""
    row = "| R1-1 | med | 2.6 | scale | deferred | uncapped sweep |\n"
    _plant(tmp_path, 1, row)
    _plant(tmp_path, 2, row)
    assert rule_attribution(load_rounds(tmp_path), {"2.6"})["saves"] == {"2.6": 1}


def test_a_mistyped_rule_id_is_surfaced(tmp_path):
    _plant(tmp_path, 1, "| R1-1 | high | 27 | x | fixed | y |\n")
    a = rule_attribution(load_rounds(tmp_path), {"2.7"})
    assert a["unknown_rules"] == ["27"]


def test_attribution_refuses_deletion_candidates_on_thin_data(tmp_path):
    for n in range(1, MIN_ROUNDS_FOR_ATTRIBUTION):
        _plant(tmp_path, n)
    text = report(load_rounds(tmp_path), {"9.9"})
    assert "NOT REPORTED" in text and "9.9" not in text


def test_the_refusal_lifts_at_the_threshold(tmp_path):
    """A refusal that never lifts is as useless as one that never fires.
    Needs both floors cleared: enough rounds AND months of span."""
    for n in range(1, MIN_ROUNDS_FOR_ATTRIBUTION + 1):
        _plant(tmp_path, n, date=f"2026-0{n}-01")
    text = report(load_rounds(tmp_path), {"9.9"})
    assert "NOT REPORTED" not in text and "9.9" in text


def test_deletion_candidates_need_a_time_span_not_just_rounds(tmp_path):
    """Six rounds in nine days cleared the round floor and named 25 deletion
    candidates while 8.1's own condition - months of silence - had not begun
    to run. A burst of rounds is a busy week, not a silent rule."""
    for n in range(1, MIN_ROUNDS_FOR_ATTRIBUTION + 2):
        _plant(tmp_path, n, date=f"2026-06-{n:02d}")
    text = report(load_rounds(tmp_path), {"9.9"})
    assert "NOT REPORTED" in text and "9.9" not in text


def test_a_retracted_finding_loses_its_save_and_leaves_the_register(tmp_path):
    """closed resolves a finding whose save stands; retracted marks the
    finding itself as wrong, so the save goes with it. Round 6 could only
    ask readers to mentally discount a retracted finding's save."""
    _plant(tmp_path, 1, "| R1-1 | med | 2.6 | audit | deferred | wrong count |\n")
    _plant(tmp_path, 2, "| R1-1 | med | 2.6 | - | retracted | auditor's bug |\n")
    rounds = load_rounds(tmp_path)
    assert rule_attribution(rounds, {"2.6"})["saves"] == {}
    assert residual_register(rounds) == []
    assert rounds[1].count("med") == 0  # bookkeeping, not a new finding


def test_doctrine_ids_parse_from_the_real_doctrine():
    ids = doctrine_rule_ids(Path(__file__).resolve().parents[2] / "DOCTRINE.md")
    assert {"1.1", "2.2", "6.3", "8.1"} <= ids and len(ids) > 30


# ── the measured half ───────────────────────────────────────────────────────

def test_floors_are_sampled_from_baseline_files(tmp_path):
    (tmp_path / "swallow_baseline.json").write_text('{"a.py": 3, "b.py": 2}')
    (tmp_path / "ratchet_baseline.json").write_text('["one", "two"]')
    floors = sample_floors(tmp_path)
    assert floors["swallow_baseline.json"] == 5
    assert floors["ratchet_baseline.json"] == 2


def test_report_labels_recorded_and_measured_separately(tmp_path):
    """Doctrine 5.1: a logbook and a measurement may not read the same."""
    _plant(tmp_path, 1, "| R1-1 | high | 2.7 | x | fixed | y |\n")
    text = report(load_rounds(tmp_path), {"2.7"}, floors={"b.json": 4})
    assert "[RECORDED" in text and "[MEASURED" in text


# ── CLI ─────────────────────────────────────────────────────────────────────

def test_cli_check_rejects_an_unknown_rule_id(tmp_path, capsys):
    import sutradhar_guards.rounds as rd
    doctrine = tmp_path / "D.md"
    doctrine.write_text("**2.7 A rule.** text\n")
    rounds = tmp_path / "r"; rounds.mkdir()
    _plant(rounds, 1, "| R1-1 | high | 9.9 | x | fixed | y |\n")
    assert rd.main([str(rounds), "--doctrine", str(doctrine), "--check"]) == 1
    assert "9.9" in capsys.readouterr().out


def test_cli_check_passes_on_valid_records(tmp_path):
    import sutradhar_guards.rounds as rd
    doctrine = tmp_path / "D.md"
    doctrine.write_text("**2.7 A rule.** text\n")
    rounds = tmp_path / "r"; rounds.mkdir()
    _plant(rounds, 1, "| R1-1 | high | 2.7 | x | fixed | y |\n")
    assert rd.main([str(rounds), "--doctrine", str(doctrine), "--check"]) == 0


def test_cli_reports_no_records_as_two_not_zero(tmp_path):
    """No data is not a pass. Exit 2, never 0."""
    import sutradhar_guards.rounds as rd
    assert rd.main([str(tmp_path / "nope")]) == 2


def test_the_repos_own_round_record_is_valid():
    import sutradhar_guards.rounds as rd
    root = Path(__file__).resolve().parents[2]
    assert rd.main([str(root / "docs" / "rounds"),
                    "--doctrine", str(root / "DOCTRINE.md"), "--check"]) == 0


# ── selfcheck + mutation ────────────────────────────────────────────────────

def test_selfcheck_passes():
    assert selfcheck()


def test_a_stop_rule_that_always_rests_fails_the_selfcheck(monkeypatch):
    import sutradhar_guards.rounds as rd
    monkeypatch.setattr(rd, "stop_rule", lambda rounds: ("REST", "always"))
    assert not rd.selfcheck()


def test_a_register_that_never_releases_fails_the_selfcheck(monkeypatch):
    import sutradhar_guards.rounds as rd
    real = rd.residual_register
    monkeypatch.setattr(rd, "residual_register",
                        lambda rounds: real(rounds) or [object()])
    assert not rd.selfcheck()


def test_a_reporter_that_never_refuses_fails_the_selfcheck(monkeypatch):
    """The thin-data refusal is the whole reason this tool can be trusted
    with 8.1. Blinding it must go red."""
    import sutradhar_guards.rounds as rd
    monkeypatch.setattr(rd, "MIN_ROUNDS_FOR_ATTRIBUTION", 0)
    assert not rd.selfcheck()
