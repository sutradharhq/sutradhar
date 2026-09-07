# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""A ratchet key is an IDENTITY, not a position (R18-1).

The defect this file guards was in our own shipped code. `ratchet.py`
documented key mode as "violations are identifiers (file:line, route names,
...)"; `detectors.find_unresolved_relative_imports` emitted `file:line:
message`; `dead_route_lint.find_unfailable_assertions` emitted `a.cy.ts:1`;
and `docs/backend.md` and `docs/frontend.md` showed adopters wiring exactly
those into `Ratchet(...).assert_only_shrinks(...)`. Every one of those
baselines re-flagged its banked findings on any edit above them, and the
obvious fix - `--update-baseline` - banks the real new findings too.

These are class ratchets over the SHIPPED detectors rather than point tests
per detector (doctrine 2.1), so a detector added later is covered the day it
lands. The load-bearing one is `test_keys_survive_lines_inserted_above`: it
asserts the invariant behaviourally, and its companion assertion proves the
fixture actually moved, because a shift that did not happen would make the
whole case pass vacuously (3.6).
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.dead_route_lint import (  # noqa: E402
    find_dead_routes,
    find_unfailable_assertions,
)
from sutradhar_guards.detectors import (  # noqa: E402
    find_order_by_without_limit,
    find_unresolved_relative_imports,
)
from sutradhar_guards.ratchet import Ratchet, RatchetError, Violation  # noqa: E402

# A line number anywhere in a key. `:12`, `:12:` and `a.cy.ts:5` all match.
LINE_NUMBER = re.compile(r":\d+")


# ── the fixtures each shipped detector is exercised over ────────────────────
# name -> (plant, run, comment prefix, files to shift, message carries a line)
#
# The last flag is honest bookkeeping, not a loophole: `find_dead_routes`
# reports a spec and an absent path and never had a line to lose, so its
# "the fixture actually moved" witness is the file text rather than the
# message. Spelling that difference out beats a case that quietly proves
# less than the others (2.9).

def _plant_imports(root: Path) -> None:
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "real.py").write_text("VALUE = 1\n")
    (pkg / "broken.py").write_text(
        "from .real import VALUE\n"
        "from .nowhere import thing\n"
        "from .real import MISSING\n"
    )


def _plant_specs(root: Path) -> None:
    (root / "a.cy.ts").write_text(
        'cy.request({ url: `${BASE}/ghost/route` }).then((res) => {\n'
        "  expect(res.status).to.not.eq(500);\n"
        "});\n"
        "expect(other.status).to.not.eq(500);\n"
    )


def _plant_query(root: Path) -> None:
    (root / "q.py").write_text(
        'def read():\n'
        '    return db.query("SELECT * FROM readings ORDER BY ts DESC")\n'
    )


DETECTORS = {
    "unresolved_relative_imports": (
        _plant_imports,
        lambda root: find_unresolved_relative_imports(root / "pkg"),
        "# pushed down\n",
        ("pkg/broken.py",),
        True,
    ),
    "unfailable_assertions": (
        _plant_specs,
        lambda root: find_unfailable_assertions(root),
        "// pushed down\n",
        ("a.cy.ts",),
        True,
    ),
    "dead_routes": (
        _plant_specs,
        lambda root: find_dead_routes(root, {"/real/route"}),
        "// pushed down\n",
        ("a.cy.ts",),
        False,
    ),
    "order_by_without_limit": (
        _plant_query,
        lambda root: find_order_by_without_limit(
            (root / "q.py").read_text(), "q.py"
        ),
        "# pushed down\n",
        ("q.py",),
        True,
    ),
}


def test_the_detector_table_is_not_empty():
    """Guards the guard: an empty table makes every parametrised case below
    pass vacuously, which is exactly rule 3.6's complaint about counting."""
    assert len(DETECTORS) >= 4, DETECTORS


@pytest.mark.parametrize("name", sorted(DETECTORS))
def test_a_detector_finds_the_planted_case(name, tmp_path):
    """Without this, `keys survive a shift` would be comparing two empty
    sets and reporting a green invariant nothing exercised."""
    plant, run = DETECTORS[name][:2]
    plant(tmp_path)
    assert run(tmp_path), f"{name} found nothing in its planted fixture"


@pytest.mark.parametrize("name", sorted(DETECTORS))
def test_no_key_contains_a_line_number(name, tmp_path):
    plant, run = DETECTORS[name][:2]
    plant(tmp_path)
    offenders = [v.key for v in run(tmp_path) if LINE_NUMBER.search(v.key)]
    assert not offenders, (
        f"{name} banks a position, not an identity: {offenders}. Any edit "
        f"above one of these re-flags a banked finding as new, and the quick "
        f"way out (--update-baseline) banks the real new ones with it."
    )


@pytest.mark.parametrize("name", sorted(DETECTORS))
def test_the_line_number_still_reaches_the_reader(name, tmp_path):
    """The line has to go somewhere. Dropping it from the key must not drop
    it from the report, or a stable baseline costs the reader the location."""
    plant, run = DETECTORS[name][:2]
    plant(tmp_path)
    found = run(tmp_path)
    assert all(v.message for v in found), (
        f"{name} returns keys with no human-readable message"
    )


@pytest.mark.parametrize("name", sorted(DETECTORS))
def test_keys_survive_lines_inserted_above(name, tmp_path):
    """The invariant, asserted behaviourally rather than by regex.

    Insert lines at the top of every fixture file, so every violation in it
    moves, and require the banked key set to be byte-identical.
    """
    plant, run, comment, files, line_in_message = DETECTORS[name]
    plant(tmp_path)
    before = run(tmp_path)
    original = {rel: (tmp_path / rel).read_text() for rel in files}
    for rel in files:
        f = tmp_path / rel
        f.write_text(comment * 7 + f.read_text())
    after = run(tmp_path)

    assert all((tmp_path / rel).read_text() != original[rel] for rel in files), (
        f"{name}: the fixture was not rewritten - this case would pass "
        f"whatever the keys did"
    )
    if line_in_message:
        assert {v.message for v in before} != {v.message for v in after}, (
            f"{name}: the findings did not move - this case would pass "
            f"whatever the keys did"
        )
    assert {v.key for v in before} == {v.key for v in after}, (
        f"{name}: seven lines inserted above the findings changed their keys\n"
        f"before: {sorted(v.key for v in before)}\n"
        f"after:  {sorted(v.key for v in after)}"
    )


def test_a_shifted_baseline_stays_green_through_the_ratchet(tmp_path):
    """End to end, through the real seam an adopter uses (2.3): bank a
    baseline, edit the file above the finding, run the gate again."""
    root = tmp_path / "tree"
    root.mkdir()
    _plant_imports(root)
    baseline = Ratchet(tmp_path / "imports.json", "imports")
    baseline.assert_only_shrinks(find_unresolved_relative_imports(root / "pkg"),
                                 update=True)

    broken = root / "pkg" / "broken.py"
    broken.write_text('"""A docstring somebody added."""\nimport os\n'
                      + broken.read_text())
    baseline.assert_only_shrinks(find_unresolved_relative_imports(root / "pkg"))


# ── two of the same thing in one file ───────────────────────────────────────

def test_a_repeated_match_gets_its_own_key_and_does_not_rename_the_first(tmp_path):
    """Adding a second identical assertion must not renumber the first's
    banked entry - the set gains one member and loses none."""
    (tmp_path / "a.cy.ts").write_text("expect(res.status).to.not.eq(500);\n")
    one = [v.key for v in find_unfailable_assertions(tmp_path)]
    assert one == ["a.cy.ts::.to.not.eq(500)"]

    (tmp_path / "a.cy.ts").write_text(
        "expect(res.status).to.not.eq(500);\nexpect(b.status).to.not.eq(500);\n"
    )
    two = [v.key for v in find_unfailable_assertions(tmp_path)]
    assert two == ["a.cy.ts::.to.not.eq(500)", "a.cy.ts::.to.not.eq(500)#2"]
    assert set(one) < set(two), "the first entry was renamed by the second"


def test_two_identical_queries_in_one_file_key_apart(tmp_path):
    """The same defect twice is two things to fix, and banking one key for
    both silently halves the floor. Adding the second must not rename the
    first: the set gains a member and loses none."""
    one = 'q = "SELECT * FROM t ORDER BY ts"\n'
    keys_one = [v.key for v in find_order_by_without_limit(one, "q.py")]
    assert keys_one == ["q.py::SELECT * FROM t ORDER BY ts"]
    keys_two = [v.key for v in find_order_by_without_limit(one * 2, "q.py")]
    assert len(keys_two) == 2 and keys_two[1].endswith("#2")
    assert keys_two[0] == keys_one[0], "the first entry was renamed by the second"


def test_the_same_broken_import_twice_keys_apart(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text("from .nowhere import thing\n" * 2)
    keys = [v.key for v in find_unresolved_relative_imports(pkg)]
    assert len(keys) == 2 and keys[1].endswith("#2"), keys


def test_two_unresolved_imports_of_different_names_key_apart(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "real.py").write_text("VALUE = 1\n")
    (pkg / "m.py").write_text("from .real import A, B\n")
    keys = sorted(v.key for v in find_unresolved_relative_imports(pkg))
    assert [k.split("::", 1)[1] for k in keys] == [
        "from .real import A", "from .real import B",
    ]


# ── migrate_keys: the only supported way across a key-scheme change ─────────

def _legacy(tmp_path) -> Ratchet:
    r = Ratchet(tmp_path / "b.json", "legacy")
    r.assert_only_shrinks(["a.py:12 read", "a.py:30 write"], update=True)
    return r


def test_migrate_keys_rewrites_one_to_one(tmp_path):
    r = _legacy(tmp_path)
    out = r.migrate_keys({"a.py:12 read": "a.py::read",
                          "a.py:30 write": "a.py::write"})
    assert out == ["a.py::read", "a.py::write"]
    r.assert_only_shrinks(["a.py::read", "a.py::write"])


def test_migrate_keys_refuses_an_entry_it_cannot_place(tmp_path):
    """The refusal is the feature. A partial migration silently drops a
    banked violation back into the unbanked pile, where the next run reports
    it as new and the reader reaches for --update-baseline."""
    r = _legacy(tmp_path)
    with pytest.raises(RatchetError, match="no new key in the mapping"):
        r.migrate_keys({"a.py:12 read": "a.py::read"})
    assert r._read_list() == ["a.py:12 read", "a.py:30 write"], (
        "a refused migration still wrote the file"
    )


def test_migrate_keys_never_banks_an_entry_that_was_not_banked(tmp_path):
    """`--update-baseline` is what this method exists to not be."""
    r = _legacy(tmp_path)
    with pytest.raises(RatchetError, match="not in the baseline"):
        r.migrate_keys({"a.py:12 read": "a.py::read",
                        "a.py:30 write": "a.py::write",
                        "a.py:99 purge": "a.py::purge"})
    assert r._read_list() == ["a.py:12 read", "a.py:30 write"]


def test_migrate_keys_refuses_a_merge(tmp_path):
    """Two banked violations collapsing into one key is a floor given back
    without anybody deciding to."""
    r = _legacy(tmp_path)
    with pytest.raises(RatchetError, match="not one to one"):
        r.migrate_keys({"a.py:12 read": "a.py::read",
                        "a.py:30 write": "a.py::read"})
    assert r._read_list() == ["a.py:12 read", "a.py:30 write"]


def test_migrate_keys_refuses_an_empty_baseline(tmp_path):
    """Otherwise it becomes a second --update-baseline with a better name."""
    r = Ratchet(tmp_path / "none.json", "none")
    with pytest.raises(RatchetError, match="nothing to migrate"):
        r.migrate_keys({"a": "b"})


# ── the Violation carrier ───────────────────────────────────────────────────

def test_a_violation_banks_its_key_and_reports_its_message(tmp_path):
    r = Ratchet(tmp_path / "v.json", "v")
    r.assert_only_shrinks([Violation("a.py::read", "a.py:12: reads uncapped")],
                          update=True)
    assert r._read_list() == ["a.py::read"]
    with pytest.raises(RatchetError, match="a.py:40"):
        r.assert_only_shrinks([
            Violation("a.py::read", "a.py:12: reads uncapped"),
            Violation("a.py::write", "a.py:40: writes uncapped"),
        ])


def test_plain_strings_still_work(tmp_path):
    """Adopters' own detectors return strings; the contract did not move."""
    r = Ratchet(tmp_path / "s.json", "s")
    r.assert_only_shrinks(["one", "two"], update=True)
    r.assert_only_shrinks(["one", "two"])


# ── the documented wiring must not teach the defect back ────────────────────

# Snippets an adopter would copy. A round record has to be able to QUOTE the
# defect it is recording, so history is scanned and only code is judged.
_TAUGHT_KEYS = ('f"{f}:{hit}"', 'f"{py}:{node.lineno}"', 'f"{spec.name}:{i}"')


def _fenced_code(text: str) -> str:
    """The fenced code blocks of a markdown document, concatenated."""
    blocks, inside = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if inside:
            blocks.append(line)
    return "\n".join(blocks)


def test_no_shipped_doc_teaches_a_line_number_as_a_ratchet_key():
    """R18-1 reached adopters through the docs, not only through the code:
    `docs/backend.md` showed `f"{f}:{hit}"` going into `assert_only_shrinks`,
    which is the shape an adopter copies.

    Only CODE is judged, and round records are exempt: a document recording
    the defect must be able to name it, and a gate that refuses that teaches
    people to describe incidents vaguely."""
    root = Path(__file__).resolve().parents[2]
    docs = [
        d for d in sorted((root / "docs").rglob("*.md"))
        if "rounds" not in d.relative_to(root).parts
    ] + [root / "README.md"]
    assert len(docs) >= 5, "scanned almost nothing - this would pass vacuously"
    offenders = []
    for doc in docs:
        code = _fenced_code(doc.read_text(encoding="utf-8", errors="replace"))
        if any(snippet in code for snippet in _TAUGHT_KEYS):
            offenders.append(str(doc.relative_to(root)))
    assert not offenders, (
        f"these documents show a file:line ratchet key in code an adopter "
        f"would copy: {offenders}"
    )
