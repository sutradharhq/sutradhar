# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Tests for the backflow register (R7-1).

R7-1 sat deferred for six rounds because recording an owed item cost nothing.
The register only closes it if an undecided item eventually FAILS something -
so the load-bearing tests here are the ones that prove the gate bites, and
that each of the three ways out is a decision rather than a way to stay quiet.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.rounds import (  # noqa: E402
    BACKFLOW_COLUMNS,
    RoundError,
    backflow_problems,
    main,
    parse_backflow,
)

HEADER = (
    "## The register\n\n"
    "| " + " | ".join(BACKFLOW_COLUMNS) + " |\n"
    "|" + "|".join(["---"] * len(BACKFLOW_COLUMNS)) + "|\n"
)


def reg(*rows: str) -> str:
    return HEADER + "".join(r if r.endswith("\n") else r + "\n" for r in rows)


def row(id="B-1", source="Thread-A", what="a thing", evidence="scar",
        rule="2.1", status="owed", by_round="14", note="") -> str:
    return f"| {id} | {source} | {what} | {evidence} | {rule} | {status} | {by_round} | {note} |"


# ── the mechanism: an undecided item eventually costs something ──────────────

def test_an_owed_item_past_its_round_fails():
    """The whole point. Before this, an owed item cost nothing and so it sat."""
    items = parse_backflow(reg(row(status="owed", by_round="14")))
    assert backflow_problems(items, latest_round=13, all_rules={"2.1"}) == []
    problems = backflow_problems(items, latest_round=14, all_rules={"2.1"})
    assert len(problems) == 1 and "B-1" in problems[0]


def test_a_deferred_item_past_its_round_fails_too():
    """Otherwise `deferred` is just `owed` wearing a hat."""
    items = parse_backflow(reg(row(status="deferred", by_round="14", note="waiting on X")))
    assert backflow_problems(items, latest_round=15, all_rules={"2.1"})


def test_re_deferring_to_a_later_round_with_a_reason_is_a_way_out():
    items = parse_backflow(reg(row(status="deferred", by_round="20", note="blocked on B-7")))
    assert backflow_problems(items, latest_round=15, all_rules={"2.1"}) == []


def test_deferring_without_a_reason_is_not():
    """7.4: an unrecorded dead end gets re-explored at full price."""
    items = parse_backflow(reg(row(status="deferred", by_round="20", note="")))
    problems = backflow_problems(items, latest_round=15, all_rules={"2.1"})
    assert any("no reason" in p for p in problems)


def test_rejecting_without_a_reason_is_not_either():
    items = parse_backflow(reg(row(status="rejected", by_round="20", note="-")))
    assert any("no reason" in p for p in backflow_problems(items, 15, {"2.1"}))


def test_an_adopted_item_must_land_somewhere_real():
    """An adoption citing no rule, or a rule that does not exist, is a claim
    with nothing behind it - the shape 8.1's attribution counts depend on."""
    nowhere = parse_backflow(reg(row(status="adopted", rule="-")))
    assert any("cites no doctrine rule" in p for p in backflow_problems(nowhere, 13, {"2.1"}))
    ghost = parse_backflow(reg(row(status="adopted", rule="9.9")))
    assert any("not in the doctrine" in p for p in backflow_problems(ghost, 13, {"2.1"}))
    real = parse_backflow(reg(row(status="adopted", rule="2.1")))
    assert backflow_problems(real, 13, {"2.1"}) == []


# ── 8.1: an intention is not an incident ─────────────────────────────────────

def test_a_practice_item_cannot_found_a_new_rule():
    """The guard against a survey of well-run repos inflating the doctrine
    with things nobody has paid for. Charters, protocols and ADRs document
    what a team MEANT to do; 8.1 wants what something COST them."""
    items = parse_backflow(reg(row(evidence="practice", rule="new")))
    problems = backflow_problems(items, 13, {"2.1"})
    assert any("8.1" in p and "practice" in p for p in problems)


def test_a_practice_item_may_strengthen_an_existing_rule():
    items = parse_backflow(reg(row(evidence="practice", rule="7.4")))
    assert backflow_problems(items, 13, {"2.1", "7.4"}) == []


def test_a_scar_item_may_propose_a_new_rule():
    items = parse_backflow(reg(row(evidence="scar", rule="new")))
    assert backflow_problems(items, 13, {"2.1"}) == []


# ── the parser refuses rather than skipping (2.9, in the instrument) ─────────

def test_a_malformed_row_is_refused_not_skipped():
    """Found the first time this register was written for real: a note
    containing a pipe split the row into nine cells, an earlier parser skipped
    any row that was not eight, and the item vanished under a printed OK.
    'Cannot read this row' must not be spelled the same as 'no row here'."""
    bad = reg(row(note="either a | or the other"))
    with pytest.raises(RoundError, match="9 cell"):
        parse_backflow(bad)


def test_prose_tables_above_the_heading_are_not_read_as_entries():
    doc = "| column | meaning |\n|---|---|\n| id | a thing |\n\n" + reg(row())
    assert [i.id for i in parse_backflow(doc)] == ["B-1"]


def test_a_register_with_no_heading_is_refused():
    with pytest.raises(RoundError, match="heading"):
        parse_backflow("| B-1 | a | b | scar | 2.1 | owed | 14 | |")


@pytest.mark.parametrize(
    "bad,match",
    [
        (row(status="pending"), "not one of"),
        (row(evidence="vibes"), "not one of"),
        (row(by_round="soon"), "not a round number"),
        (row(id="7"), "form B-"),
    ],
)
def test_unreadable_fields_are_refused(bad, match):
    with pytest.raises(RoundError, match=match):
        parse_backflow(reg(bad))


def test_a_duplicate_id_is_refused():
    with pytest.raises(RoundError, match="twice"):
        parse_backflow(reg(row(id="B-1"), row(id="B-1", what="something else")))


# ── the CLI: absence is not a pass ───────────────────────────────────────────

def _rounds_dir(tmp_path: Path) -> Path:
    d = tmp_path / "rounds"
    d.mkdir()
    for n in (1, 2):
        (d / f"round-00{n}.md").write_text(
            f"# Round {n} - 2026-0{n}-01\n\nLenses: x\n\n"
            "| id | severity | rule | found-by | status | summary |\n"
            "|---|---|---|---|---|---|\n"
            f"| R{n}-1 | low | 2.1 | test | fixed | a thing |\n"
        )
    return d


def test_a_missing_register_exits_two_not_zero(tmp_path, capsys):
    """2.9. A register that is not there has told us nothing about what is
    owed - which is the same silence the gate exists to break."""
    rc = main([str(_rounds_dir(tmp_path)), "--backflow",
               str(tmp_path / "nope.md"), "--doctrine", "DOCTRINE.md"])
    assert rc == 2
    assert "nothing was checked" in capsys.readouterr().out


def test_an_empty_register_exits_two_not_zero(tmp_path, capsys):
    empty = tmp_path / "bf.md"
    empty.write_text(HEADER)
    rc = main([str(_rounds_dir(tmp_path)), "--backflow", str(empty),
               "--doctrine", "DOCTRINE.md"])
    assert rc == 2
    assert "refusal rather than a pass" in capsys.readouterr().out


def test_the_cli_fails_on_an_overdue_item(tmp_path, capsys):
    bf = tmp_path / "bf.md"
    bf.write_text(reg(row(status="owed", by_round="1")))
    rc = main([str(_rounds_dir(tmp_path)), "--backflow", str(bf),
               "--doctrine", "DOCTRINE.md"])
    assert rc == 1
    assert "need a decision" in capsys.readouterr().out


# ── the shipped register itself ──────────────────────────────────────────────

def test_this_repos_register_is_valid_and_current():
    root = Path(__file__).resolve().parents[2]
    items = parse_backflow((root / "docs" / "backflow.md").read_text(), "docs/backflow.md")
    assert len(items) >= 19
    assert any(i.status == "adopted" for i in items), (
        "a register with nothing adopted has not yet shown the mechanism works"
    )


def test_ci_runs_the_backflow_gate():
    """R7-1 recurs the moment nothing runs this."""
    root = Path(__file__).resolve().parents[2]
    ci = (root / ".github" / "workflows" / "selftest.yml").read_text()
    assert "--backflow" in ci, "CI no longer checks the backflow register"
