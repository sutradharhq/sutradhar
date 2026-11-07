---
sutradhar_scar: R22-1, R22-2, R24-2
sutradhar_budget: defect-corpus
n: 60
n_unit: corpus cases
p95_ms: 15000
memory_mb: 64
ci_slack: 2.0
---

# Design note: the defect corpus

<!-- Written after the mechanism ran: the numbers below are measured on a
     60-case synthetic corpus on this machine, not chosen first. -->

## What and why

The framework's improvement loop needs a scorer that cannot be gamed by
deleting cases or by counting its own loop iterations. `corpus.py` scores
defective/clean twin pairs through the real guard invocations, takes its
denominator from the manifest set on disk, holds that total against a
declared `case_count.json` (R24-2: a disk-derived denominator alone let a
deleted case print "51 of 51" and pass), and holds a per-rule coverage
floor with a shrink-only reason bank. The weekly proposer round reads it
before writing any guard.

## Cardinalities and budgets  <!-- doctrine 1.1 -->

| Dimension | Design N | Enforced by |
|---|---|---|
| synthetic swallow_lint twin pairs in one scored run | 60 | `test_defect_corpus_holds_its_declared_envelope` |
| wall clock for that synthetic run | 15,000 ms (x2 CI slack) | same |
| peak Python heap of the scorer | 64 MB (x2 CI slack) | same |

**Provenance of these numbers** (doctrine 5.1): the ceilings are chosen
from a measured baseline, not the other way round. Sixty synthetic
swallow_lint twin pairs - the cheapest guard in the registry, two
subprocess runs per case plus the selfcheck-before-scan the house pattern
requires - took 4,458 ms wall clock and 0.35 MB of peak parent heap on a
2026 laptop. The wall-clock ceiling is ~3x that baseline so a shared CI
runner and the slower guards (rounds, verify_guard, each running their
own selfcheck first) do not flake; the memory ceiling is deliberately
loose because its job is a tripwire for parent-side accumulation - the
twin outputs must stream through the scorer, never collect in it.

60 is the design N because it is the committed backfill (50+ cases plus
headroom). Raise it here - deliberately, in a diff someone reviews - and
the budget test gets harder automatically, because it reads its N from
this note.

**What this envelope does not bind** (6.10, R22-9). The budget measures a
synthetic corpus built from the cheapest guard, not the corpus CI runs.
The real one mixes every guard, and the slow ones (verify_guard building
git history, rounds running its own selfcheck) dominate: 53 real cases
took 24.4 s wall clock on the same laptop on 2026-09-23, against 4.5 s
for 60 synthetic ones. Nothing but the CI job's ten-minute timeout bounds
the real run today. That is recorded as a deferred finding rather than
hidden behind a synthetic number that reads like the real one.

## Failure story  <!-- doctrine 1.4 -->

| Dependency | Down | Slow | Partial |
|---|---|---|---|
| a guard binary (missing interpreter, missing git for two_commit) | twin run exits 124/125, verdict INVALID, run exits 2 - never a catch, never a pass | per-twin timeout at 120 s, then INVALID | n/a - a twin either ran or it did not |
| the archive flags (--rounds/--backflow/--doctrine) | paths missing: validation skipped WITH a printed line, never silently; scars still need citing, rules still need shape | n/a | R ids resolve against rounds, B ids against backflow, independently |
| the coverage floor files | missing EXCLUSIONS.md reads as no exclusions; missing uncovered.json reads as an empty floor, so uncovered rules fail loudly with the sentence to write | n/a | a floor entry that gained a case fails until removed |

## Illegal states  <!-- doctrine 1.2 -->

A manifest cannot name a command: the frontmatter key set is fixed, the
registry owns every argv and every runner, and an unknown key or guard is
a load refusal. That is the seam that keeps a case file from becoming a
script someone reviews as prose and executes as code.

## Guards shipping with this

- [x] `test_defect_corpus_holds_its_declared_envelope` (enforces all three numbers)
- [x] the twelve `test_corpus.py` verdict tests, each docstring naming its mutation
- [x] `corpus.py --selfcheck` (the CAUGHT/MISSED/FALSE_POSITIVE pair plus the CLI pair)
- [x] the reachability ratchet covers the new module automatically (class, not point)

## What this note deliberately does not cover

`corpus.py` does not join the bootstrap copy set in v1: a tool that only
ever exits 2 in a tree with no cases would teach adopters that a red gate
is normal. It joins the copy set in the release after the skill teaches
adopters to write cases. The proposer skill, the CI step, and the README
row land with phase 4, not here.
