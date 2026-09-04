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

## What this repository is

Sutradhar is a **framework, not a product.** It ships a copy-in toolkit of
stdlib-only guards, this doctrine, and the agent workflow around them - and it
ships no runtime and installs nothing. The rules below are portable advice for
*your* codebase; they are not describing an application that lives here,
because none does. The only application in this tree is `examples/broken-app/`,
which exists to be broken at.

This is a commitment, not a description, so it is a gate rather than a
sentence - a rule that lives only in prose is one this framework does not
trust itself to keep. `framework_only.py` holds the line: the shipped guards
import the standard library only, and no dependency manifest may appear in the
framework surface (`examples/` excepted). The first `import requests` or the
first `requirements.txt` is the moment the framework starts becoming a
product, and the gate makes that a deliberate diff instead of a quiet drift.
Adopters build products with this; the framework itself stays a framework.

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
symbol the handler never imported.* A contract across a process boundary is tested by one test that crosses it: the client's real values against the server's real validation, in one run. Two green suites that each stub the other side have tested two assumptions and no contract. *Scar: all six of a client's upload purposes 400'd against the API, the error was swallowed, and three downstream features silently no-op'd; the API's tests used valid values, the client's stubbed the service, and neither could see the seam (B-6).*

**2.4 Honest degradation.** A failure states itself: no silent fallbacks, no
fabricated values, no "ok" status wrapping an error list. A partial result
carries a flag the caller must see. Confirmations (deletes, erasures, sends)
are issued only when every layer verifiably succeeded. *Scar: a purge on a
compressed table deleted nothing, hit a tuple-decompression limit, and
reported success; every erasure for months was a no-op with a receipt.*

**2.5 Freeze numeric truth.** Golden datasets with declared tolerances for
anything numeric. Re-baseline only deliberately, in the same commit as the
intentional change, with the reason in the commit message. A golden is a regression pin, not an oracle: it is generated from a source independent of the code it checks, never from that code's own output, or it freezes the bugs it exists to catch. *Scar: a build thread froze its engine's own output as the golden and locked every current defect in as truth (B-5).* Historical data carries the timestamp at which it became available, never the time it was written: a backfill dated to `now()` cannot be told from a live observation, and every replay afterward has seen the future. *Scar: two threads invented the availability timestamp independently (B-9).*

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

**2.9 A check that could not run has not passed.** "Did not fail" and
"could not measure" are different answers and must be different values.
Give the third state a name of its own, make it reportable as a rate, and
have it say what would settle the question. A check whose inconclusive
result is spelled the same as its pass is off, and looks on. *Scar, and the
only rule here that four independent build threads each invented separately
before it reached this file: a quality gate returned `None` both when it
could not compute a score and when it computed one and failed; the library
it needed was an optional dependency, so every deployment that lacked it ran
with the gate silently disabled under a green suite. The other three threads
arrived at the same shape from different directions - a trigger that reports
`UNARMED` rather than "not triggered", a verdict of `INSUFFICIENT_EVIDENCE`
that names the evidence that would resolve it, and a refusal rate published
alongside the pass rate. Convergence at that width is the strongest evidence
8.1 accepts.* This is 2.4 turned on the instrument: the guards must degrade
as honestly as the systems they watch, and the failure is quieter here
because a silent check produces no incident to investigate.

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
browser tools). Pixels lie in both directions.

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
not string presence. *Scar, the same defect on a second surface: an i18n check counted translation keys present, not keys reachable, and reported full coverage for strings no screen could show (B-17).*

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
config) so any generated artifact can be re-derived and disputed later. The anchor applies to actions, not only artifacts: a consequential agent action - a routing decision, a committed change, a send - leaves a tamper-evident record of its inputs, so what the agent *did* can be replayed and disputed the way what it *generated* can. *Scar: B-14 - the thread that paid for it built the receipt before this file named the rule.*

## 5. Claims (numbers that leave the building)

**5.1 Every published figure carries its provenance tier** (measured,
estimated with stated assumptions, or illustrative) in the artifact itself,
not in the author's head. A scenario presented as a measurement is a lie
with extra steps. The tier is per value, not per artifact: a derived value carries the weakest tier among its inputs, never the strongest, and a value with no witnessed source carries a gap marker, not a guess. *Scar: B-7 and B-12 - two threads built per-value tiers, one with an explicit gap tag, because one label on the whole artifact could not say which numbers inside it were real.* A published number is withdrawn only by a retraction published with the same provenance, never by a silent edit; retraction is a status of its own, and the number it replaces stays visible as retracted. *Scar: an RCA retracted eight already-promoted results, and nothing in this section had a name for what had just happened (B-10).*

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
costs more trust than no finding.* Pre-register, before the window opens, both the condition that kills the hypothesis and the condition that voids the test; a voided window is "the protocol working" only if that was written down first. *Scar: two validation windows were voided after the fact as "the protocol working, not a failure", and nobody could say whether that was true (B-8).*

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
proxy agreed, so the looking stopped.* A job's success carries its output count: a run that succeeds and produces nothing is a failure unless zero was declared expected, so the floor for a job is rows-per-run, not only fired-succeeded-failed. *Scar: a training loop ran thirty days at zero rows under green status, because the job counter could not tell a silent zero from a full run (B-4).*

**6.7 An exit code is not a witness.** It is a claim about a process, not
about a check. It is evidence only in pairs: a known-good input exits 0 AND a
known-bad input exits non-zero. Confirm a check exists and can fail before
reporting it green - `--selfcheck` on a tool with no argument parser exits 0
because the import succeeded. When an instrument and a person's observation
disagree, the instrument is on trial first. *Scar: the round-4 half of 6.6,
and the reason every guard here ships a selfcheck with a case it must fail.*

**6.8 An instrument's error branch must say WHOSE failure it is.** A handler
that cannot tell "the system is down" from "my parser crashed" reports the
wrong outage with total confidence - and it always reports it about the
system. Catch narrowly, print the exception type, and never let a fallback
speak on the subject's behalf. *Scar: a polling loop printed ten consecutive
"no response" lines about a production API that was serving 200s in 0.27 s;
a backslash inside an f-string raised, and the shell's `||` fallback turned
the poller's bug into a claim about the server.*

**6.9 A verdict's WORD is part of its correctness.** A number can be right
while the name attached to it sends the reader the opposite way, and nobody
re-derives a figure that arrived with a confident label. When one bound is a
floor and another a ceiling, a miss has a DIRECTION; name it, or the verdict
is wrong in the only register anyone reads. *Scar: a gate classified years
holding nine labelled stretches at 96% coverage - one over a ceiling of eight
- as "thin", and rolled them into "the past is empty theatre". The fix that
report argued for was the exact inverse of the one the data wanted.*

**6.10 Measure the whole surface the reader gets, or a real fix scores as a
no-op.** A metric scoped to less than what is delivered reports "unchanged"
for an improvement it is simply not looking at. Scope the measurement to the
artifact, and pin the mirror between instrument and product so it fails when
they drift apart. *Scar: a composed-versus-bank instrument read only the
card's headline while the fix landed in the paragraph beneath it - the
numbers moved by nothing and the fix was nearly reverted as ineffective.
Recorded here from the backflow register as B-18.*

**6.11 A guard that crashes has not reported anything.** Red is a verdict; a
stack trace is an absence of one, and it takes every other check in the run
down with it. Validate the shape before the operation that assumes it.
*Scar: a source guard sliced a string range to prove two controls sat in
opposite corners - the mutant that swapped them made the range reversed,
which is a fatal error, so the mutation run killed the instrument instead of
the guard.*


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
another project's untracked WIP into a robustness commit twice.* The mechanism for it is a file-ownership manifest: each parallel agent declares the paths it owns before it starts, and a stage that touches a path owned by another agent is refused. *Scar: the two collisions above; one thread built the manifest because the sentence had not prevented them (B-16).*

**7.4 Record what you ruled out** (and why) where the next session will
look. Un-recorded dead ends get re-explored at full price. Decisions chain: a record that changes an earlier one says whether it *extends* or *revokes* it, in those words, so a reader follows the chain without re-deriving it. *Practice, not scar (B-11): it strengthens this rule's mechanism and founds nothing.*

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
