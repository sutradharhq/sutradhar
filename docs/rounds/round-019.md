# Round 19 - 2026-09-07

Lenses: our own shipped surface, the vocabulary a framework speaks, entry gating

**What this round was.** Round 18 found the framework speaking one adopter's
business - kilowatt-hours beside rupees inside `claim_check.py`, a
"regulator-facing document" in its docstring, a meter-billing worked example -
while `framework_only.py` reported green throughout, because every one of
those files imported the standard library only and declared no dependency.
That finding, R18-5, was made **by hand**. This round is the mechanism for it,
and the honest half of the round is that the mechanism does not cover the
finding that produced it. It covers the part that can be checked from inside
the repository, says so in as many words, and names the part that cannot.

Nothing else changed. No doctrine rule was added or renumbered; the preamble
gained one sentence describing what the new gate holds.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R19-1 | med | 8.1 | building the mechanism R18-5 asked for | fixed | `framework_only.py` gates "a framework, not a product" on an import list and the absence of a manifest, and neither can see a framework that has started speaking an adopter's business. Shipped as `framework_shape.py`: a numeric literal immediately followed by a **domain unit** (kilowatt-hours, barrels, tonnes, acres, patients, beds, lakh/crore - 65 units across 8 industries, deliberately not energy-only) or a **currency symbol**, anywhere in what ships or teaches, against a baseline in which **every banked entry carries a written reason and a row without one is refused**. There is no `--update-baseline`: banking here is the act of writing the sentence. `docs/rounds/` and `CHANGELOG.md` are exempt, which is the difference between a record and a leak. Wired into CI (selfcheck on 3.12 and 3.9, plus a real run over this repository), into `bootstrap.sh`, and into the pre-commit hook in `--diff` mode so an agent's commit is gated at entry |
| R19-2 | med | 2.9 | stating the new gate's reach before trusting it | closed | the shipped gate **cannot find an ordinary business noun**, and nothing self-contained can: no property of this repository separates `device` (fine) from `meter` (the leak R18-5 actually found, 12 occurrences here and 3,688 in the private tree). The signal exists only relative to a corpus the public repository does not have. So `framework_shape.py` is a **floor and not a proof**, it says that on every green run, and the corpus-relative check that can see the noun ships as `--against <corpus>` - a maintainer's report, run locally, never in CI, printing a ranked list for a person rather than a verdict. Recorded as a finding rather than a caveat because a gate whose limit is only in a docstring is a gate somebody will read as complete |
| R19-3 | low | 6.11 | the guard's own mutation run | fixed | the new guard's selfcheck indexed `flat[0]` and `found[0]` before checking either list was non-empty, so the mutant that blinds the detector - `scan_text` returning `[]`, the exact vacuity the selfcheck exists to catch - killed the instrument with an `IndexError` instead of producing a red verdict, and took every later case in the run with it. Found by writing the blinded-detector test, not by reading. Second occurrence of 6.11 in two rounds, on the first guard written since round 18 filed the same shape against `ci_step_lint`; shapes are validated before they are indexed now |

## R19-1: the gate that was measured and rejected first

The obvious mechanism is a **vocabulary ratchet**: bank the framework's
current word set, fail on any new word. It was measured before it was
rejected. New words per commit in the framework surface, over the last twelve
commits:

```
6  10  13  18  18  25  37  47  57  64  71  10
```

A gate demanding roughly twenty banked words per commit is a gate whose
correct answer, every single time, is `--update-baseline` - which is the
reflex R18-1 was filed to remove from ratchet keys, reintroduced one layer up
and with a bigger blast radius, because a bulk re-bank of a word list buries a
real leak among sixty legitimate nouns. It is not built, and the numbers are
here so the next session does not re-derive them.

**Domain-unit literals are the part that can ship.** They were 14 in the
surface before the round-18 scrub and 7 after, and the ones the scrub removed
were exactly the leaked material (`1,240 kWh` in the example app and its
README, `980 kWh`). Low volume, high signal, and a judgement per entry that a
person can actually make. That is the whole design: a check whose findings are
few enough to read is a check whose baseline can carry a reason per row.

Two smaller measurements shaped the detector rather than being argued about:

- **`$` on its own is not a currency signal.** 427 hits in the surface, and
  nearly all of them are `$?`, `$HOME` and `$1` in shell. `$` counts only
  immediately before a number of at least two characters, which separates a
  grouped or decimal amount from `$1`..`$9`. The price is that a one-digit
  amount is missed; the guard's docstring says so, and this is what "floor"
  means in practice.
- **The engineering allowlist is written down, not inferred.** 84 units the
  framework measures *itself* in - milliseconds, bytes, rows, requests. A
  detector defined as "everything not on the other list" grows silently every
  time somebody adds a word; the selfcheck asserts the two lists are disjoint
  and that every unit on each side lands on the side it is declared on.

## R19-2: what this gate does not cover, stated rather than implied

The shipped check is a floor. Specifically, it does not see:

- **an ordinary business noun.** `meter`, `feeder`, `tariff`, `claimant`,
  `policyholder` - no numeric literal, no unit, nothing mechanical to count.
  This is the class R18-5 found and the class the shipped gate misses.
- **a domain unit spelled out in words** (`one thousand two hundred
  kilowatt-hours`), or a number and its unit separated by more than one space
  or a line break.
- **anything outside the declared surface.** `agent/`, `ci/`,
  `CONTRIBUTING.md`, `NOTICE` and `CITATION.cff` are not scanned today. That
  is a scope decision, not an oversight, and widening a gate's reach should be
  a diff somebody makes on purpose.
- **a second occurrence of an already-banked term in an already-banked file.**
  The key is `path::term`, so a file banked for demonstrating crore parsing may
  gain another crore example without a new finding. That is the granularity
  the subject wants - the identity of a leak is "this file speaks this term" -
  and it is a hole in exactly one direction, named here.
- **a currency amount under `$10`,** per the measurement above.
- **a deliberate evasion.** The guard's own currency table is written as
  `₹`-style escapes so the detector does not trip over itself, which
  means the same trick would hide a symbol from it. The threat model is drift,
  not an adversary; a repository whose maintainer is smuggling their adopter's
  domain past their own gate has a different problem.

`--against <corpus>` is the answer to the first of those and only the first.
It is not in CI, it produces no verdict, and its output says both things on
every run.

## Calibration of `--against`, since a report nobody has watched work is prose

Run against this repository's own `examples/` tree - the only corpus that
exists here, and deliberately not pointed anywhere outside the repository:

```
python3 python/sutradhar_guards/framework_shape.py . --against examples
```

It ranks `billing` (16 occurrences there, rank 7), `readings` (15, rank 11),
`store` (13, 14), `device` (11, 19), `device_id` (9, 26), `subtotal` (9, 27)
and `discount` (8, 34) - the worked example's
distinctive nouns, which is the shape R18-5 used to find `meter`. Because the
corpus is inside the surface being checked, the output says so itself and
labels the run a calibration rather than a leak report; every term is
trivially "present here" when the corpus is part of "here".

## Mutation verification (2.2)

Every claim was shown able to fail before it was trusted. Each mutant was
applied by editing the file, running the named command, and restoring from a
backup taken first.

| mutant | result |
|---|---|
| `1,240 kWh` planted in `docs/adoption.md` (a surface file) | **red**, `framework_shape.py .` exit 1, naming `docs/adoption.md:83: '1,240 kWh'` |
| the same string planted in `docs/rounds/round-019.md` | **green**, exit 0 - the exemption is real and not a comment |
| `scan_text` monkeypatched to return `[]` (the detector blinded) | **red** through the CLI on a tree it had just called clean; this is the mutant that found R19-3 |
| a baseline row with its reason emptied | **exit 2**, refused rather than passed - "could not measure" is not "did not fail" |
| `docs/rounds` removed from `EXEMPT` | **red**, and the round record above becomes a finding, which is the whole argument for the exemption |
| an engineering unit moved into `_DOMAIN_UNITS` | **red** in the selfcheck's disjointness case before any file is read |
| the pre-commit hook, driven with a real `PreToolUse` payload over a staged file carrying a planted domain literal | `permissionDecision: deny`, naming `framework_shape`; with the literal removed, allowed |

## Measured, not estimated

| Number | Before | After |
|---|---|---|
| tests | 550 | **749** |
| guard modules | 16 | **17** |
| guard programs bundled in the plugin | 8 | **9** |
| files in the framework surface this gate reads | - | **108** |
| declared domain units / industries | - | **65 / 8** |
| declared engineering units | - | **84** |
| banked baseline entries, every one with a reason | - | **10** |

## The backflow register is still red, and this round did not answer it

Recording round 19 leaves **B-13**, **B-16**, **B-20** and **B-21** overdue and
undecided, exactly as round 18 left them, and adds **B-22**, **B-24**, **B-25**
and **B-26** to the overdue set, all carrying round 19.

```
python3 python/sutradhar_guards/rounds.py docs/rounds/ --backflow docs/backflow.md
```

still exits 1. **That is the mechanism working and it is left failing on
purpose.** This round built one guard; it did not build the Playwright port,
the file-ownership manifest, the `%`-format detector, the operating drill, the
rows-per-run check, the fan-out cap or the deployment-version surface. Moving
eight deadlines to make a gate go green is the R15-4 shape that rounds 16 and
18 both refused, and no row in the register was touched by this round.

## What was ruled out (7.4)

- **The general vocabulary ratchet.** Measured and rejected; the per-commit
  numbers are above so nobody re-derives them.
- **`--update-baseline` on this guard.** The reason column is the decision,
  and a flag that banks a finding without one would make the baseline an
  ignore-list. Banking is done by hand, by editing the JSON.
- **Running `framework_shape` uncommented in `ci/guards.yml`.** That template
  goes into an adopter's repository, and an adopter building a *product* is
  supposed to speak their own business domain: the gate would be red on their
  first push, which is precisely how a correct guard gets muted (R14-2). It
  ships commented, with the "only if what you ship is a framework" condition
  above it.
- **Widening the surface to `agent/` and `ci/`.** Both teach, and both are a
  real gap (R19-2). Not widened in the same round that introduced the gate,
  because a scope change should be its own visible diff rather than a rider on
  a new mechanism.
- **Adding `framework_shape` to the MCP tool table.** The commit gate and CI
  are the two placements that do not depend on anyone remembering; a third
  that does is not what this finding was about.
- **A design note for the new guard.** `docs/design/scope-framework-only.md`
  already states the boundary this holds, and it now names both gates. A
  second note declaring no budget would add a file and no constraint.
- **Adding `framework_shape` to `test_stable_keys.py`'s detector table.** Its
  keys are `path::<matched text>`, and the matched text legitimately begins
  with a digit (`a.md::1,240 kwh`); that table's `:\d+` heuristic would call
  the term a position. The invariant is asserted directly in
  `test_framework_shape.py` instead, behaviourally, by shifting the fixture.
- **Exempting `docs/backflow.md`.** It is a register of items, not a record of
  removals, and nothing in it trips the gate today. If a future item needs to
  quote a domain literal, that is the round to decide it.

## Guards touched

`framework_shape.py` (new), `plugin/scripts/precommit_gate.py` and
`plugin/sync_guards.py` (the ninth bundled guard),
`.github/workflows/selftest.yml`, `ci/guards.yml`, `bootstrap.sh`,
`README.md`, `python/README.md`, `DOCTRINE.md` (one preamble sentence, no rule
added or renumbered) and `docs/design/agent-loop-hooks.md`.

550 tests before, 749 after.
