# Round 5 - 2026-08-16

Lenses: doctrine promotion, provenance, mechanisation

**What this round was.** The maintainer resolved R4-5. Observability enters
the doctrine as **6.6**, and it enters as a provenance gate rather than as a
monitoring mandate - in the maintainer's words: *"observability as a
provenance gate. therefore every task becomes verifiable. that's where we
draw the line."* This round records the decision, the promotion, and the
tool that makes the rule checkable.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R4-5 | med | 6.6 | maintainer decision | fixed | the observability floor is numbered (6.6), mechanised (obsgate.py), and citable; rounds --check now accepts findings against it |
| R3-1 | high | 6.6 | maintainer decision | fixed | the round-3 candidate rule ("verify against the surface that carries the consequence"), held pending a second incident, is promoted: the second incident was R4-1, and the rule is now 6.6 |
| R5-1 | med | 2.2 | obsgate mutation run | fixed | first selfcheck survived a blinded empty-payload branch: the verdict stayed UNWITNESSED via per-surface misses, so the one diagnosis naming the empty-200 lie vanished undetected. The selfcheck asserted the outcome, not the reason |
| R2-4 | high | 3.6 | - | deferred | unchanged: still awaiting a second repo |
| R1-7 | med | 2.2 | - | deferred | unchanged |
| R1-8 | med | 1.1 | - | deferred | unchanged |
| R1-9 | low | 1.1 | - | deferred | unchanged |

## Why 6.6 cleared the 8.1 bar

A rule enters with the incident that paid for it. This one has two, both in
this register:

- **Round 3, R3-1**: a verification aimed at a queryable proxy passed three
  times while the surface a person actually saw disagreed throughout. Held
  then as a candidate, pending a second incident.
- **Round 4, R4-1**: a review read exit 0 from five selfchecks that did not
  exist. The process terminated; nothing was witnessed; the zero was
  reported as a pass. Round 4 declined to promote because 2.2 already
  covered the CLI case - correctly, for that case.

What 6.6 adds that 2.2 does not: 2.2 disciplines *guards* (a guard never
shown to fail is decoration). Neither it nor anything in section 6 said
what these two incidents share: **a claim is worth what the surface that
witnessed it is worth, and a surface that cannot witness must say so.**
That is 5.1's provenance discipline pointed at runtime, which is why the
rule lands in Operating with a cross-reference rather than as a new
section.

The framing matters and is the maintainer's: not "run a metrics stack" -
that would be a mandate this toolkit cannot check - but "unwitnessable
tasks are not done." A gate, not an aspiration. That is the line, and
everything past it (dashboards, tracing, alerting, SLOs) stays outside the
doctrine until an incident pays its way in (8.1, 8.5).

## What was built

`obsgate.py` - the floor as a checkable gate. Floor declared as JSON, one
entry per surface (pattern, min_series, per-label cardinality caps);
payload read from a file or endpoint; verdict tri-state.

The three refusals are the tool:

- **Empty payload → UNWITNESSED.** An endpoint that answers with nothing
  has not reported zero traffic; "no data" and "all zero" must never read
  the same (2.4).
- **Unreachable source → INCONCLUSIVE.** A dead endpoint witnesses
  nothing. Mapping it to a pass would be R3-1 shipped as a tool.
- **Cardinality past cap → UNWITNESSED.** Raw paths where route templates
  belong - the unbounded-cardinality memory bomb (the 1.1 class,
  relocated to the metrics store).

Mutation-verified five ways: blinded empty-payload branch, blinded
cardinality cap, blinded min_series check, INCONCLUSIVE→WITNESSED swap on
dead endpoints, broken parser regex. All five go red; restored goes green.

**R5-1, recorded because the base rate held.** Rounds 1-2 observed that
every tool's selfcheck caught a real defect on its first run. This one
appeared to pass its mutation run first time - and the appearance was the
defect. Blinding the empty-payload branch left the verdict UNWITNESSED
(per-surface misses still fire), so the selfcheck's verdict-only assertion
stayed green while the diagnosis that names the lie disappeared. The
selfcheck now asserts the violation text, not just the verdict. The
generalisation is already written down as R3-2: a reporter is believed in
proportion to its confidence, not its evidence - and a *check* is trusted
in proportion to what it actually asserts, not what its name implies.

## Harness gotchas

- The reachability ratchet from round 4 covered `obsgate` automatically on
  the day it landed - 33 parametrised cases across 11 modules, no edit to
  the test. That is what a class ratchet is for (2.1), and it is the first
  concrete repayment on the round-4 work.
- CI invokes every tool as a direct script (`python .../obsgate.py`), not
  as a module. A tool with intra-package imports would pass `-m` locally
  and die in CI. obsgate is stdlib-only and self-contained like its
  siblings; the constraint is now written here so the next tool's author
  reads it before, not after.

## Stop decision

The v0.3 stop on items 5-7 is **unchanged** - none of them were built, and
the restart bar for them (external evidence) remains unmet and unreachable
while the repo has no outside users.

6.6 did not reopen that decision and did not need to: it entered by
maintainer decision on two recorded incidents, which is the 8.1 mechanism
working as designed. The distinction worth keeping: items 5-7 wait on
evidence the repo does not have; 6.6 had its evidence in this register
already.
