"""budget - mechanise doctrine 1.1: state your cardinalities before building.

Doctrine 1.1 is, by our own README's account, the cheapest rule in the
framework and the one whose absence cost us the most. Until now it shipped
as a markdown table nothing read.

*Scar: an unbounded fleet sweep worked perfectly at demo scale (50 entities)
and OOM-crashed the datastore at 200,000. The design-time sentence - "this
must survive 200,000 meters" - would have cost nothing to write. Finding out
instead cost a full scale pass and seventeen store crashes.*

The gate here is deliberately NOT "did you write a design note". That is
bureaucracy: it is guessable, gameable, and it measures paperwork. The gate
is the second, harder question:

    **Is every number you declared actually enforced by a test?**

A budget declared and never enforced is decoration - the same disease as a
guard that has never been shown to fail. So this module does two things.

**1. The test reads its N from the design note.**

    ---
    sutradhar_budget: fleet-sweep
    n: 200000
    p95_ms: 800
    memory_mb: 512
    ---

    def test_fleet_sweep_at_design_scale():
        with budget("fleet-sweep") as b:
            sweep(synth_meters(b.n))      # b.n IS the declared 200,000

Nobody hand-picks a comfortable N. Raising the design figure automatically
makes the test harder; lowering it is a visible diff in the design note,
which is exactly where that argument belongs.

**2. A declared budget with no test is a build failure.**

    python budget.py docs/design/ --tests tests/

Honest limits, stated plainly:

  - `memory_mb` is measured with `tracemalloc`, which counts PYTHON heap
    allocations, not process RSS. It will not see memory held by a C
    extension, the interpreter itself, or your database driver's buffers.
    It is a good proxy for "this data structure got too big" and a bad one
    for "the container OOMed"; the drill remains the authority on RSS.
  - The latency check is a CEILING on the runs you actually performed, not
    a percentile estimate. `p95_ms` records design intent; a single-sample
    run that exceeds it fails. Declare `ci_slack` for shared runners rather
    than quietly widening the number, so the looseness stays in the diff.
  - Enforcement is detected by finding the budget's id quoted in a test
    file. That is a text match: it proves a test MENTIONS the budget, not
    that the assertion is meaningful. Pair it with `verify_guard.py` on the
    commit that introduces the budget if you want the stronger claim.
"""
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
from __future__ import annotations

import os
import re
import sys
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path

MARKER = "sutradhar_budget"

# Flat scalars only. A design note is a contract, so the parser REFUSES
# what it does not understand rather than guessing a meaning for it - a
# silently misparsed budget is worse than no budget at all.
_SCALAR = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")
_NUMERIC_FIELDS = ("n", "rps", "p95_ms", "memory_mb", "ci_slack")


class BudgetError(AssertionError):
    pass


@dataclass
class Budget:
    id: str
    source: str = ""
    n: int | None = None
    n_unit: str = ""
    rps: float | None = None
    p95_ms: float | None = None
    memory_mb: float | None = None
    ci_slack: float = 1.0

    def declared(self) -> list[str]:
        out = []
        if self.n is not None:
            out.append(f"n={self.n:,}{(' ' + self.n_unit) if self.n_unit else ''}")
        if self.rps is not None:
            out.append(f"rps={self.rps:g}")
        if self.p95_ms is not None:
            out.append(f"p95<={self.p95_ms:g}ms")
        if self.memory_mb is not None:
            out.append(f"mem<={self.memory_mb:g}MB")
        return out


# ── parsing ─────────────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> dict | None:
    """Parse a leading `---` fenced block of flat `key: value` pairs.

    Returns None when the document has no frontmatter. Raises BudgetError
    on a block it cannot parse strictly - doctrine 2.4, a failure states
    itself rather than degrading into a partial dict."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise BudgetError("frontmatter opened with '---' but never closed")

    out: dict[str, str] = {}
    for lineno, raw in enumerate(lines[1:end], start=2):
        line = raw.split("#", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        match = _SCALAR.match(line.strip())
        if not match:
            raise BudgetError(
                f"line {lineno}: cannot parse {line.strip()!r}. Design-note "
                f"frontmatter takes flat `key: value` scalars only - no lists, "
                f"no nesting. A budget the parser has to guess at is not a budget."
            )
        key, value = match.group(1), match.group(2).strip().strip('"').strip("'")
        if key in out:
            raise BudgetError(f"line {lineno}: {key!r} declared twice")
        out[key] = value
    return out


def budget_from_frontmatter(data: dict, source: str = "") -> Budget:
    ident = data.get(MARKER, "").strip()
    if not ident:
        raise BudgetError(f"{source}: no `{MARKER}: <id>` in the frontmatter")

    kwargs: dict = {"id": ident, "source": source, "n_unit": data.get("n_unit", "")}
    for field in _NUMERIC_FIELDS:
        if field not in data:
            continue
        raw = data[field].replace(",", "").replace("_", "")
        try:
            kwargs[field] = int(raw) if field == "n" else float(raw)
        except ValueError:
            raise BudgetError(
                f"{source}: {field}={data[field]!r} is not a number. "
                f'"lots of rows" is not a cardinality (doctrine 1.1).'
            )
    b = Budget(**kwargs)
    if not b.declared():
        raise BudgetError(
            f"{source}: budget {ident!r} declares no numbers. A design note "
            f"with an empty envelope is the paperwork without the discipline; "
            f"name at least one of n / rps / p95_ms / memory_mb."
        )
    if b.ci_slack < 1.0:
        raise BudgetError(f"{source}: ci_slack={b.ci_slack} must be >= 1.0")
    return b


def load_budgets(root: str | Path) -> dict[str, Budget]:
    """Every design note under `root` that declares a budget, by id."""
    found: dict[str, Budget] = {}
    root = Path(root)
    files = [root] if root.is_file() else sorted(root.rglob("*.md"))
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        if MARKER not in text:
            continue
        data = parse_frontmatter(text)
        if not data or MARKER not in data:
            continue
        b = budget_from_frontmatter(data, source=str(path))
        if b.id in found:
            raise BudgetError(
                f"budget id {b.id!r} declared twice: {found[b.id].source} and "
                f"{b.source}. Ids are how tests find their numbers; a duplicate "
                f"means one of the two is silently unenforced."
            )
        found[b.id] = b
    return found


def _default_root() -> str:
    return os.environ.get("SUTRADHAR_DESIGN_NOTES", "docs/design")


# ── enforcement at test time ────────────────────────────────────────────────

def get_budget(ident: str, root: str | Path | None = None) -> Budget:
    budgets = load_budgets(root or _default_root())
    if ident not in budgets:
        known = ", ".join(sorted(budgets)) or "(none found)"
        raise BudgetError(
            f"no budget {ident!r} under {root or _default_root()}. Declared: {known}. "
            f"Write the design note first - that is the whole point of 1.1."
        )
    return budgets[ident]


class _BudgetRun:
    """Context manager that measures a run and asserts the declared envelope."""

    def __init__(self, b: Budget):
        self.budget = b
        self.elapsed_ms: float | None = None
        self.peak_mb: float | None = None
        self._t0 = 0.0
        self._owns_tracing = False

    # expose the declared numbers so the test body uses them
    @property
    def n(self) -> int:
        if self.budget.n is None:
            raise BudgetError(
                f"budget {self.budget.id!r} declares no `n`; this test asked for "
                f"one. Add it to {self.budget.source} or stop depending on it."
            )
        return self.budget.n

    @property
    def rps(self) -> float | None:
        return self.budget.rps

    def __enter__(self) -> "_BudgetRun":
        if self.budget.memory_mb is not None and not tracemalloc.is_tracing():
            tracemalloc.start()
            self._owns_tracing = True
        if self.budget.memory_mb is not None:
            tracemalloc.reset_peak()
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.elapsed_ms = (time.perf_counter() - self._t0) * 1000.0
        if self.budget.memory_mb is not None:
            _, peak = tracemalloc.get_traced_memory()
            self.peak_mb = peak / (1024 * 1024)
            if self._owns_tracing:
                tracemalloc.stop()
        if exc_type is not None:
            return False  # a real failure inside the block wins

        b, breaches = self.budget, []
        if b.p95_ms is not None:
            ceiling = b.p95_ms * b.ci_slack
            if self.elapsed_ms > ceiling:
                slack = f" (p95 {b.p95_ms:g}ms x ci_slack {b.ci_slack:g})" if b.ci_slack != 1 else ""
                breaches.append(
                    f"latency {self.elapsed_ms:.0f}ms > {ceiling:.0f}ms{slack}"
                )
        if b.memory_mb is not None and self.peak_mb is not None:
            ceiling = b.memory_mb * b.ci_slack
            if self.peak_mb > ceiling:
                breaches.append(
                    f"peak python heap {self.peak_mb:.1f}MB > {ceiling:.1f}MB"
                )
        if breaches:
            raise BudgetError(
                f"[budget:{b.id}] declared envelope exceeded at n={b.n:,}:\n  "
                + "\n  ".join(breaches)
                + f"\nDeclared in {b.source}. Either make it fit, or change the "
                  f"design note deliberately - raising the number in the note is "
                  f"an argument someone can see in review; widening it here is not."
            )
        return False


def budget(ident: str, root: str | Path | None = None) -> _BudgetRun:
    """Enforce a declared envelope around a block. See the module docstring."""
    return _BudgetRun(get_budget(ident, root))


# ── the gate: a declared budget with no test is decoration ──────────────────

def find_unenforced(budgets: dict[str, Budget], test_root: str | Path) -> list[str]:
    """Budget ids that no test file so much as mentions."""
    root = Path(test_root)
    haystack = []
    files = [root] if root.is_file() else root.rglob("*")
    for path in files:
        if path.is_file() and path.suffix in (".py", ".ts", ".js", ".tsx", ".mjs"):
            haystack.append(path.read_text(encoding="utf-8", errors="replace"))
    blob = "\n".join(haystack)
    return sorted(
        ident for ident in budgets
        if f'"{ident}"' not in blob and f"'{ident}'" not in blob
    )


# ── selfcheck ───────────────────────────────────────────────────────────────

def selfcheck() -> bool:
    """Plant a declared-but-unenforced budget and require the gate to catch
    it; plant an enforced one and require it to pass. A gate that cannot
    tell them apart would wave every unenforced number through."""
    try:
        return _selfcheck_body()
    except Exception as exc:  # noqa: BLE001
        # A selfcheck that dies is a selfcheck that failed. Reporting it as
        # a clean False beats a traceback: the caller gets an answer, not a
        # stack trace it has to interpret (doctrine 2.4).
        print(f"[budget] SELFCHECK FAILED: the selfcheck itself raised "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return False


def _selfcheck_body() -> bool:
    import tempfile

    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        design, tests = Path(tmp) / "design", Path(tmp) / "tests"
        design.mkdir(), tests.mkdir()
        (design / "swept.md").write_text(
            "---\nsutradhar_budget: planted-enforced\nn: 200000\n---\n# note\n"
        )
        (design / "orphan.md").write_text(
            "---\nsutradhar_budget: planted-unenforced\nn: 50\n---\n# note\n"
        )
        (tests / "test_x.py").write_text(
            'from sutradhar_guards.budget import budget\n'
            'def test_a():\n    with budget("planted-enforced") as b:\n        pass\n'
        )
        budgets = load_budgets(design)
        unenforced = find_unenforced(budgets, tests)
        if unenforced != ["planted-unenforced"]:
            print(f"[budget] SELFCHECK FAILED: expected ['planted-unenforced'], "
                  f"got {unenforced}", file=sys.stderr)
            ok = False

        # The envelope must actually bite.
        (design / "tiny.md").write_text(
            "---\nsutradhar_budget: planted-tight\nn: 10\np95_ms: 0.000001\n---\n"
        )
        try:
            with budget("planted-tight", root=design):
                time.sleep(0.005)
            print("[budget] SELFCHECK FAILED: a 5ms run passed a 1ns budget",
                  file=sys.stderr)
            ok = False
        except BudgetError:
            pass

        # ...and must not fire on a run that fits.
        (design / "loose.md").write_text(
            "---\nsutradhar_budget: planted-loose\nn: 10\np95_ms: 60000\n---\n"
        )
        try:
            with budget("planted-loose", root=design):
                pass
        except BudgetError as exc:
            print(f"[budget] SELFCHECK FAILED: a no-op broke a 60s budget: {exc}",
                  file=sys.stderr)
            ok = False

        # A note with no numbers is paperwork, and must be refused.
        try:
            budget_from_frontmatter({MARKER: "empty"}, source="<selfcheck>")
            print("[budget] SELFCHECK FAILED: an empty envelope was accepted",
                  file=sys.stderr)
            ok = False
        except BudgetError:
            pass

        # The parser is the contract surface, so its strictness is guarded
        # too. A parser that quietly skips what it cannot read turns a
        # malformed budget into "no budget declared" - an unenforced number
        # that reports as compliant. (Found by mutation: blinding the
        # refusal branch passed every other case in this selfcheck.)
        malformed = [
            ("nested structure", "---\nsutradhar_budget: x\nlimits:\n  - 5\n---\n"),
            ("unclosed frontmatter", "---\nsutradhar_budget: x\nn: 5\n"),
            ("duplicate key", "---\nsutradhar_budget: x\nn: 5\nn: 9\n---\n"),
            ("non-numeric cardinality", "---\nsutradhar_budget: x\nn: lots\n---\n"),
        ]
        for label, text in malformed:
            note = design / "malformed.md"
            note.write_text(text)
            try:
                load_budgets(note)
                print(f"[budget] SELFCHECK FAILED: parser accepted {label}",
                      file=sys.stderr)
                ok = False
            except BudgetError:
                pass
            note.unlink()
    return ok


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--selfcheck" in argv:
        return 0 if selfcheck() else 1

    design_root, test_root = None, "tests"
    positional: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--tests":
            test_root = argv[i + 1]; i += 2
        elif argv[i].startswith("--"):
            i += 1
        else:
            positional.append(argv[i]); i += 1
    design_root = positional[0] if positional else _default_root()

    if not selfcheck():
        return 1

    if not Path(design_root).exists():
        print(f"[budget] no design notes at {design_root} - nothing to check. "
              f"Point at your notes directory or set SUTRADHAR_DESIGN_NOTES.")
        return 0
    try:
        budgets = load_budgets(design_root)
    except BudgetError as exc:
        print(f"\n[budget] {exc}\n")
        return 1

    if not budgets:
        print(f"[budget] no budgets declared under {design_root}.")
        return 0

    unenforced = find_unenforced(budgets, test_root) if Path(test_root).exists() else sorted(budgets)
    if unenforced:
        print(f"\n[budget] {len(unenforced)} declared budget(s) that no test enforces:\n")
        for ident in unenforced:
            b = budgets[ident]
            print(f"  {ident}  ({', '.join(b.declared())})")
            print(f"    declared in {b.source}, enforced nowhere under {test_root}/")
        print(
            "\n  A number written down and never enforced is decoration: it "
            "reads\n  as a commitment and behaves like a wish. Add a test:\n\n"
            f'      with budget("{unenforced[0]}") as b:\n'
            "          ...run the thing at b.n...\n"
        )
        return 1

    total = ", ".join(f"{i} ({', '.join(b.declared())})" for i, b in sorted(budgets.items()))
    print(f"[budget] OK - {len(budgets)} budget(s), all enforced: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
