"""Golden gate - frozen numeric truth with declared tolerance and a
re-baseline paper trail.

Doctrine 2.5: freeze numeric truth. Anything numeric that matters (a
scoring pipeline, a forecast, a fee computation) gets a frozen golden
dataset; the gate recomputes and compares within the tolerance THE FILE
ITSELF declares. Re-baselining is deliberate: it requires an explicit
reason, which is recorded in the file and therefore in the diff, so "the
numbers changed and someone re-recorded them" can never happen silently.

The golden file:

    {
      "tolerance_rel": 0.001,
      "reason": "initial baseline from v1 scoring pipeline",
      "data": { "feeder_7": {"loss_pct": 12.41, "rank": 3}, ... }
    }

Usage in a test:

    from sutradhar_guards.golden import GoldenGate

    def test_scoring_matches_golden():
        computed = score_all(FROZEN_INPUT)     # deterministic input!
        GoldenGate("tests/golden/scores_v1.json").check(computed)

Re-baseline (same commit as the intentional change, reason in the file
AND the commit message):

    GOLDEN_UPDATE=1 GOLDEN_REASON="re-tuned weights per ADR-12" pytest ...
"""
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
from __future__ import annotations

import json
import math
import os
from pathlib import Path


class GoldenError(AssertionError):
    pass


class GoldenGate:
    def __init__(self, path: str | Path, tolerance_rel: float = 0.001):
        self.path = Path(path)
        self.default_tol = tolerance_rel

    def check(self, computed, update: bool | None = None) -> None:
        if self._updating(update):
            reason = os.environ.get("GOLDEN_REASON", "").strip()
            if not reason:
                raise GoldenError(
                    f"[golden:{self.path.name}] re-baselining requires "
                    f"GOLDEN_REASON=\"why the numbers legitimately changed\" - "
                    f"an unreasoned re-baseline is how a golden file stops "
                    f"meaning anything."
                )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(
                {"tolerance_rel": self.default_tol, "reason": reason, "data": computed},
                indent=2, sort_keys=True,
            ) + "\n")
            return

        if not self.path.exists():
            raise GoldenError(
                f"[golden:{self.path.name}] no golden file at {self.path} - "
                f"record one deliberately:\n"
                f'  GOLDEN_UPDATE=1 GOLDEN_REASON="initial baseline" pytest ...'
            )
        frozen = json.loads(self.path.read_text())
        tol = float(frozen.get("tolerance_rel", self.default_tol))
        diffs: list[str] = []
        self._compare("", frozen["data"], computed, tol, diffs)
        if diffs:
            raise GoldenError(
                f"[golden:{self.path.name}] {len(diffs)} value(s) outside the "
                f"declared tolerance ({tol}):\n  " + "\n  ".join(diffs[:40])
                + (f"\n  ... and {len(diffs) - 40} more" if len(diffs) > 40 else "")
                + "\nIf the change is INTENTIONAL, re-baseline in the same "
                  "commit with GOLDEN_UPDATE=1 GOLDEN_REASON=\"...\"."
            )

    # ── internals ───────────────────────────────────────────────────────────

    @staticmethod
    def _updating(update: bool | None) -> bool:
        if update is not None:
            return update
        return os.environ.get("GOLDEN_UPDATE", "").lower() in ("1", "true", "yes")

    def _compare(self, key: str, want, got, tol: float, diffs: list[str]) -> None:
        if isinstance(want, dict):
            if not isinstance(got, dict):
                diffs.append(f"{key or '<root>'}: expected object, got {type(got).__name__}")
                return
            for k in want:
                if k not in got:
                    diffs.append(f"{key}.{k}: missing from computed output")
                else:
                    self._compare(f"{key}.{k}" if key else k, want[k], got[k], tol, diffs)
            for k in got:
                if k not in want:
                    diffs.append(f"{key}.{k}: NEW key not in golden (re-baseline if intended)")
        elif isinstance(want, list):
            if not isinstance(got, list) or len(got) != len(want):
                diffs.append(
                    f"{key}: length {len(got) if isinstance(got, list) else '?'} != golden {len(want)}"
                )
                return
            for i, (w, g) in enumerate(zip(want, got)):
                self._compare(f"{key}[{i}]", w, g, tol, diffs)
        elif isinstance(want, (int, float)) and not isinstance(want, bool):
            if not isinstance(got, (int, float)) or isinstance(got, bool):
                diffs.append(f"{key}: expected number {want}, got {got!r}")
            elif not _close(float(want), float(got), tol):
                diffs.append(f"{key}: {got} vs golden {want}")
        else:
            if want != got:
                diffs.append(f"{key}: {got!r} vs golden {want!r}")


def _close(want: float, got: float, tol: float) -> bool:
    if math.isnan(want) or math.isnan(got):
        return False  # NaN never silently matches
    if want == 0:
        return abs(got) <= tol
    return abs(got - want) / abs(want) <= tol


def selfcheck() -> bool:
    """Exercise the four behaviours a golden gate is worthless without.

    The unreasoned-re-baseline refusal is the load-bearing one. A gate that
    lets `GOLDEN_UPDATE=1` overwrite the baseline without stating why turns
    every future mismatch into a shrug and a re-record.
    """
    import tempfile

    ok = True

    def _fail(msg: str) -> None:
        nonlocal ok
        print(f"[golden] SELFCHECK FAILED: {msg}")
        ok = False

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "baseline.json"
        gate = GoldenGate(path, tolerance_rel=0.01)

        try:
            gate.check({"loss": 1.0}, update=False)
            _fail("a missing golden file passed instead of refusing")
        except GoldenError:
            pass

        os.environ.pop("GOLDEN_REASON", None)
        try:
            gate.check({"loss": 1.0}, update=True)
            _fail("re-baselined with no GOLDEN_REASON")
        except GoldenError:
            pass

        os.environ["GOLDEN_REASON"] = "initial baseline for selfcheck"
        try:
            gate.check({"loss": 1.0, "name": "run-a"}, update=True)
        except GoldenError as exc:
            _fail(f"reasoned re-baseline refused: {exc}")
        os.environ.pop("GOLDEN_REASON", None)

        try:
            gate.check({"loss": 1.005, "name": "run-a"}, update=False)
        except GoldenError as exc:
            _fail(f"a value inside tolerance was rejected: {exc}")

        try:
            gate.check({"loss": 1.5, "name": "run-a"}, update=False)
            _fail("a value outside tolerance passed")
        except GoldenError:
            pass

        try:
            gate.check({"loss": 1.0, "name": "run-a", "extra": 1}, update=False)
            _fail("a NEW key not present in the golden file passed")
        except GoldenError:
            pass

    if not _close(0.0, 0.0, 0.001):
        _fail("zero vs zero reported as a difference")
    if _close(float("nan"), float("nan"), 1e9):
        _fail("NaN silently matched NaN - a golden file full of NaN would pass")

    if ok:
        print(
            "[golden] selfcheck ok: missing file refused, unreasoned re-baseline "
            "refused, tolerance honoured, new key caught, NaN never matches"
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
        f"[golden] unknown argument(s): {' '.join(argv)}\n"
        f"golden is a library; its CLI exists to run --selfcheck.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
