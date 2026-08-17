# Round 6 - 2026-08-17

Lenses: outside evidence, doctrine coverage, adoption audit, self-application

*Drafted in a parallel session whose local `main` was stale - it lacked the
maintainer's rounds 3, 4 and 5 and the R2-4 addition. First numbered 5/6/7
against that stale view; renumbered 6/7/8 before merge to sit after the
maintainer's rounds, which the session could not see. The collision itself is
recorded as a finding in round 8 (7.5). Content is preserved; only numbers,
ids, and the stop-rule reasoning that depended on the stale history are
corrected.*

**What this round was.** Not a build pass and not an adversarial sweep: a
cross-read of an outside repository against this doctrine. DeepSeek published
`deepseek-ai/deepseek-harness` (DSH) on 2026-08-13 - an agent runtime, ~49
package groups of TypeScript, MIT, developer preview - carrying an unusually
heavy internal engineering-discipline layer built by a team that has never
read this framework.

It is recorded as a round because doctrine 8.4 names outside minds as a
distinct evidence source and this is the first time this repo has had one,
and because the read produced findings against real gaps rather than
impressions. The findings are gaps in THIS framework surfaced by the
comparison; DSH's own gaps are not findings against us and are recorded under
*What we ruled out* instead.

The round grew a second half when the cross-read prompted a plainer question:
is this framework over-tightened for the repos that actually took it? That is
an adoption audit against six trees rather than a cross-read, so R6-12 and
R6-13 carry their own found-by. It is the only part of this round measured
against the working tree instead of a document.

The honest limit, stated first: this is convergent evidence for the DOCTRINE
(8.4 satisfied), and no evidence at all for the GUARDS (8.5 still unsatisfied).
Nobody outside this repo has run `verify_guard.py`, `budget.py`, or
`rounds.py`. A round that confused those two would be exactly the provenance
failure 5.1 names.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R6-1 | med | 7.4 | dsh cross-read | deferred | 7.4 records what you ruled out in prose only - no format, no artifact, no gate; DSH carries 684 path-encoded decision notes under a lifecycle gate that fails a non-trivial PR without one |
| R6-2 | med | 2.1 | dsh cross-read | deferred | our ratchets are opt-in per detector; exhaustive per-unit ownership with a required explained-empty reason is the stronger shape and we have no form of it |
| R6-3 | med | 2.4 | dsh cross-read | deferred | 2.4 says a failure states itself but never that orthogonal outcomes report on independent axes; a run can time out AND exit 0 by trapping the signal |
| R6-4 | med | 2.3 | dsh cross-read | deferred | "the real seam" permits a source-path launcher; the PUBLISHED artifact under plain node is the stronger seam and catches settle races and resolution failures a dev loader masks |
| R6-5 | med | 7.2 | dsh cross-read | deferred | 7.2 copes with stale docs instead of gating them; word budgets, export-JSDoc and dead-link gates make staleness fail loudly, and agent context is the wrong place to accept decay |
| R6-6 | med | - | dsh cross-read | deferred | no rule bounds the COST of verification; agents default to the full suite where the changed surface names a narrower proof |
| R6-7 | med | 2.7 | dsh cross-read | deferred | swallow_lint cannot see the idiomatic TS form of 2.7; a ~49-package TS repo enforces the same rule by prose because no lint exists for it - roadmap item 6 now has its outside demand signal |
| R6-8 | med | 8.1 | rounds report | fixed | round-002 re-listed three open deferrals as new rows; residual_register already carries deferrals forward, so the only effect was inflating 2.2 to 5 saves and 1.1 to 4, of which 3 are re-counts |
| R6-9 | low | 8.2 | dsh cross-read | deferred | 8.2 has no mechanism at all; dead-export and clone detection are the missing tools and both are off-the-shelf |
| R6-10 | low | 8.4 | dsh cross-read | deferred | 8.4 still has no artifact in either repo - DSH ships two review skills, both self-review by the same agent family that wrote the code |
| R6-11 | low | - | reading our own tree | fixed | doctrine 3.7 (on the declined guard branch, not on main) was filed beneath the `## 4. AI/LLM` heading, so a reader landed in the wrong section; fixed on that branch, and the parser is section-blind and never noticed |
| R6-12 | med | 8.3 | adoption audit | deferred | 551 LOC (20% of the toolkit) sits in rounds.py, adopted by 0 of 6 projects; guard weight tracked author interest rather than evidence of need |
| R6-13 | med | 1.1 | adoption audit | deferred | the two largest repos (~2.4k code files each) carry zero round records and, in one case, zero design notes, while 26- and 60-file repos carry eight guards each |

Open deferrals from earlier rounds are NOT re-listed here. See R6-8: the
register carries them forward on its own, and re-listing them costs
attribution accuracy for nothing.

## Corrected premises

- **"Outside evidence will arrive as someone using our tools."** It arrived
  as someone independently deriving our rules and never touching our tools.
  The v0.3 stop decision named "evidence from a repo that is not this one" as
  the restart condition without distinguishing convergence on the DOCTRINE
  from push-back on the GUARDS. Only the first has happened, and the two
  justify different work: convergence sharpens rules, push-back would fix
  tools. Restarting the tool backlog on doctrine evidence would be reading
  the wrong signal, so the items below are rule work, not tool work, except
  where an outside repo demonstrates the tool gap directly (R6-7).
- **"A logbook is cheap to keep honestly."** R6-8 is this repo's own flight
  recorder reporting inflated attribution because a previous round wrote its
  register out by hand for readability. The convenience copy became the
  measurement. This is 5.1 inside the tool built to enforce 5.1, and it took
  an unrelated cross-read to notice.
- **"Our doctrine covers the process; the mechanisms are the gap."** Half of
  this round's findings are missing RULES, not missing tools: nothing in the
  doctrine bounds verification cost (R6-6), requires orthogonal outcomes to
  report independently (R6-3), or reaches the published artifact rather than
  the seam (R6-4). The framework has been treating prose as the solved half.
- **"More mechanism is more safety."** The adoption audit says the opposite
  happened. The three most expensive tools by line count are the three least
  adopted; the two smallest repos (26 and 60 code files) carry eight guards
  each while the two largest (~2.4k files each) carry five or six, no round
  record, and in one case no design note. Every baseline in every adopting
  repo was written at adoption and never moved again save one, so the
  ratchets are recording a floor rather than lowering it. Guard weight went
  where installation was easy, not where the risk was - which is 8.3 failing
  in the direction the stop rule cannot see, because a tool nobody runs
  produces no findings and therefore never argues for its own deletion.

## Harness gotchas

- R6-8 was fixed in-round: `rule_attribution` now counts a finding once, on
  its first appearance, so a re-listed deferral is bookkeeping. Round-002 was
  NOT edited - a logbook rewritten to look right is worse than one wrong in
  public - so its duplicate rows stand and the parser ignores them.
- The stop-rule reasoning in the first draft of this record was written
  against a stale local `main` and reported a REST verdict that never existed
  on the true history. That was itself an instance of the R3-1 class the
  maintainer's method round names: a verification read from the convenient
  surface (the local clone) rather than the one that carries the consequence
  (origin). The corrected reading is below; the mistake is kept as a premise,
  not smoothed away.
- Every verification in this round was performed by the author. Reading an
  outside repo is the weaker form of 8.4 - an outside ARTIFACT, still read by
  the same mind that wrote the doctrine.

## What we ruled out

- **Adopting DSH's mechanisms directly.** Its discipline layer is welded to
  Cordis, pnpm, vitest and oxlint; nobody can take the discipline without
  taking the runtime. What ports is the SHAPE of four mechanisms (R6-1,
  R6-2, R6-5, R6-9), not the implementations.
- **Treating DSH's gaps as work for us.** It has no cardinality or budget
  discipline (its only scale lanes sit outside every CI gate, and its own
  stress-testing note is still `proposed/`), no operational drills, no eval
  sets or grounding gate on the model output it exists to produce, and no
  stop rule or rule-attribution over its own ~124 gates. Those are the four
  places this framework is genuinely ahead. They are recorded here as the
  measured contrast that makes the convergence meaningful, and they generate
  no findings against us.
- **Filing the convergences as saves.** DSH independently derived 2.2
  ("introduce the regression, watch red, revert"), 2.3, 2.7, 4.6 and the
  verify-the-world half of section 6. That is the most valuable thing in this
  read, and it is not a finding: no defect was surfaced, and counting
  agreement as a save would corrupt exactly the attribution R6-8 is about.

## Stop decision (doctrine 8.3)

CONTINUE. `stop_rule` measures whether the HARDENING loop is still finding
defects in the code, and this round genuinely found none there - it did not
run the code. It read a doctrine against an outside repo and audited six
adopting trees, and found thirteen gaps in COVERAGE and UTILISATION,
different questions the tool does not measure and should not pretend to.

R6-12 indicts the verdict mechanism either way: the stop rule can only see
loops that produce findings, so a tool that no project runs never appears as
a cost and never argues for its own deletion.

The work this round justifies is rule work - R6-3, R6-4 and R6-6 are
one-sentence doctrine additions with real scars behind them, two of them
someone else's scars - plus R6-8, the only finding here that touches a
shipped tool and the only one that is a straight defect rather than a gap -
and R6-12/R6-13, which argue for SUBTRACTION rather than more mechanism, and
are the first findings in this repo's history to do so.
