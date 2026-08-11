# Round 3 - 2026-08-11

Lenses: verification method, honest reporting, irreversibility

**What this round was.** No code changed. A round spent on the *method*
rather than the tree, prompted by a stretch of work in which the tooling was
correct and the conclusions drawn from it were not. Recorded because the
premises corrected here cost more than any of the defects in rounds 1 and 2,
and because doctrine 8.1 admits a rule only with the incident that paid for
it - these are the incidents, held for a second confirmation before any of
them is promoted.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R3-1 | high | 6.4 | operating, not reading | deferred | a verification aimed at a queryable proxy passed repeatedly while the surface the user actually sees disagreed; the instrument was never made the suspect |
| R3-2 | med | 2.4 | building the recorder | fixed | a reporter that answers confidently on thin evidence will be believed on thin evidence; the refusal floor turned out to be the load-bearing behaviour, not an edge case |
| R3-3 | low | - | publishing | deferred | some published state is permanently irretractable; the inventory of what cannot be withdrawn belongs before the act, not after it |

## Corrected premises

These matter more than the fixes (robustness-loop phase 6), and this round
produced nothing but these.

### "My check passed, therefore the thing is true" (R3-1)

The sharpest lesson available in this framework so far, and the one it does
not yet state.

A claim was verified three separate times against an interface that was easy
to query. That interface agreed every time. The surface a user actually
looks at was served by a different path and disagreed the whole way through.
Nothing in the method was sloppy - the queries were correct, the parsing was
correct, the results were read correctly - and the conclusion was wrong
anyway, because the instrument was measuring an adjacent thing.

What makes this a rule rather than an anecdote: **the proxy agreed, so the
looking stopped.** A check that confirms the hypothesis ends the
investigation; a check that contradicts it starts one. That asymmetry is
where the class lives, and it is invisible from inside the check.

The doctrine reaches close to this and misses it. **3.3** says assert runtime
state, not pixels. **3.6** says a spec can pass vacuously, so measure
reachability and effect. **6.3** says measure, never eyeball. All three
discipline the *app*. None of them says: when a human reports what they see
and your instrument disagrees with them, **the instrument is the suspect**.
The report is data about the system; the instrument is a hypothesis about
the system.

Candidate rule, held pending a second incident:

> *Verify against the surface that carries the consequence, not the one that
> is convenient to query. Where a person's observation and an instrument
> disagree, the instrument is on trial first. A check that agrees with you
> has told you less than one that does not.*

The practical form costs nothing: before reporting a verification, state
which surface was measured and whether it is the one that matters. Where
those differ, say so in the same sentence as the result.

### "The refusals are edge cases" (R3-2)

Building a reporter that computes when to stop, the interesting part looked
like the computation. It was not. The behaviour that carries the weight is
the floor below which the tool declines to answer - because a report is
believed in proportion to its confidence, not its evidence, and a tool that
always produces an answer will be trusted on the round where it should not
have spoken.

Generalised past that one tool: **a reporting surface needs a stated
evidence floor, and must fail closed to "insufficient" rather than open to
a plausible number.** This is 2.4 (honest degradation) pointed at analysis
rather than at failure paths, and 5.1 (provenance) made operational. It is
recorded here rather than promoted, because it is currently one tool's
design decision and not yet a class.

### "Anything published can be withdrawn" (R3-3)

Discovered by attempting it: parts of a published artifact's history are
permanently immutable by design, and no amount of rewriting reaches them.
The retraction was mostly successful and permanently partial, which is a
worse position than either fully reversible or known-irreversible, because
the partial success reads as complete.

The framework rule this suggests is a prevention one, not an operating one -
closer to 1.4 (write the failure story at design time) than to anything in
section 6: **before publishing, know which parts of the act cannot be
undone.** Not because publishing is bad, but because "we can clean that up
later" is a plan that silently only half-works, and nobody checks which half.

Left at LOW and undeferred to any tool. One incident, and the honest
mitigation is a sentence of forethought rather than a mechanism.

## Harness gotchas

- A measurement harness written ad hoc is still a harness, and 6.3 applies
  to it in full. The exit code of a pipeline is the last command's; a
  verification that reports success because a pager exited cleanly is not a
  verification. This bit inside the very pass that was mechanising the rule
  about guards being shown to fail.
- Four tools were built in rounds 1-2 and all four had a real defect caught
  by their own selfcheck on its first run. That is not a coincidence worth
  celebrating; it is evidence about the base rate of defects in new code
  that looks finished, and an argument for the selfcheck being written
  before the tool is trusted rather than after it is shipped.

## Stop decision

Unchanged, and reinforced. The release stays closed at four of seven items.
This round adds no mechanism and promotes no rule; it records three
corrected premises so that a second incident can promote one on evidence
rather than on memory. Doctrine 8.2 applies to rules as much as to code:
adding one here, on a single incident each, would be the accretion the
framework exists to resist.
