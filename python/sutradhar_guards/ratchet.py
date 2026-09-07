"""Ratchet: shrink-only allowlists for class-invariant tests.

The single highest-yield testing pattern from our build record. Instead of
pinning each fixed defect with its own test, write ONE detector over the
whole defect class (walk the AST, the route table, the schema - whatever
enumerates the siblings) and gate it with a ratchet:

  - current violations already known are held in a frozen baseline file;
  - a NEW violation (not in the baseline) fails the build immediately;
  - a baseline entry that is no longer a violation ALSO fails, with
    "remove it from the baseline" - so the floor drops monotonically and a
    silently-fixed entry cannot linger as a hole the detector never re-checks.

That second failure mode is the guard-the-guard: it is what distinguishes a
ratchet from an ignore-list. An ignore-list only grows; a ratchet only
shrinks.

The evidence for the pattern: on the codebase this framework distills,
~37 ratchet tests (2.5% of the suite) produced two thirds of all
test-driven discoveries, while ~1,400 per-defect point tests produced three.

Usage in a pytest test:

    from sutradhar_guards.ratchet import Ratchet

    def test_every_fleet_query_is_capped():
        violations = find_uncapped_queries(SRC_DIR)   # your detector
        Ratchet("tests/baselines/uncapped_queries.json").assert_only_shrinks(
            violations
        )

    def test_the_detector_itself_works():
        # A detector that cannot flag a planted bad case is decoration.
        assert find_uncapped_queries_in_source(KNOWN_BAD_SNIPPET)

To (re)record the baseline after fixing a violation:

    RATCHET_UPDATE=1 pytest tests/test_ratchets.py

Baselines are sorted JSON lists (or dicts for count mode), reviewed in the
PR like any other file. A baseline diff that grows should be as alarming to
a reviewer as a deleted test.

## The key must be a stable IDENTITY, not a position

A baseline entry names a violation. It must name it in a way that survives
an edit somewhere else in the file, because a key that moves re-flags a
banked finding as new - and the obvious way out of that noise is
`--update-baseline`, which banks every genuinely new finding along with it.
So: **a line number must never appear in a key.** Use the qualified name of
the enclosing `def` (`Cls.method`, `outer.inner`) for a Python definition,
or the file plus the normalised matched text for anything else, and put the
line number in the human-readable message where it belongs.

*Scar, from a private build thread that shipped this ratchet: a baseline
keyed on `path:line name` re-flagged banked findings three times in one day
- a docstring edit above one function, a single added import, and a refactor
that moved three functions it did not change. Each time the tempting fix was
`--update-baseline`, which would have banked any real new finding along with
the noise. The key became `path::qualified_name`.*

When a detector's key scheme changes, migrate the baseline with
`Ratchet.migrate_keys` - never with `--update-baseline`, which cannot tell a
renamed entry from a new violation. `Violation(key, message)` is the shipped
way to carry both halves: the ratchet banks `.key` and prints `.message`.
"""
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Mapping, NamedTuple


class RatchetError(AssertionError):
    """Raised when a ratchet check fails. Subclasses AssertionError so it
    reads naturally in pytest output."""


class Violation(NamedTuple):
    """A finding whose banked IDENTITY and printed LOCATION are different
    strings, deliberately.

    `key` is what the baseline stores and must not contain a line number;
    `message` is what a person reads and should. A ratchet reads `.key`
    (and `str()` gives the same), so a detector can return these wherever
    it used to return plain strings.
    """

    key: str
    message: str = ""

    def __str__(self) -> str:
        return self.key


class Ratchet:
    def __init__(self, baseline_path: str | Path, name: str = ""):
        self.path = Path(baseline_path)
        self.name = name or self.path.stem

    # ── key mode: violations are stable identities ──────────────────────────
    # A key names a violation - a qualified function name, a route name, a
    # normalised matched string. NOT a position: see the module docstring.

    def assert_only_shrinks(
        self, current: Iterable[object], update: bool | None = None
    ) -> None:
        """Fail on any violation not in the baseline, and on any baseline
        entry that is no longer a violation (stale - must be removed).

        **The stable-key contract.** Each item is banked by its key: `.key`
        when the item has one (a `Violation`), otherwise `str(item)`. A key
        must identify the violation independently of where it sits in the
        file, so **a line number must not appear in it** - an edit anywhere
        above a banked finding would otherwise re-flag it as new, and the
        only quick way out is `--update-baseline`, which banks every real
        new finding at the same time. Put the line in the `message`.

        Changing a detector's key scheme invalidates every existing
        baseline. `migrate_keys` is the way across; re-recording is not.
        """
        detail: dict[str, str] = {}
        keys: list[str] = []
        for item in current:
            key = getattr(item, "key", None)
            key = key if isinstance(key, str) else str(item)
            keys.append(key)
            msg = getattr(item, "message", None)
            if isinstance(msg, str) and msg and key not in detail:
                detail[key] = msg
        cur = sorted(set(keys))
        if self._updating(update):
            self._write(cur)
            return
        base = set(self._read_list())
        new = [
            v if v not in detail else f"{v}\n      {detail[v]}"
            for v in cur if v not in base
        ]
        stale = [v for v in sorted(base) if v not in cur]
        self._raise_if_needed(new, stale)

    def migrate_keys(self, mapping: Mapping[str, str]) -> list[str]:
        """Rewrite this baseline from old keys to new, one to one, refusing
        anything it cannot place.

        That refusal is the point. A key-scheme change makes every banked
        entry look new, and `--update-baseline` would silently bank the real
        new findings alongside the renamed ones - which is the failure this
        method exists to make impossible. So it **never writes an entry that
        was not already banked**: every baseline entry must appear in
        `mapping`, every `mapping` key must be in the baseline, and two old
        keys may not collapse onto one new key. Any of those raises and the
        file on disk is left alone.

            Ratchet("tests/baselines/imports.json").migrate_keys(
                {"src/a.py:12: ...": "src/a.py::from .x import y"}
            )

        Returns the new baseline, sorted, as written.
        """
        old = self._read_list()
        if not old:
            raise RatchetError(
                f"[{self.name}] nothing to migrate: {self.path} holds no "
                f"entries. A migration that starts from an empty baseline "
                f"would only be a way of banking today's findings."
            )
        unplaceable = [k for k in old if k not in mapping]
        if unplaceable:
            raise RatchetError(
                f"[{self.name}] {len(unplaceable)} baseline entr(ies) have no "
                f"new key in the mapping:\n  " + "\n  ".join(sorted(unplaceable))
                + f"\nEvery banked entry must be placed. Do NOT re-record: "
                f"--update-baseline cannot tell a renamed entry from a new "
                f"violation and would bank both."
            )
        unbanked = [k for k in mapping if k not in set(old)]
        if unbanked:
            raise RatchetError(
                f"[{self.name}] {len(unbanked)} mapping key(s) are not in the "
                f"baseline:\n  " + "\n  ".join(sorted(unbanked))
                + f"\nA migration may only rename what is already banked."
            )
        new_keys = [mapping[k] for k in old]
        collisions = sorted({k for k in new_keys if new_keys.count(k) > 1})
        if collisions:
            raise RatchetError(
                f"[{self.name}] migration is not one to one - "
                f"{len(collisions)} new key(s) claimed by more than one old "
                f"entry:\n  " + "\n  ".join(collisions)
                + f"\nMerging two banked violations into one loses a floor."
            )
        out = sorted(set(new_keys))
        self._write(out)
        return out

    # ── count mode: per-key violation counts (file -> n) ────────────────────

    def assert_counts_only_shrink(
        self, current: Mapping[str, int], update: bool | None = None
    ) -> None:
        """Fail on any key whose count exceeds its baseline, and on any key
        whose count dropped below baseline without the baseline being
        re-recorded (bank the improvement or lose the floor)."""
        cur = {k: int(v) for k, v in current.items() if v}
        if self._updating(update):
            self._write(dict(sorted(cur.items())))
            return
        base: dict[str, int] = self._read_dict()
        grew = [
            f"{k}: {n} (baseline {base.get(k, 0)})"
            for k, n in sorted(cur.items())
            if n > base.get(k, 0)
        ]
        shrank = [
            f"{k}: {cur.get(k, 0)} (baseline {n})"
            for k, n in sorted(base.items())
            if cur.get(k, 0) < n
        ]
        self._raise_if_needed(grew, shrank)

    # ── internals ───────────────────────────────────────────────────────────

    @staticmethod
    def _updating(update: bool | None) -> bool:
        if update is not None:
            return update
        return os.environ.get("RATCHET_UPDATE", "").lower() in ("1", "true", "yes")

    def _write(self, data) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2) + "\n")

    def _read_list(self) -> list[str]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text())
        if not isinstance(data, list):
            raise RatchetError(
                f"[{self.name}] baseline {self.path} is not a list; "
                f"use assert_counts_only_shrink for dict baselines"
            )
        return data

    def _read_dict(self) -> dict[str, int]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text())
        if not isinstance(data, dict):
            raise RatchetError(
                f"[{self.name}] baseline {self.path} is not a dict; "
                f"use assert_only_shrinks for list baselines"
            )
        return data

    def _raise_if_needed(self, new: list[str], stale: list[str]) -> None:
        msgs: list[str] = []
        if new:
            msgs.append(
                f"[{self.name}] {len(new)} NEW violation(s) beyond the baseline "
                f"({self.path}):\n  " + "\n  ".join(new) + "\n"
                f"Fix them, or - only if each is genuinely intentional - "
                f"re-record with RATCHET_UPDATE=1."
            )
        if stale:
            msgs.append(
                f"[{self.name}] {len(stale)} baseline entr(ies) are no longer "
                f"violations - the ratchet only shrinks, so bank the fix:\n  "
                + "\n  ".join(stale)
                + f"\nRe-record with RATCHET_UPDATE=1 to drop the floor."
            )
        if msgs:
            raise RatchetError("\n\n".join(msgs))


def selfcheck_detector(detector, known_bad, label: str = "detector") -> None:
    """Assert that a detector flags a planted known-bad input.

    Call this from a sibling test of every ratchet. It is the difference
    between a guard and a green light wired to nothing: a detector edited
    into vacuity (a broken regex, a renamed AST node) passes every real file
    forever, and only a planted bad case can catch that.

        def test_uncapped_query_detector_still_detects():
            selfcheck_detector(
                find_uncapped_queries_in_source,
                'db.query(f"SELECT * FROM t")',
            )
    """
    result = detector(known_bad)
    if not result:
        raise RatchetError(
            f"[{label}] selfcheck failed: the detector found nothing in a "
            f"planted known-bad input. The guard is decoration until fixed."
        )


def selfcheck() -> bool:
    """The ratchet must SHRINK only, and must refuse a vacuous detector.

    Two behaviours carry this module. A baseline that can grow is a
    to-do list nobody reads; and `selfcheck_detector` must actually raise
    when handed a detector that finds nothing, or every ratchet built on it
    is a green light wired to nothing.
    """
    import tempfile

    ok = True

    def _fail(msg: str) -> None:
        nonlocal ok
        print(f"[ratchet] SELFCHECK FAILED: {msg}")
        ok = False

    try:
        selfcheck_detector(lambda s: [], "planted known-bad input", "vacuity")
        _fail("selfcheck_detector accepted a detector that finds nothing")
    except RatchetError:
        pass

    try:
        selfcheck_detector(lambda s: [1], "planted known-bad input", "working")
    except RatchetError as exc:
        _fail(f"selfcheck_detector rejected a working detector: {exc}")

    with tempfile.TemporaryDirectory() as td:
        counts = Ratchet(Path(td) / "counts.json", "counts")
        counts.assert_counts_only_shrink({"a.py": 2, "b.py": 1}, update=True)

        try:
            counts.assert_counts_only_shrink({"a.py": 2, "b.py": 1})
        except RatchetError as exc:
            _fail(f"an unchanged count was rejected: {exc}")

        try:
            counts.assert_counts_only_shrink({"a.py": 3, "b.py": 1})
            _fail("a GROWING count was accepted - the ratchet does not hold")
        except RatchetError:
            pass

        try:
            counts.assert_counts_only_shrink({"a.py": 2, "b.py": 1, "new.py": 1})
            _fail("a NEW offending file was accepted")
        except RatchetError:
            pass

        # Shrinking must ALSO fail until the baseline is re-recorded: an
        # improvement nobody banks is a floor quietly given back.
        try:
            counts.assert_counts_only_shrink({"a.py": 1, "b.py": 1})
            _fail("an unbanked improvement passed - the floor was given back")
        except RatchetError:
            pass

        listed = Ratchet(Path(td) / "list.json", "list")
        listed.assert_only_shrinks(["x.py::Cls.read", "y.py::parse"], update=True)

        try:
            listed.assert_only_shrinks(["x.py::Cls.read", "y.py::parse"])
        except RatchetError as exc:
            _fail(f"an unchanged violation set was rejected: {exc}")

        try:
            listed.assert_only_shrinks(
                ["x.py::Cls.read", "y.py::parse", "z.py::sweep"]
            )
            _fail("a NEW violation was accepted")
        except RatchetError:
            pass

        try:
            listed.assert_only_shrinks(["x.py::Cls.read"])
            _fail("a STALE baseline entry passed instead of demanding removal")
        except RatchetError:
            pass

        # A Violation banks its key and REPORTS its message: the line number
        # has to reach the reader without reaching the baseline.
        listed.assert_only_shrinks(
            [Violation("x.py::Cls.read", "x.py:12: reads without a cap")],
            update=True,
        )
        if json.loads((Path(td) / "list.json").read_text()) != ["x.py::Cls.read"]:
            _fail("a Violation banked something other than its key")
        try:
            listed.assert_only_shrinks(
                [Violation("x.py::Cls.read", "x.py:12: reads without a cap"),
                 Violation("x.py::Cls.write", "x.py:40: writes without a cap")]
            )
            _fail("a NEW Violation was accepted")
        except RatchetError as exc:
            if "x.py:40" not in str(exc):
                _fail("the report named no line; the message never reached the reader")

        # migrate_keys: renames what is banked and refuses everything else.
        mig = Ratchet(Path(td) / "mig.json", "mig")
        mig.assert_only_shrinks(["a.py:12 read", "a.py:30 write"], update=True)
        try:
            mig.migrate_keys({"a.py:12 read": "a.py::read"})
            _fail("a baseline entry with no new key was migrated anyway")
        except RatchetError:
            pass
        try:
            mig.migrate_keys({"a.py:12 read": "a.py::read",
                              "a.py:30 write": "a.py::write",
                              "a.py:99 purge": "a.py::purge"})
            _fail("migrate_keys BANKED an entry that was never banked")
        except RatchetError:
            pass
        try:
            mig.migrate_keys({"a.py:12 read": "a.py::read",
                              "a.py:30 write": "a.py::read"})
            _fail("two banked entries were merged into one; a floor was lost")
        except RatchetError:
            pass
        if json.loads((Path(td) / "mig.json").read_text()) != [
            "a.py:12 read", "a.py:30 write"
        ]:
            _fail("a REFUSED migration still wrote the baseline")
        moved = mig.migrate_keys({"a.py:12 read": "a.py::read",
                                  "a.py:30 write": "a.py::write"})
        if moved != ["a.py::read", "a.py::write"]:
            _fail(f"a one-to-one migration produced {moved}")
        try:
            mig.assert_only_shrinks(["a.py::read", "a.py::write"])
        except RatchetError as exc:
            _fail(f"the migrated baseline did not hold: {exc}")

    if ok:
        print(
            "[ratchet] selfcheck ok: growth refused, new entry refused, unbanked "
            "shrink refused, stale entry refused, vacuous detector refused, "
            "Violation banks its key and reports its line, migrate_keys refuses "
            "an unplaceable entry / an unbanked one / a merge and moves a "
            "one-to-one baseline"
        )
    return ok


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or "--selfcheck" in argv:
        return 0 if selfcheck() else 1
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    print(
        f"[ratchet] unknown argument(s): {' '.join(argv)}\n"
        f"ratchet is a library; its CLI exists to run --selfcheck.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
