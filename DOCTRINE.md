# The Doctrine

Standing engineering rules for agent-built software. Every rule entered this
list with the incident that paid for it; a rule nobody can cite a save from
is a candidate for deletion. A doctrine that cannot name its scars is
ceremony.

These are checkable practices, not aspirations. When a rule and a deadline
conflict, say so out loud rather than silently dropping the rule.

The one-line summary of the whole document: **almost every serious defect is
found by operating the system or asserting on its runtime state, not by
reading code; and almost every expensive defect could have been prevented by
a one-sentence design-time statement.**

---

## 1. Prevention (design time, cheaper than any detection)

**1.1 State your cardinalities and budgets before building.** Every feature
design names the N it must survive (rows, users, requests per second) and
its latency/memory envelope, as numbers. Tests then enforce the envelope -
mechanically: the numbers live in the design note's frontmatter, the test
reads its N from there (`with budget("fleet-sweep") as b: ... b.n ...`), and
`budget.py` fails the build on any declared number no test enforces. The
gate is deliberately not "did you write a note" - that measures paperwork -
but "is every number you wrote down actually binding".
*Scar: an unbounded fleet sweep worked perfectly at demo scale (50 entities)
and OOM-crashed the datastore at 200,000. The design-time sentence would
have cost nothing; finding it cost a full scale pass and seventeen store
crashes.*

**1.2 Make illegal states unrepresentable; ratchets are the second line.**
A seam whose type or constructor cannot express the bug beats a test that
catches it. When a fix is possible as either a guard or a seam, prefer the
seam. *Scar: a single tenant-binding type ended a cross-tenant-read bug
class that had regrown three times past individual guards.*

**1.3 Property-based and fuzz tests on parsing and numeric surfaces.**
Example tests pin known cases; properties pin the space. *Scar: the one
fuzzer we wrote (a wire-format decoder) caught a real defect within its
first week. Most such surfaces deserve one.*

**1.4 Write the failure story at design time.** For each dependency a
feature touches: what does the user see when it is down, slow, or partial?
If the answer is "the same as success", the design is not done. *Scar: a
metering read failed over to an empty map indistinguishable from "no usage",
and an invoice was computed over it.*

## 2. Backend

**2.1 Every fix ships with a guard in the same commit.** Prefer a class
ratchet (an invariant that walks the code by AST, route table, or schema and
fails on any current or future sibling) over a point test. *Scar and the
strongest statistic we own: ~37 ratchet tests produced two thirds of all
test-driven discoveries; ~1,400 point pins produced three.*

**2.2 Mutation-verify guards.** Revert the fix: the test must go red. Weaken
the seam: behavioral cases must go red. A guard never shown to fail is
decoration. *Scar: a tenant-isolation fix shipped tested-and-half-dead for a
week because its tests set internal state by hand; the production path ran
the guard in a thread whose context write was discarded, and no test noticed
because no test went through the route.* The revert half is mechanical -
`verify_guard.py` runs it in a throwaway worktree and exits nonzero when the
guard survives the revert; the weaken-the-seam half is still yours to run.

**2.3 Test through the real seam** (the route, the transport, the public
function), never by poking internals the production path does not use.
*Scar: a helper-level unit test passed while the route using it 500'd on a
symbol the handler never imported.*

**2.4 Honest degradation.** A failure states itself: no silent fallbacks, no
fabricated values, no "ok" status wrapping an error list. A partial result
carries a flag the caller must see. Confirmations (deletes, erasures, sends)
are issued only when every layer verifiably succeeded. *Scar: a purge on a
compressed table deleted nothing, hit a tuple-decompression limit, and
reported success; every erasure for months was a no-op with a receipt.*

**2.5 Freeze numeric truth.** Golden datasets with declared tolerances for
anything numeric. Re-baseline only deliberately, in the same commit as the
intentional change, with the reason in the commit message.

**2.6 Unbounded reads are bugs.** Any query or sweep over a collection that
grows with real usage carries a cap and an honest too-large refusal. ORDER
BY on an unbounded result set is a memory bomb. *Scar: see 1.1. Also: a
"latest timestamp" lookup that was O(1) when data existed and a full-table
walk when it did not, so exactly the newly-onboarded customer with no data
timed out on day one.*

**2.7 Exceptions are never silently swallowed.** An `except` block logs,
degrades explicitly, or re-raises. Returning an empty value from a bare
handler converts an outage into a lie. Enforced mechanically by
`swallow_lint.py`. *Scar: a fleet-wide read failure was swallowed into `{}`,
which downstream code read as "an event-free fleet", flipping a fraud
detector's verdict for every entity at once, under a green status.*

**2.8 String interpolation into a query language is a hole even when the
current value is safe.** The pattern becomes the vulnerability the moment
someone parameterises it. Enforced mechanically by `interpolation_lint.py`.

## 3. Frontend

**3.1 Every interactive control has an asserted effect.** A click must
change URL, DOM, or persisted state, and a test must assert that it did.
*Scar: a scope picker rendered, opened, accepted a selection, and changed
nothing; a sort header was static text with no control behind it. Both
passed every existing test, because every existing test asserted rendering.*

**3.2 Baseline per route: renders, no error boundary, console clean.** A
route-by-role sweep asserting landed (not bounced to login), no crash
fallback, zero meaningful console errors, non-empty body. Cheap, and it
catches the page-crashes-to-boundary class that review never sees.

**3.3 Assert runtime state, not pixels, in the inner loop.** While building,
verify against the running app's actual state: network responses, store
values, console. Use runtime observation (browser devtools protocol, MCP
browser tools, Reticle-class tools). Pixels lie in both directions.

**3.4 Keep paint checks in the outer loop.** Inside-the-app observation
cannot see pure paint defects (overprints, occlusion). The committed e2e
suite keeps geometry and visibility assertions and stays the regression
gate. *Scar: a badge painted over a currency figure; two drafts of the
detector passed against a reproduction because box geometry and scrollWidth
are both blind to it. The shipped detector measures inked bounds with a
Range.*

**3.5 Instrument at the source.** Stable testids are source work, done when
a component is built, one naming idiom per project. A page with no anchors
is unanchorable and its specs will rot. *Scar: an entire dashboard shipped
with zero testids and the whole surface was untestable after the fact.*

**3.6 Selector counting measures nothing.** A testid can exist and be
unreachable; a spec can pass vacuously (`not.exist` on deleted selectors,
catch-all redirects masking dead routes). Measure reachability and effect,
not string presence.

## 4. AI/LLM (for products that ship model-backed features)

**4.1 The model phrases; it never invents.** LLM output is grounded in
computed values or refuses cleanly. Every generated number is traceable to a
computation or flagged as unverifiable, mechanically (a claim-check pass
over the output), not by prompt hope.

**4.2 Eval sets are golden files for prompts.** Every LLM surface gets a
small frozen eval run as a regression gate; a model or prompt swap must pass
parity before shipping.

**4.3 Schema-validate every structured output** with bounded corrective
retries. A model response is untrusted input.

**4.4 Budget tokens like memory.** Per-surface caps, metered and surfaced.
Usage-priced dependencies without budgets are unbounded liabilities.

**4.5 Human review is non-overridable for consequential artifacts.** Where
generated output leaves the building (letters, filings, recommendations),
`requires_review` is frozen at the type level, not a flag someone can flip.

**4.6 Anchor for replay.** Hash the inputs (prompt version, grounded values,
config) so any generated artifact can be re-derived and disputed later.

## 5. Claims (numbers that leave the building)

**5.1 Every published figure carries its provenance tier** (measured,
estimated with stated assumptions, or illustrative) in the artifact itself,
not in the author's head. A scenario presented as a measurement is a lie
with extra steps.

**5.2 Sell the method, not the demo numbers.** Synthetic-corpus results
never leave as evidence. The first real deployment converts scenario rows to
measured ones; nothing else does.

## 6. Operating (what code reading cannot find)

**6.1 Drills outrank review.** Cold-start-from-docs, restore-reconciliation,
unattended soak, upgrade-in-place: recurring, with command-verifiable gates
and a deviation log. *Scar: the un-restorable backup, the root-owned data
directory, and the architecture-dependent build were all invisible to
review and each fell out of the first drill that touched it.*

**6.2 A backup that has not been restored somewhere is cosmetics.** No real
data rides on an unreconciled restore path. *Scar: a plain `psql < dump`
restore aborted at the catalog and left 25 tables at zero rows. The dump
tool had warned; nobody had checked.*

**6.3 Exit-code discipline.** Never pipe a build or test through anything
that swallows `$?`. Truncated runs report as truncated. Measure (counts,
exit codes, RSS, computed layout), never eyeball. *Scar: `| tail` reported a
failed production build as success during a drill; an OOM-killed test run
reported its last green line and passed for two rounds as a full suite.*

**6.4 Verify a finding refutes the null before filing it.** Prove the test
itself is valid first. *Scar: `docker kill` suppresses restart policies by
design; we nearly filed a bug against a healthy stack. A false finding
costs more trust than no finding.*

**6.5 Converged areas regrow.** Hardened subsystems get periodic re-audit,
not a "done" sticker. *Scar: an authorization layer declared mature regrew a
cross-tenant read within five rounds.*

**6.6 Observability is a provenance gate.** A change to a running system is
done only when its effect can be witnessed at a runtime surface, and a claim
about a running system is worth exactly what the surface that witnessed it
is worth. The floor, before anything runs unattended: requests (count +
latency by route template, never raw path), jobs (fired, succeeded, failed),
ingest chokepoints, and dependency up/down gauges. A surface that cannot
report must say so - an endpoint that degrades to an empty 200 turns "no
data" into "all zero", and every claim read from it afterward is fabricated
with extra steps. This is 5.1 pointed at runtime: unwitnessed numbers do not
leave the building, and unwitnessable tasks are not done. *Scar, twice: a
verification read a queryable proxy three times while the surface a person
actually saw disagreed throughout (round 3); a review read exit 0 from five
tools whose selfchecks did not exist - the process terminated, nothing was
witnessed, and the zero was reported as a pass (round 4). Both times the
proxy agreed, so the looking stopped.*

## 7. Multi-session / multi-agent workflow

**7.1 Orient before starting.** Read the owning plan or tracker AND
spot-check its claims against the tree. *Scar: parallel sessions completed
two workstreams that were then started fresh by sessions that skipped the
two-minute grep.*

**7.2 Trust the tree, not the doc.** Status docs go stale in days. Verify
"done" claims against code before acting on them, and record your own
completions the same day so the next session can trust the doc a little
more.

**7.3 One worktree per agent. Stage only named files; never `git add -A` on
a shared tree.** *Scar: an agent's explicit `git add <file>` captured
another session's unstaged mid-edits to the same file; a `git add -A` swept
another project's untracked WIP into a robustness commit twice.*

**7.4 Record what you ruled out** (and why) where the next session will
look. Un-recorded dead ends get re-explored at full price.

**7.5 Serialize runs that share a backend.** Two concurrent test runs
against one slow service poison each other's results; the invalidated
verdicts cost more than the parallelism saved.

## 8. Meta (rules about the rules)

**8.1 The doctrine grows only from evidence and shrinks by it too.** A new
rule enters with the incident that paid for it. A rule nobody can cite a
save from in months is deleted.

**8.2 Deletion is a discipline.** Guards, tests, services, and rules accrete
by default; schedule pruning. Great systems subtract. *(The 1,400-point-pins
lesson lives here.)*

**8.3 Have a stop rule.** Engineer time is a budget. When the marginal round
of any loop (hardening, polishing, testing) yields less than the next
cheapest activity, stop and switch. *Scar: it took us 24 rounds to ask the
question. Ask by round 5.*

**8.4 Seek outside minds on purpose.** One mind, or one family of agents,
shares blind spots with itself. Independent review, domain red-teams, and
paying users find classes self-discipline cannot. Budget for them; they are
epistemics, not compliance.

**8.5 The unvalidated loop is production.** Everything above is pre-field
doctrine until real operations push back. Expect the first production
contact to add rules nothing here anticipates. That is the system working,
not failing.
