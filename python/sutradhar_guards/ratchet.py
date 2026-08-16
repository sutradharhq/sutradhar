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
"""
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Mapping


class RatchetError(AssertionError):
    """Raised when a ratchet check fails. Subclasses AssertionError so it
    reads naturally in pytest output."""


class Ratchet:
    def __init__(self, baseline_path: str | Path, name: str = ""):
        self.path = Path(baseline_path)
        self.name = name or self.path.stem

    # ── key mode: violations are identifiers (file:line, route names, ...) ──

    def assert_only_shrinks(
        self, current: Iterable[str], update: bool | None = None
    ) -> None:
        """Fail on any violation not in the baseline, and on any baseline
        entry that is no longer a violation (stale - must be removed)."""
        cur = sorted(set(str(v) for v in current))
        if self._updating(update):
            self._write(cur)
            return
        base = set(self._read_list())
        new = [v for v in cur if v not in base]
        stale = [v for v in sorted(base) if v not in cur]
        self._raise_if_needed(new, stale)

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
        listed.assert_only_shrinks(["x.py:1", "y.py:2"], update=True)

        try:
            listed.assert_only_shrinks(["x.py:1", "y.py:2"])
        except RatchetError as exc:
            _fail(f"an unchanged violation set was rejected: {exc}")

        try:
            listed.assert_only_shrinks(["x.py:1", "y.py:2", "z.py:9"])
            _fail("a NEW violation was accepted")
        except RatchetError:
            pass

        try:
            listed.assert_only_shrinks(["x.py:1"])
            _fail("a STALE baseline entry passed instead of demanding removal")
        except RatchetError:
            pass

    if ok:
        print(
            "[ratchet] selfcheck ok: growth refused, new entry refused, unbanked "
            "shrink refused, stale entry refused, vacuous detector refused"
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
