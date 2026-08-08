# Round 1 - 2026-08-08

Lenses: test quality, docs-vs-code honesty, self-application

**What this round was.** Not an adversarial depth sweep - the v0.3 build
pass that shipped `verify_guard` and `budget`. It is recorded as round 1
because it produced real findings against real code, and because a flight
recorder with a fabricated history would be the exact defect doctrine 5.2
names. Every finding below actually happened; none are illustrative.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R1-1 | high | 6.4 | verify-guard selfcheck | fixed | docs-only commit reported DECORATION: prose counted as production code, so a good guard was falsely accused |
| R1-2 | med | 6.4 | dogfood on a real commit | fixed | guard-collision warning matched bare substrings; golden.py flagged against test_claim_check_golden.py |
| R1-3 | high | 2.2 | mutation testing | fixed | budget parser strictness had NO selfcheck; blinding its refusal branch passed every other planted case |
| R1-4 | med | 2.4 | mutation testing | fixed | budget selfcheck crashed instead of returning False, answering with a traceback rather than a verdict |
| R1-5 | med | 2.1 | full-suite run | fixed | __init__ export shadowed the budget submodule; file passed alone, five tests failed in the suite |
| R1-6 | low | 2.2 | rounds selfcheck | fixed | round-heading regex lacked re.MULTILINE, so no record was ever parsed |
| R1-7 | med | 2.2 | design review | deferred | verify_guard mechanises only the revert half of 2.2; weaken-the-seam mutation mode not implemented |
| R1-8 | med | 1.1 | design review | deferred | budget enforcement detection is a text match: proves a test mentions the budget, not that its assertion bites |
| R1-9 | low | 1.1 | design review | deferred | budget latency check is a single-sample ceiling, not a percentile; needs a samples=N runner |

## Corrected premises

These matter more than the fixes (robustness-loop phase 6):

- **"The selfcheck passing means the tool works."** It does not. Three of
  four blinding experiments went red on the budget parser and the fourth
  passed - the selfcheck had a hole exactly where nobody had looked. A
  selfcheck is a guard, and guards are decoration until shown to fail.
- **"A false positive is a minor bug."** For a tool whose whole job is
  accusation, it is the worst class: a net that cries wolf gets muted, and
  a muted net is worse than none. R1-1 and R1-2 are the same defect twice.
- **"Measuring a mutation is trivial."** The first mutation run reported
  EXIT=0 for three mutations that had genuinely failed, because the harness
  piped through `| tail` and read tail's exit code. Doctrine 6.3, inside
  the pass that was mechanising doctrine 2.2.

## Harness gotchas

- The local `python3` is 3.9 (Xcode's), so 3.9 compatibility is exercised
  by default here and NOT independently verified. CI covers it properly.
- `verify_guard` on a commit that adds a whole module reports
  `VERIFIED (weak)`: reverting deletes the import target, so the guard
  fails to load rather than failing to assert. Correct, and worth
  remembering before reading a weak verdict as a problem.
