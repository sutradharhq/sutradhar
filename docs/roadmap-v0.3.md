# v0.3 roadmap - move rules from memory to mechanism

v0.1 wrote down what the build record taught us. v0.2 made the guards guard
themselves. v0.3 has one theme:

> **Every rule that lives only in prose is a rule that gets dropped under
> deadline pressure. A rule that lives in a command survives.**

The doctrine's own 8.1 says a rule enters with the incident that paid for
it. The corollary this release acts on: a rule that cannot be checked
mechanically will decay to ceremony no matter how well it is written, and
the honest move is either to give it a mechanism or to mark it as
judgement-only.

Where the framework stood at v0.2, by rule:

| Rule | Mechanised at v0.2? |
|---|---|
| 2.7 no silent swallows | yes - `swallow_lint.py` |
| 2.8 no query interpolation | yes - `interpolation_lint.py` |
| 2.1 guard in the same commit | partly - ratchet library, no gate |
| 2.5 numeric truth | yes - `golden.py` |
| 3.1 asserted effects | yes - `expectEffect` |
| 3.2 route baseline | yes - route sweep |
| 4.1 grounded numbers | yes - `claim_check.py` |
| **2.2 guards shown to fail** | **no - honour system** |
| **1.1 cardinalities and budgets** | **no - a fillable template** |
| **8.1 / 8.3 evidence and stop rules** | **no - hand-counted, once** |

The three in bold are the highest-consequence unmechanised rules in the
framework, and 1.1 is the one the README already calls "the cheapest rule
in the framework and the one whose absence cost us the most".

## Shipped

### 1. `verify_guard.py` - doctrine 2.2 becomes a command

Reverts the production half of a fix commit in a throwaway worktree, keeps
the tests, and requires the guard to go red. Tri-state exit code so
"inconclusive" is never reported as a pass. See
[backend.md](backend.md#step-3-is-a-command-not-a-habit).

Chosen first because it is the largest consequence-to-effort ratio in the
table: the tested-but-half-dead fix cost a week, and the experiment that
would have caught it takes a worktree and two test runs.

### 2. `budget.py` - doctrine 1.1 becomes a gate

The cardinality table is now machine-readable frontmatter, the test reads
its N from the design note instead of picking a comfortable one, and the
CLI fails on any declared number no test enforces.

One design decision worth recording, because the obvious version is worse:
the gate is **not** "does this feature have a design note". That is
guessable, gameable, and it measures paperwork - you cannot mechanically
decide what counts as a "feature", and any rule that tries will be either
noisy or trivially satisfied by an empty file. The gate is the second,
harder question: *is every number you declared actually enforced?* A budget
written down and never enforced is decoration - the same disease as a guard
that has never been shown to fail, and the same fix.

Deferred within this item: a percentile mode. The envelope check is a
CEILING on the runs performed, not a percentile estimate; `p95_ms` records
design intent and a single sample over it fails. Real percentiles need a
`samples=N` runner, which is worth having and is not worth blocking the
gate on.

### 3. `rounds.py` - the flight recorder

Doctrine 8.1 (which rules earn their keep) and 8.3 (when to stop) both ask
questions that need a history nobody was keeping. This reads the round
records the robustness-loop skill already asks for and computes: the stop
rule, the residual register, and rule attribution.

Two design decisions worth recording:

**It refuses more than it reports.** The stop rule will not answer on fewer
than two rounds; attribution will not name deletion candidates on fewer than
five. A reporter that always produces a confident answer would be actively
harmful here, because 8.1 would then delete rules on the strength of a quiet
week. The refusals are the load-bearing behaviour and they are what the
selfcheck guards hardest.

**Findings are RECORDED, floors are MEASURED, and the report says so.** A
logbook has a logbook's biases - a round that found nothing because nobody
looked produces the same row as a round that found nothing because there was
nothing to find. Baseline totals have no judgement in the loop. Presenting
them as one number would be exactly the provenance failure 5.1 names.

Deferred within this item: effort per round (the denominator the 8.3 stop
rule really wants - findings per engineer-hour, not per round). It needs an
effort figure nobody currently records, and inventing one would be worse
than the round count.

### 4. `examples/` - a worked repo with planted defects

Seven planted defects in an app whose test suite is green, and a runner that
surfaces all seven in ten seconds with no install.

The design decision that makes it work: **the app's own tests pass.** An
example where the tests fail teaches nothing - it just looks like a broken
build. The whole point is the gap between a green suite and a correct
system, so the suite has to be green.

Two things excluded on purpose, with the reason stated in the example's own
README rather than quietly: the frontend guards (Cypress, npm and a browser
would turn a ten-second demo into a five-minute install) and the operational
drills (they need a stack and a few hours, which is the honest limit of a
shell-script demo, and rather the point of the ops-drill skill).

The example is under guard itself - the runner exits nonzero on a missed
defect and CI runs it - because a walkthrough that has silently stopped
catching things fails in front of the person evaluating whether any of this
works. Mutation-verified: fixing the swallow, making the decorative test
real, or enforcing the orphan budget each turns it red at 6 of 7.

## Not built, and that is the release decision

v0.3 ships four of the seven items below. Items 5-7 were not dropped for
lack of time; they were declined on doctrine 8.3, and the reasoning is
recorded here so the next session does not re-derive it.

**The marginal tool is now worth less than the first outside reader.** Every
claim in this repo has been validated against one codebase by one reviewer.
Doctrine 8.5 says the unvalidated loop is production until real operations
push back; four working tools and a ten-second demo is enough surface for
that push-back to arrive, and more surface would only mean more to unbuild
when it does.

**Each remaining item is also weaker than it looks:**

- **Item 5** gates on commit *shape*, which is precisely the kind of check
  that cries wolf - and a muted net is worse than none. It wants real
  commit histories to tune against, which is to say it wants users.
- **Item 6** would genuinely double the addressable audience, and it is the
  one item that should be built the moment somebody asks for it. Building
  it first is guessing at demand that one conversation would settle.
- **Item 7** is a prompt file: cheap, but it proves nothing until an outside
  reader has actually used it, at which point they can tell us what it
  should say.

The stop rule that would justify restarting: evidence from a repo that is
not this one. Not the backlog still having entries.

## Planned, if the evidence arrives

### 5. Commit conformance - ratchet the workflow (AGENTS.md 8, 11, 12)

The agent operating rules are good and unenforced. A pre-push hook or CI
job can mechanically check most of them: a fix-shaped commit with no test
change, a commit sweeping unrelated paths, a closed tracker item with an
untouched status doc. The ratchet philosophy applied to the process rather
than the code. Agents drift; the guard against drift should not be the
agent's own recall of a file it read a hundred thousand tokens ago.

### 6. TS/JS ports of the ratchet and swallow detectors

The README claims the ratchet pattern "ports to any language in an
afternoon". Spend the afternoon. Most agent-built apps are TypeScript end
to end, and empty `catch {}` is *the* idiomatic sin there - the shipped
swallow lint cannot see it.

### 7. The red-team diff review skill (rule 8.4)

8.4 says outside minds find what self-discipline cannot, but both shipped
skills are self-review by the same agent family that wrote the code. Add a
third: an adversarial review of a *diff*, written to be handed to a fresh
agent with no context, framed as "refute the claim that this diff is
correct". It is the only rule in section 8 with no artifact behind it.

## Deferred to v0.4, and why

- **A backend runtime probe.** The inner loop is frontend-only today, which
  is a real gap - the backend equivalent of "assert on live state" is
  currently just "exercise the real seam". Deferred because the surface is
  large (process attach, DB state, queue depth) and items 2-3 return more
  per line.
- **Playwright port of `uiGuards.ts`.** Mechanical, valuable, not urgent;
  the patterns already carry over by hand.
- **Mutation mode for `verify_guard`** (the "weaken the seam" half of 2.2).
  Real mutation testing on the named code files, requiring the guard to
  catch each mutant. Deferred deliberately: the revert half is the complete
  high-value unit, and shipping it whole beats shipping both halves badly
  (doctrine 8.3, the stop rule). The tool states this gap in its own
  `--help` rather than implying full coverage of 2.2.

## Subtractions (doctrine 8.2 applies to this repo too)

- `bootstrap.sh` copies every layer unconditionally. A backend-only team
  gets Cypress files it will never use, which reads as bloat and costs
  trust. Add `--layers doctrine,python,probe`.
