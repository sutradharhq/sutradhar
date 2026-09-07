# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Tests for the framework-shape gate (R19-1).

The load-bearing cases here are the DIRECTIONS and the EXEMPTIONS. A gate
that flagged everything would be removed within a week, and a gate that
flagged nothing would pass this repository vacuously - so every case below
has both halves: a domain unit is caught AND an engineering unit is not; a
literal in `docs/` is caught AND the same literal in `docs/rounds/` is not.

**Nothing in this file writes a domain literal or a currency symbol
directly.** They are built from the module's own lists, which does two
things at once: this file stays clean under the gate it tests (it is inside
the framework surface), and every declared unit is exercised rather than one
hand-picked favourite.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards import framework_shape as fs  # noqa: E402
from sutradhar_guards.framework_shape import (  # noqa: E402
    _CURRENCY_SYMBOLS,
    _DOMAIN_UNITS,
    _ENGINEERING_UNITS,
    ShapeError,
    against_report,
    compare,
    load_baseline,
    main,
    scan_diff,
    scan_surface,
    scan_text,
    selfcheck,
    surface_files,
)

REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / "framework_shape_baseline.json"

# Built, never written out. `A_DOMAIN_UNIT` is whichever unit sorts first,
# so the fixtures follow the list rather than a memory of it.
A_DOMAIN_UNIT = sorted(_DOMAIN_UNITS)[0]
A_DOMAIN_LITERAL = "1,240 {}".format(A_DOMAIN_UNIT)
AN_ENGINEERING_LITERAL = "1,240 {}".format(sorted(_ENGINEERING_UNITS)[0])


def test_selfcheck_passes():
    assert selfcheck() is True


# ── the two directions ───────────────────────────────────────────────────────

@pytest.mark.parametrize("unit", sorted(_DOMAIN_UNITS))
def test_every_declared_domain_unit_is_caught(unit):
    """A class ratchet over the list itself (2.1): a unit added to
    `_DOMAIN_UNITS` is covered the day it lands, and a typo in the list
    fails here rather than by letting a leak through."""
    found = scan_text("peak was 1,240 {} last week".format(unit), "a.md")
    assert len(found) == 1, unit
    assert found[0].text == "1,240 {}".format(unit)
    assert _DOMAIN_UNITS[unit] in found[0].why


@pytest.mark.parametrize("unit", sorted(_ENGINEERING_UNITS))
def test_no_declared_engineering_unit_is_caught(unit):
    """The half that keeps the guard installed. `500 ms` is this framework
    talking about itself, and a gate that flagged it would be muted."""
    assert scan_text("the sweep took 500 {}".format(unit), "a.md") == []


def test_the_two_lists_do_not_overlap():
    """A unit in both lists makes the gate contradict itself, and the
    contradiction would be invisible in either direction alone."""
    assert not (set(_ENGINEERING_UNITS) & set(_DOMAIN_UNITS))


@pytest.mark.parametrize("symbol", _CURRENCY_SYMBOLS)
def test_every_declared_currency_symbol_is_caught(symbol):
    found = scan_text("revenue rose {}4,200".format(symbol), "a.md")
    assert [f.text for f in found] == [symbol]


def test_a_dollar_amount_is_caught_and_a_shell_positional_is_not():
    """Measured before the rule was written: `$` alone matches 427 times in
    this surface and nearly every one is shell. The two-character floor is
    what separates an amount from `$1`..`$9`, and both halves are asserted
    because excluding one bad outcome is not the same as asserting a
    contract (3.7)."""
    assert scan_text("total ${} due".format("1,240"), "a.md")
    assert scan_text("price ${} each".format("12.50"), "a.md")
    assert scan_text('printf "%s" "$1" && exit $?', "run.sh") == []
    assert scan_text("cd $HOME && echo $0 $9", "run.sh") == []


@pytest.mark.parametrize("text", [
    "coverage improved to 84.5% this round",
    "python3.9 and v0.3.0 still parse",
    "Round 18 - 2026-09-07",
    "R18-5 and R16-1 both landed",
    "200,000 rows and 1,400 point pins",
])
def test_the_shapes_this_repository_is_full_of_stay_quiet(text):
    assert scan_text(text, "a.md") == []


# ── keys are identities, not positions (R18-1) ───────────────────────────────

def test_a_key_survives_lines_inserted_above_it():
    flat = scan_text(A_DOMAIN_LITERAL + "\n", "a.md")
    shifted = scan_text("# pushed down\n" * 7 + A_DOMAIN_LITERAL + "\n", "a.md")
    assert flat and shifted
    assert shifted[0].line != flat[0].line, (
        "the fixture did not move; this case would pass whatever the keys did"
    )
    assert {f.key for f in shifted} == {f.key for f in flat}


def test_the_line_still_reaches_the_reader():
    found = scan_text("\n\n" + A_DOMAIN_LITERAL + "\n", "a.md")
    assert found[0].line == 3
    assert ":3:" in found[0].message


def test_the_same_term_twice_in_one_file_is_one_finding():
    """The identity is 'this file uses this term'. A second legitimate rupee
    example in a file already banked for rupee parsing is not a new leak,
    and a gate that called it one would be switched off by noise (B-2)."""
    found = scan_text("{lit}\nnoise\n{lit}\n".format(lit=A_DOMAIN_LITERAL),
                      "a.md")
    assert len(found) == 1 and found[0].line == 1


# ── the baseline: a row without a reason is not a decision ───────────────────

def test_a_well_formed_baseline_loads(tmp_path):
    p = tmp_path / "b.json"
    p.write_text(json.dumps({"a.md::x": "the guard's own example"}))
    assert load_baseline(p) == {"a.md::x": "the guard's own example"}


def test_a_missing_baseline_is_empty_not_an_error(tmp_path):
    assert load_baseline(tmp_path / "absent.json") == {}


@pytest.mark.parametrize("body", [
    {"a.md::x": ""},
    {"a.md::x": "   "},
    {"a.md::x": None},
    {"a.md::x": 1},
    ["a.md::x"],
])
def test_a_baseline_row_with_no_reason_is_refused(tmp_path, body):
    """The whole difference between a ratchet and an ignore-list. A row that
    cannot say why it is there has not been decided, and undecided must not
    read the same as allowed (2.9)."""
    p = tmp_path / "b.json"
    p.write_text(json.dumps(body))
    with pytest.raises(ShapeError):
        load_baseline(p)


def test_an_unreadable_baseline_is_refused_not_treated_as_empty(tmp_path):
    p = tmp_path / "b.json"
    p.write_text("{not json")
    with pytest.raises(ShapeError):
        load_baseline(p)


def test_compare_reports_new_and_stale():
    found = scan_text(A_DOMAIN_LITERAL, "a.md")
    assert compare(found, {found[0].key: "banked"}) == ([], [])
    new, stale = compare(found, {})
    assert [f.key for f in new] == [found[0].key] and stale == []
    new, stale = compare([], {"a.md::gone": "banked"})
    assert new == [] and stale == ["a.md::gone"]


# ── the surface, and the exemption that is the point ─────────────────────────

def _tree(root: Path) -> None:
    (root / "docs" / "rounds").mkdir(parents=True)
    (root / "docs" / "guide.md").write_text("clean\n")
    (root / "docs" / "rounds" / "round-001.md").write_text("clean\n")
    (root / "CHANGELOG.md").write_text("clean\n")
    (root / "README.md").write_text("clean\n")
    (root / "agent").mkdir()
    (root / "agent" / "AGENTS.md").write_text("clean\n")


def test_the_surface_reads_what_ships_and_teaches(tmp_path):
    _tree(tmp_path)
    rels = {"/".join(p.relative_to(tmp_path).parts)
            for p in surface_files(tmp_path)}
    assert {"README.md", "docs/guide.md"} <= rels


def test_a_round_record_may_name_the_term_it_removed(tmp_path):
    """The exemption, asserted as behaviour rather than trusted as config.
    Round 18's record says `meter` came back at 3,688 occurrences; a gate
    that refused that sentence teaches people to describe incidents vaguely,
    which is the opposite of what a record is for."""
    _tree(tmp_path)
    (tmp_path / "docs" / "rounds" / "round-019.md").write_text(
        "the example app said {} and it is gone\n".format(A_DOMAIN_LITERAL))
    found, paths = scan_surface(tmp_path)
    assert found == [], [f.message for f in found]

    # ... and the SAME string one directory up is caught. Without this half
    # the case above proves only that the scan found nothing anywhere.
    (tmp_path / "docs" / "guide.md").write_text(
        "the fleet drew {}\n".format(A_DOMAIN_LITERAL))
    found, paths = scan_surface(tmp_path)
    assert [f.key for f in found] == ["docs/guide.md::" + A_DOMAIN_LITERAL]


def test_the_changelog_is_exempt_too(tmp_path):
    _tree(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(
        "- removed the {} example\n".format(A_DOMAIN_LITERAL))
    found, _ = scan_surface(tmp_path)
    assert found == []


def test_a_path_outside_the_declared_surface_is_not_scanned(tmp_path):
    """Honest scope. `agent/` is not in the surface today, and a test that
    pretended otherwise would report a reach the gate does not have."""
    _tree(tmp_path)
    (tmp_path / "agent" / "AGENTS.md").write_text(A_DOMAIN_LITERAL + "\n")
    found, _ = scan_surface(tmp_path)
    assert found == []


# ── this repository, through the real seam ───────────────────────────────────

def test_this_repository_passes_its_own_gate():
    assert main([str(REPO), "--baseline", str(BASELINE)]) == 0


def test_every_banked_entry_carries_a_reason_and_is_still_found():
    """Guards the shipped baseline from both sides: no row may be a bare
    allow, and no row may linger after the thing it banks has gone."""
    baseline = load_baseline(BASELINE)
    assert baseline, "an empty baseline would make the gate above vacuous"
    found, _ = scan_surface(REPO)
    new, stale = compare(found, baseline)
    assert not new, [f.message for f in new]
    assert not stale, stale


def test_a_planted_literal_in_this_repository_fails_the_gate(tmp_path, capsys):
    """The mutation, run as a test rather than left to a round record: plant
    the round-18 leak back into a surface file and require the gate to go red
    and NAME it."""
    plant = REPO / "docs" / "adoption.md"
    original = plant.read_text(encoding="utf-8")
    try:
        plant.write_text(original + "\nthe fleet drew {}.\n".format(
            A_DOMAIN_LITERAL), encoding="utf-8")
        assert main([str(REPO), "--baseline", str(BASELINE)]) == 1
        out = capsys.readouterr().out
        assert "docs/adoption.md" in out and A_DOMAIN_LITERAL in out
    finally:
        plant.write_text(original, encoding="utf-8")


# ── the CLI partition ────────────────────────────────────────────────────────

def test_an_unknown_flag_exits_two(capsys):
    assert main(["--not-a-flag"]) == 2


def test_a_missing_repository_exits_two_not_zero(tmp_path, capsys):
    """2.9: asked about a tree that is not there, "I did not check" and
    "nothing was wrong" must be different answers."""
    assert main([str(tmp_path / "nope")]) == 2
    assert "not a pass" in capsys.readouterr().err


def test_a_flag_with_no_value_exits_two_rather_than_crashing(capsys):
    """6.11: a stack trace is the absence of a verdict, not a verdict."""
    assert main([".", "--baseline"]) == 2
    assert "bad argument" in capsys.readouterr().err


def test_a_reasonless_baseline_makes_the_gate_refuse_not_pass(tmp_path, capsys):
    bad = tmp_path / "b.json"
    bad.write_text(json.dumps({"a.md::x": ""}))
    assert main([str(REPO), "--baseline", str(bad)]) == 2
    assert "no reason" in capsys.readouterr().err


def test_a_surface_that_does_not_exist_is_refused(tmp_path, capsys):
    """An empty surface reporting OK is the empty-200 lie (6.6)."""
    (tmp_path / "nothing-here").mkdir()
    assert main([str(tmp_path)]) == 2
    assert "not a pass" in capsys.readouterr().err


def test_a_blinded_detector_fails_the_cli(monkeypatch):
    """The selfcheck-wiring case the whole suite is built on: a detector
    edited into vacuity passes every real file forever, so the CLI must go
    red on a tree it had just called clean."""
    assert main([str(REPO), "--baseline", str(BASELINE)]) == 0
    monkeypatch.setattr(fs, "scan_text", lambda *a, **k: [])
    assert main([str(REPO), "--baseline", str(BASELINE)]) == 1


# ── check 3: added lines only ────────────────────────────────────────────────

def _git(repo: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=T",
         "-c", "user.email=t@example.com", *args],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, (args, proc.stderr)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _tree(r)
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "seed")
    return r


def test_a_diff_gates_what_is_entering(repo: Path, capsys):
    (repo / "docs" / "guide.md").write_text(
        "the fleet drew {}\n".format(A_DOMAIN_LITERAL))
    _git(repo, "add", "docs/guide.md")
    found, lines = scan_diff(repo, "HEAD")
    assert [f.key for f in found] == ["docs/guide.md::" + A_DOMAIN_LITERAL]
    assert lines, "the diff was empty; this case would pass vacuously"
    assert main([str(repo), "--diff", "HEAD"]) == 1


def test_a_diff_ignores_an_added_line_in_a_round_record(repo: Path):
    (repo / "docs" / "rounds" / "round-019.md").write_text(
        "we removed {} from the example\n".format(A_DOMAIN_LITERAL))
    _git(repo, "add", "docs/rounds/round-019.md")
    found, lines = scan_diff(repo, "HEAD")
    assert lines, "the diff was empty; this case would pass vacuously"
    assert found == [], [f.message for f in found]
    assert main([str(repo), "--diff", "HEAD"]) == 0


def test_a_diff_does_not_re_litigate_what_is_already_banked(repo: Path):
    """The reason this mode exists: an untouched banked entry is not a new
    finding, and a diff that re-reported it would be the noise that gets a
    commit gate uninstalled."""
    (repo / "docs" / "guide.md").write_text(
        "the fleet drew {}\n".format(A_DOMAIN_LITERAL))
    _git(repo, "add", "docs/guide.md")
    baseline = repo / "framework_shape_baseline.json"
    baseline.write_text(json.dumps(
        {"docs/guide.md::" + A_DOMAIN_LITERAL: "the worked example needs it"}))
    assert main([str(repo), "--diff", "HEAD"]) == 0


def test_a_diff_against_a_ref_that_does_not_exist_exits_two(repo: Path, capsys):
    assert main([str(repo), "--diff", "no-such-ref"]) == 2
    assert "could not run" in capsys.readouterr().err


# ── check 2: the corpus-relative report ──────────────────────────────────────

def test_the_corpus_report_ranks_a_central_term_that_is_present_here(tmp_path):
    """Calibration, not a gate. The term must be central in the corpus AND
    present in the surface to appear at all - that pairing IS the method
    R18-5 records."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.py").write_text("widgetron\n" * 30 + "solitary\n" * 30)
    repo_root = tmp_path / "repo"
    _tree(repo_root)
    (repo_root / "docs" / "guide.md").write_text("widgetron appears here\n")

    rows, corpus_files, surface_count = against_report(
        repo_root, corpus, top=10, min_count=5)
    terms = [t for t, _, _ in rows]
    assert "widgetron" in terms, rows
    assert "solitary" not in terms, (
        "a term absent from the surface was reported; the report would be a "
        "list of the corpus rather than of the overlap")
    assert corpus_files == 1 and surface_count >= 2


def test_the_corpus_report_is_never_a_verdict(tmp_path, capsys):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.py").write_text("doctrine\n" * 40)
    assert main([str(REPO), "--against", str(corpus)]) == 0
    out = capsys.readouterr().out
    assert "REPORT ONLY" in out
    assert "not sufficient" in out.lower()
    assert "never run in CI" in out or "never a gate" in out


def test_a_missing_corpus_exits_two_not_zero(tmp_path, capsys):
    assert main([str(REPO), "--against", str(tmp_path / "nope")]) == 2
    assert "not a pass" in capsys.readouterr().err


# ── wiring ───────────────────────────────────────────────────────────────────

def test_the_precommit_gate_runs_this_guard():
    """A guard nobody runs at commit time is a guard that catches the leak
    after it has shipped."""
    text = (REPO / "plugin" / "scripts" / "precommit_gate.py").read_text()
    assert "framework_shape.py" in text and "--diff" in text


def test_ci_runs_the_full_scan_over_this_repository():
    """The selfcheck lists are covered by the class ratchet in
    test_detectors_and_wiring; this pins the REAL run, which is the one that
    would have caught round 18's leak."""
    ci = (REPO / ".github" / "workflows" / "selftest.yml").read_text()
    assert "framework_shape.py ." in ci
