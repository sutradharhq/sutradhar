# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Tests for the design-note scar admission gate (R14-8).

8.1 says a mechanism enters with the incident that paid for it. The backflow
register makes that computable for RULES; nothing made it computable for
MECHANISMS, so a design note could enter on argument alone. Every note in this
repo happened to cite a scar in its prose, one cited nothing, and no gate would
have refused a note that cited nothing - a habit, not a discipline.

So the load-bearing tests here are the ones that prove the gate REFUSES: a
missing key, an id nobody can resolve, and a bare `distribution` with no
argument behind it. `distribution` is a legitimate way in; an unstated one is
the thing being closed.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.rounds import (  # noqa: E402
    RoundError,
    load_design_notes,
    main,
    parse_scar,
    scar_problems,
)

KNOWN = {"R10-1", "R4-5", "R3-1"}


def note(front: str, body: str = "\n# Design note: planted\n\nprose.\n") -> str:
    return "---\n" + front + "---\n" + body


# ── the mechanism: a note must name what paid for it ─────────────────────────

def test_a_note_citing_a_finding_in_the_records_passes():
    c = parse_scar(note("sutradhar_scar: R10-1\n"), source="planted.md")
    assert c.findings == ["R10-1"] and c.distribution is False
    assert scar_problems([c], KNOWN) == []


def test_a_note_citing_an_id_no_round_record_contains_fails():
    """The whole point. An id nobody can resolve reads as provenance and
    carries none - the same failure as citing nothing, better disguised."""
    c = parse_scar(note("sutradhar_scar: R99-9\n"), source="ghost.md")
    problems = scar_problems([c], KNOWN)
    assert len(problems) == 1
    assert "R99-9" in problems[0] and "ghost.md" in problems[0]


def test_a_note_with_no_scar_key_is_refused_and_names_the_file():
    """Before this, a note that entered on argument alone cost nothing."""
    with pytest.raises(RoundError, match="quiet.md"):
        parse_scar(note("sutradhar_budget: q\nn: 5\n"), source="quiet.md")


def test_an_empty_scar_value_is_refused_too():
    """Otherwise the key becomes a box to tick rather than a claim to make."""
    with pytest.raises(RoundError, match="sutradhar_scar"):
        parse_scar(note("sutradhar_scar:\n"), source="blank.md")


def test_several_ids_may_be_cited_and_every_one_must_resolve():
    """A note can be paid for by more than one incident; a list is not a
    place to hide one unresolvable id among the real ones."""
    good = parse_scar(note("sutradhar_scar: R3-1, R4-5\n"), source="two.md")
    assert good.findings == ["R3-1", "R4-5"]
    assert scar_problems([good], KNOWN) == []
    mixed = parse_scar(note("sutradhar_scar: R3-1, R99-9\n"), source="two.md")
    assert len(scar_problems([mixed], KNOWN)) == 1


def test_a_deferred_finding_still_counts_as_an_incident():
    """R3-1 was deferred for two rounds before it was fixed. Refusing open
    findings would push notes towards citing nothing, which is the defect."""
    root = Path(__file__).resolve().parents[2]
    deferred = (root / "docs" / "rounds" / "round-003.md").read_text()
    assert "| R3-1 | high |" in deferred and "| deferred |" in deferred
    c = parse_scar(note("sutradhar_scar: R3-1\n"), source="ok.md")
    assert scar_problems([c], {"R3-1"}) == []


def test_something_that_is_not_a_finding_id_is_refused():
    for bad in ("R10", "10-1", "round 10", "R10-1 R4-5"):
        with pytest.raises(RoundError, match="not a finding id"):
            parse_scar(note("sutradhar_scar: %s\n" % bad), source="bad.md")


# ── `distribution`: an allowed answer, never an unstated one ─────────────────

def test_distribution_with_no_argument_is_refused():
    """A bare `distribution` is exactly the argument-alone admission this
    gate exists to make somebody write down."""
    with pytest.raises(RoundError, match="sutradhar_scar_argument"):
        parse_scar(note("sutradhar_scar: distribution\n"), source="reach.md")


def test_distribution_with_an_empty_argument_is_refused():
    with pytest.raises(RoundError, match="sutradhar_scar_argument"):
        parse_scar(note("sutradhar_scar: distribution\nsutradhar_scar_argument:   \n"),
                   source="reach.md")


def test_distribution_with_an_argument_is_a_way_in():
    """Refusing it outright would only teach people to cite a loosely
    related finding, which is worse than an honest sentence."""
    c = parse_scar(
        note("sutradhar_scar: distribution\n"
             "sutradhar_scar_argument: adopters need a filled-in example\n"),
        source="reach.md",
    )
    assert c.distribution is True and c.findings == []
    assert "adopters" in c.argument
    assert scar_problems([c], KNOWN) == []


# ── the parser refuses rather than skipping (2.9, in the instrument) ─────────

@pytest.mark.parametrize(
    "label,text,match",
    [
        ("no frontmatter at all", "# Design note: bare\n\nprose.\n", "sutradhar_scar"),
        ("unclosed frontmatter", "---\nsutradhar_scar: R10-1\n", "never closed"),
        ("nested structure", "---\nsutradhar_scar: R10-1\nlimits:\n  - 5\n---\n", "cannot parse"),
        ("duplicate key", "---\nsutradhar_scar: R10-1\nsutradhar_scar: R4-5\n---\n", "twice"),
    ],
)
def test_a_note_the_parser_cannot_read_is_refused_not_skipped(label, text, match):
    """'Cannot read this note' must not be spelled the same as 'this note
    passed' - the malformed note would otherwise be the one way back in."""
    with pytest.raises(RoundError, match=match):
        parse_scar(text, source="broken.md")


def test_the_shipped_template_is_skipped_by_name(tmp_path):
    """Its placeholder frontmatter would open every fresh bootstrap red,
    which is the fastest way to teach someone a tool cries wolf."""
    (tmp_path / "TEMPLATE.md").write_text(note("sutradhar_scar: <finding-id>\n"))
    (tmp_path / "real.md").write_text(note("sutradhar_scar: R10-1\n"))
    assert [p.name for p in load_design_notes(tmp_path)] == ["real.md"]


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


def _run(tmp_path: Path, designs: Path, *extra: str) -> int:
    return main([str(_rounds_dir(tmp_path)), "--designs", str(designs),
                 "--doctrine", "DOCTRINE.md", *extra])


def test_a_missing_designs_directory_exits_two_not_zero(tmp_path, capsys):
    """2.9. Asked which incident paid for each mechanism and handed nothing
    to read, the honest answer is 'I did not check'."""
    rc = _run(tmp_path, tmp_path / "nope")
    assert rc == 2
    assert "nothing was checked" in capsys.readouterr().out


def test_a_designs_directory_with_no_notes_exits_two_not_zero(tmp_path, capsys):
    empty = tmp_path / "design"
    empty.mkdir()
    rc = _run(tmp_path, empty)
    assert rc == 2
    assert "nothing was checked" in capsys.readouterr().out


def test_a_directory_holding_only_the_template_exits_two_not_zero(tmp_path, capsys):
    """The template is skipped by name, so a directory of nothing else has
    told the gate nothing - and must not report as five green notes."""
    d = tmp_path / "design"
    d.mkdir()
    (d / "TEMPLATE.md").write_text(note("sutradhar_scar: <finding-id>\n"))
    assert _run(tmp_path, d) == 2
    assert "nothing was checked" in capsys.readouterr().out


def test_the_cli_fails_on_an_unresolvable_id(tmp_path, capsys):
    d = tmp_path / "design"
    d.mkdir()
    (d / "a.md").write_text(note("sutradhar_scar: R9-9\n"))
    assert _run(tmp_path, d) == 1
    assert "R9-9" in capsys.readouterr().out


def test_the_cli_fails_on_a_note_that_names_no_incident(tmp_path, capsys):
    d = tmp_path / "design"
    d.mkdir()
    (d / "a.md").write_text(note("sutradhar_budget: a\nn: 5\n"))
    assert _run(tmp_path, d) == 1
    assert "a.md" in capsys.readouterr().out


def test_the_cli_fails_on_a_bare_distribution(tmp_path, capsys):
    d = tmp_path / "design"
    d.mkdir()
    (d / "a.md").write_text(note("sutradhar_scar: distribution\n"))
    assert _run(tmp_path, d) == 1
    assert "sutradhar_scar_argument" in capsys.readouterr().out


def test_the_cli_passes_and_reports_the_split(tmp_path, capsys):
    d = tmp_path / "design"
    d.mkdir()
    (d / "a.md").write_text(note("sutradhar_scar: R1-1\n"))
    (d / "b.md").write_text(note("sutradhar_scar: R2-1\n"))
    (d / "c.md").write_text(
        note("sutradhar_scar: distribution\n"
             "sutradhar_scar_argument: adopters need a worked example\n")
    )
    assert _run(tmp_path, d) == 0
    assert ("scars OK - 3 note(s), 2 cite finding(s), 1 enter on distribution"
            in capsys.readouterr().out)


def test_it_composes_with_check(tmp_path, capsys):
    """--backflow composes this way, and a gate that only runs alone is a
    gate somebody drops from the CI line to make room."""
    d = tmp_path / "design"
    d.mkdir()
    (d / "a.md").write_text(note("sutradhar_scar: R1-1\n"))
    assert _run(tmp_path, d, "--check") == 0
    out = capsys.readouterr().out
    assert "scars OK" in out and "record(s) valid" in out


# ── the shipped notes themselves ─────────────────────────────────────────────

def test_this_repos_design_notes_all_name_what_paid_for_them():
    root = Path(__file__).resolve().parents[2]
    notes = load_design_notes(root / "docs" / "design")
    assert len(notes) >= 5
    citations = [parse_scar(p.read_text(), source=str(p)) for p in notes]
    known = set()
    for record in sorted((root / "docs" / "rounds").glob("*.md")):
        for line in record.read_text().splitlines():
            if line.startswith("| R"):
                known.add(line.strip("|").split("|")[0].strip())
    assert scar_problems(citations, known) == []
    assert any(c.findings for c in citations), (
        "no shipped note cites an incident; the gate would be passing on "
        "distribution admissions alone"
    )


def test_ci_runs_the_scar_gate():
    """A note that entered on argument alone recurs the moment nothing
    runs this."""
    root = Path(__file__).resolve().parents[2]
    ci = (root / ".github" / "workflows" / "selftest.yml").read_text()
    assert "--designs" in ci, "CI no longer checks what paid for each design note"


def test_the_template_ships_the_field():
    """An adopter filling in the template must meet the question there, not
    for the first time in a red CI run."""
    root = Path(__file__).resolve().parents[2]
    tpl = (root / "docs" / "templates" / "design-note.md").read_text()
    assert "sutradhar_scar:" in tpl and "sutradhar_scar_argument:" in tpl
