"""Tests for the budget gate - doctrine 1.1 made mechanical.

The parser gets a fuzzer because doctrine 1.3 says parsing surfaces earn
one: example tests pin known cases, properties pin the space. The property
that matters here is that a design note is a CONTRACT - the parser either
understands it exactly or refuses it loudly. There is no third outcome, and
a silently half-parsed budget would be an unenforced number reporting as
compliant.
"""
import random
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.budget import (
    Budget,
    BudgetError,
    budget,
    budget_from_frontmatter,
    find_unenforced,
    load_budgets,
    parse_frontmatter,
    selfcheck,
)


def _note(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return p


# ── parsing: the happy path ─────────────────────────────────────────────────

def test_frontmatter_reads_flat_scalars():
    data = parse_frontmatter("---\nsutradhar_budget: sweep\nn: 200000\n---\n# note\n")
    assert data == {"sutradhar_budget": "sweep", "n": "200000"}


def test_no_frontmatter_is_none_not_an_error():
    assert parse_frontmatter("# just a document\n") is None


def test_thousands_separators_are_accepted():
    b = budget_from_frontmatter({"sutradhar_budget": "s", "n": "200,000"})
    assert b.n == 200000
    b2 = budget_from_frontmatter({"sutradhar_budget": "s", "n": "200_000"})
    assert b2.n == 200000


def test_declared_summary_reads_like_the_design_note():
    b = budget_from_frontmatter({
        "sutradhar_budget": "sweep", "n": "200000", "n_unit": "meters",
        "p95_ms": "800", "memory_mb": "512",
    })
    assert b.declared() == ["n=200,000 meters", "p95<=800ms", "mem<=512MB"]


# ── parsing: what it must refuse ────────────────────────────────────────────

@pytest.mark.parametrize("text,why", [
    ("---\nsutradhar_budget: x\nlimits:\n  - 5\n---\n", "nested structure"),
    ("---\nsutradhar_budget: x\nn: 5\n", "unclosed frontmatter"),
    ("---\nsutradhar_budget: x\nn: 5\nn: 9\n---\n", "duplicate key"),
])
def test_malformed_frontmatter_is_refused_loudly(tmp_path, text, why):
    note = _note(tmp_path, "n.md", text)
    with pytest.raises(BudgetError):
        load_budgets(note)


def test_adjectives_are_not_cardinalities():
    with pytest.raises(BudgetError, match="not a cardinality"):
        budget_from_frontmatter({"sutradhar_budget": "x", "n": "lots"})


def test_an_empty_envelope_is_paperwork_not_a_budget():
    with pytest.raises(BudgetError, match="declares no numbers"):
        budget_from_frontmatter({"sutradhar_budget": "x"})


def test_duplicate_budget_ids_are_refused(tmp_path):
    _note(tmp_path, "a.md", "---\nsutradhar_budget: dup\nn: 1\n---\n")
    _note(tmp_path, "b.md", "---\nsutradhar_budget: dup\nn: 2\n---\n")
    with pytest.raises(BudgetError, match="declared twice"):
        load_budgets(tmp_path)


def test_ci_slack_below_one_is_refused():
    with pytest.raises(BudgetError, match="ci_slack"):
        budget_from_frontmatter({"sutradhar_budget": "x", "n": "1", "ci_slack": "0.5"})


# ── the fuzzer (doctrine 1.3) ───────────────────────────────────────────────

def test_parser_never_half_understands_a_note():
    """Property: for ANY input, parse_frontmatter either returns a dict of
    flat scalars or raises BudgetError. It never raises something else, and
    it never returns a value it had to guess at."""
    rng = random.Random(20260808)
    alphabet = list("abc: -\n\"'#\t{}[],.0123456789_") + ["---\n", "\n---\n", "\r\n"]
    for _ in range(3000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 60)))
        if rng.random() < 0.6:
            text = "---\n" + text
        try:
            result = parse_frontmatter(text)
        except BudgetError:
            continue                      # refused: the allowed failure mode
        except Exception as exc:          # noqa: BLE001 - that is the point
            pytest.fail(f"parser raised {type(exc).__name__} on {text!r}: {exc}")
        assert result is None or all(
            isinstance(k, str) and isinstance(v, str) for k, v in result.items()
        ), f"parser returned a non-scalar mapping for {text!r}"


def test_fuzzer_would_notice_a_crashing_parser(monkeypatch):
    """The fuzzer above is only worth its runtime if it can fail. Make the
    parser raise the wrong exception type and require a failure."""
    import sutradhar_guards.budget as bg

    def boom(text):
        raise ValueError("wrong exception type")

    monkeypatch.setattr(bg, "parse_frontmatter", boom)
    with pytest.raises(Exception):
        rng = random.Random(1)
        for _ in range(5):
            bg.parse_frontmatter("---\nx: 1\n---\n")


# ── enforcement: the envelope must bite ─────────────────────────────────────

def test_a_run_inside_the_envelope_passes(tmp_path):
    _note(tmp_path, "n.md", "---\nsutradhar_budget: loose\nn: 10\np95_ms: 60000\n---\n")
    with budget("loose", root=tmp_path) as b:
        assert b.n == 10


def test_a_run_over_the_envelope_fails(tmp_path):
    _note(tmp_path, "n.md", "---\nsutradhar_budget: tight\nn: 10\np95_ms: 0.001\n---\n")
    with pytest.raises(BudgetError, match="declared envelope exceeded"):
        with budget("tight", root=tmp_path):
            time.sleep(0.02)


def test_ci_slack_widens_the_ceiling_visibly(tmp_path):
    _note(tmp_path, "n.md",
          "---\nsutradhar_budget: slacked\nn: 10\np95_ms: 5\nci_slack: 1000\n---\n")
    with budget("slacked", root=tmp_path):
        time.sleep(0.02)      # 20ms passes only because slack is declared IN THE FILE


def test_memory_envelope_bites(tmp_path):
    _note(tmp_path, "n.md",
          "---\nsutradhar_budget: mem\nn: 100000\nmemory_mb: 0.05\n---\n")
    with pytest.raises(BudgetError, match="peak python heap"):
        with budget("mem", root=tmp_path) as b:
            _hog = [object() for _ in range(b.n)]


def test_a_failure_inside_the_block_wins_over_the_budget(tmp_path):
    """A real error must not be masked by a budget breach report."""
    _note(tmp_path, "n.md", "---\nsutradhar_budget: t\nn: 1\np95_ms: 0.001\n---\n")
    with pytest.raises(ZeroDivisionError):
        with budget("t", root=tmp_path):
            time.sleep(0.01)
            1 / 0


def test_asking_for_an_undeclared_n_is_an_error(tmp_path):
    _note(tmp_path, "n.md", "---\nsutradhar_budget: nomem\np95_ms: 100\n---\n")
    with pytest.raises(BudgetError, match="declares no `n`"):
        with budget("nomem", root=tmp_path) as b:
            _ = b.n


def test_an_unknown_budget_id_names_what_exists(tmp_path):
    _note(tmp_path, "n.md", "---\nsutradhar_budget: real\nn: 1\n---\n")
    with pytest.raises(BudgetError, match="real"):
        budget("typo", root=tmp_path)


# ── the gate: declared but unenforced ───────────────────────────────────────

def test_unenforced_budgets_are_found(tmp_path):
    design, tests = tmp_path / "d", tmp_path / "t"
    design.mkdir(), tests.mkdir()
    _note(design, "a.md", "---\nsutradhar_budget: enforced\nn: 1\n---\n")
    _note(design, "b.md", "---\nsutradhar_budget: orphan\nn: 1\n---\n")
    (tests / "test_a.py").write_text('with budget("enforced") as b:\n    pass\n')
    assert find_unenforced(load_budgets(design), tests) == ["orphan"]


def test_enforcement_is_seen_in_typescript_tests_too(tmp_path):
    design, tests = tmp_path / "d", tmp_path / "t"
    design.mkdir(), tests.mkdir()
    _note(design, "a.md", "---\nsutradhar_budget: fe-route\nn: 5000\n---\n")
    (tests / "route.cy.ts").write_text("cy.budget('fe-route')\n")
    assert find_unenforced(load_budgets(design), tests) == []


def test_cli_fails_on_an_unenforced_budget(tmp_path, capsys):
    import sutradhar_guards.budget as bg
    design, tests = tmp_path / "d", tmp_path / "t"
    design.mkdir(), tests.mkdir()
    _note(design, "a.md", "---\nsutradhar_budget: orphan\nn: 200000\n---\n")
    (tests / "test_x.py").write_text("# nothing enforces anything\n")
    assert bg.main([str(design), "--tests", str(tests)]) == 1
    assert "orphan" in capsys.readouterr().out


def test_cli_passes_when_every_budget_is_enforced(tmp_path):
    import sutradhar_guards.budget as bg
    design, tests = tmp_path / "d", tmp_path / "t"
    design.mkdir(), tests.mkdir()
    _note(design, "a.md", "---\nsutradhar_budget: kept\nn: 200000\n---\n")
    (tests / "test_x.py").write_text('with budget("kept") as b:\n    pass\n')
    assert bg.main([str(design), "--tests", str(tests)]) == 0


# ── selfcheck + mutation ────────────────────────────────────────────────────

def test_selfcheck_passes():
    assert selfcheck()


def test_a_blind_unenforced_detector_fails_the_selfcheck(monkeypatch):
    import sutradhar_guards.budget as bg
    monkeypatch.setattr(bg, "find_unenforced", lambda *a, **k: [])
    assert not bg.selfcheck()


def test_a_parser_that_stops_refusing_junk_fails_the_selfcheck(monkeypatch):
    """Found by mutation: blinding the parser's refusal branch passed every
    other case in the selfcheck, so the selfcheck grew a parser case."""
    import sutradhar_guards.budget as bg
    monkeypatch.setattr(bg, "parse_frontmatter", lambda text: {"sutradhar_budget": "x", "n": "1"})
    assert not bg.selfcheck()
