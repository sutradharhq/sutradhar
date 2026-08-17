# Round 7 - 2026-08-17

Lenses: multi-thread survey, provenance, backflow

*Drafted in the same parallel session as round 6, first numbered round 4
against a stale `main`; renumbered 7 before merge. "Round 6" below means this
session's DSH cross-read and adoption audit, not the maintainer's weekly
review that now holds round 4.*

**What this round was.** A survey of the independent build threads this
doctrine was distilled from, run because round 6 was wrong about them.

Round 6's adoption audit concluded that the framework's mechanisms were
installed but unused in the field. That conclusion came from a sample
selected on the presence of `AGENTS.sutradhar.md` - a file that marks where
`bootstrap.sh` was run, not where the practice lives - and from two greps
whose shell globs failed silent and returned zero. Both halves of the method
were wrong, and they failed in the same direction: toward "nobody is doing
this."

The threads are ten separate builds. Several are deep, four have developed
discipline the doctrine does not carry, and none of it has ever flowed back.
This round records the threads, the backflow they are owed, and the two
round-6 findings that do not survive contact with them.

## The threads

Scale is `git rev-list --count HEAD` and file counts excluding vendor trees.

| thread | what it is | scale | discipline it developed | doctrine rule it would strengthen |
|---|---|---|---|---|
| **Thread-A** | a quant-trading system | 850 commits, 1,291 py, 517 test files | a robustness gate as executable, unit-tested code; named review charters, and an RCA that **retracted 8 already-promoted results** | 5.1, 6.4 |
| **Thread-B** | a multi-stack operations platform | 280 commits, 1,364 ts/tsx, 243 dart | a 16-iteration ledger over a 14-dimension board, **four-tier evidence tags** `[V] [R] [I] [GAP]`, refutation-before-filing, "the loop does not mark its own homework", and a Playwright port of `expectEffect` | 5.1, 6.4, 6.5, 3.1 |
| **Thread-C** | a sibling multi-stack build | 194 commits, 1,113 ts/tsx, 297 dart | 66 ADRs, 32 e2e specs; ADR-heavy, no ledger | 7.4 |
| **Thread-D** | a governed agent-harness fork | 61 commits, 1,224 py, 537 test files | exact policy check plus a **tamper-evident receipt** on every routing decision and committed action | 4.6, 5.1 |
| **Thread-E** | a model orchestrator | 115 commits, 143 py | 18 ADRs carrying **`Extends (does not revoke)`** supersession chains | 7.4 |
| **Thread-F** | — | 119 commits, 209 py | robustness-loop skill, one baseline | — |
| **Thread-G** | — | 60 commits, 127 py | 4 ADRs; worktree-per-agent in practice | 7.3 |
| **Thread-H** | experiment | 67 commits, 58 py | two baselines; the widest guard install of any thread | — |
| **Thread-I** | experiment | 18 commits, 46 py | — | — |
| **Thread-J** | a harness experiment of its own | 2 commits, 24 py | — | — |

`expectEffect` is worth stating precisely, because round 6 got it wrong in
both directions. Thread-F, Thread-E and Thread-H contain the helper's DEFINITION
and no call sites. Thread-B is the only thread that uses it - and only after
porting it, because, in its own words, the shipped Cypress template "could
not run: it is a pnpm monorepo with Playwright, and the template's runner was
never adapted."

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R7-1 | high | - | thread survey | deferred | no mechanism moves an innovation from a build thread into the doctrine; four threads independently solved problems the doctrine still lists as open, and the distillation is now behind its own sources |
| R7-2 | high | 5.1 | thread survey | deferred | the README calls its statistics "measured from one production build record - ours" and warns that "one codebase is a sample size of one"; the doctrine was distilled from ten independent builds, so the repo's own provenance claim is wrong in the conservative direction |
| R7-3 | med | 8.1 | thread survey | deferred | rounds.py assumes one repository, so the only question that makes 8.1 answerable at this sample size - which rules earn saves across INDEPENDENT builds - cannot be asked |
| R7-4 | med | - | thread survey | deferred | rounds.py's record format is poorer than the ledgers threads already keep: six columns and a binary provenance label against a 14-dimension board with four evidence tiers, so adopting it asks a thread to downgrade |
| R7-5 | med | 5.1 | Thread-A | deferred | section 5 governs how a published number is labelled and says nothing about withdrawing one; Thread-A retracted 8 promoted results after an RCA and the doctrine has no name for the move |
| R7-6 | med | 8.1 | rounds report | deferred | a retracted finding keeps the save it already paid its rule, because attribution counts first appearance and has no retraction path; closing R6-12 and R6-13 below does not undo their saves to 8.3 and 1.1 |
| R7-7 | med | 7.4 | Thread-E | deferred | Thread-E's ADRs carry `Extends (does not revoke)` supersession chains - the mechanism R6-1 records as missing - invented locally and never offered upstream |
| R7-8 | med | 6.5 | Thread-B | deferred | 6.5 says converged areas regrow but does not say a prior session's green gate is not an audit; Thread-B's ledger refuses head-start green outright and starts every dimension unaudited |
| R7-9 | med | 5.1 | Thread-B | deferred | Thread-B's four evidence tiers are finer than 5.1's three and than rounds.py's binary RECORDED/MEASURED, and they tag per claim rather than per report |
| R6-12 | med | 8.3 | thread survey | closed | the fact stands (rounds.py, 0 of 6) but the diagnosis was backwards; superseded by R7-4 |
| R6-13 | med | 1.1 | thread survey | closed | retracted: "the two largest repos carry zero round records" is false - Thread-A keeps its own robustness state and log, Thread-B keeps a 16-iteration ledger |

## Backflow register

What the threads are owed, in the order their evidence is strongest. This is
the residual register's counterpart: the residual register tracks what this
repo deferred, and this tracks what it never collected.

1. **Evidence tiers per claim** (Thread-B → 5.1). Four tiers, tagged on the
   claim rather than the report. 5.1's three tiers are coarser and sit at
   document level.
2. **Retraction** (Thread-A → section 5). A published figure that turns out
   wrong needs a defined withdrawal, not just a better label next time.
3. **Supersession chains** (Thread-E → 7.4). `Extends (does not revoke)` makes a
   decision record's relationship to its predecessors explicit and checkable.
4. **No head-start green** (Thread-B → 6.5). A prior session's passing gate is
   evidence, not an audit; a dimension starts unaudited regardless.
5. **Receipts** (Thread-D → 4.6). 4.6 asks for replay anchors; a tamper-evident
   receipt per committed action is the stronger form and is already shipping.
6. **The gate as code** (Thread-A → 2.1). A robustness gate that is a unit-tested
   module rather than a document cannot rot into prose.

## Corrected premises

- **"The framework's sample is one codebase."** Held since v0.1 and stated in
  the README. It is ten, and the threads are genuinely independent - different
  stacks, different domains, different failure modes. Everything downstream of
  the single-sample premise needs rereading, including rounds 1 and 2's
  repeated note that "no outside mind has read this code."
- **"Adoption means the copied files are present."** The measurement that
  produced round 6's field conclusion counted installed files. Thread-B scores
  poorly on that metric and runs the most disciplined loop of any thread.
  Presence of the artifact is exactly the "selector counting measures nothing"
  error (3.6) applied to a repository instead of a DOM.
- **"A survey is a cheap way to check a claim."** Round 6's survey was cheap
  and wrong, and it was wrong in a way that flattered the surveyor: it found
  that the framework's users were failing rather than that the framework had
  fallen behind. Two of its greps returned zero because a shell glob failed,
  and no negative case was run to prove the greps could return non-zero. A
  check is evidence only in pairs - the discipline was applied to the guards
  this round and not to the survey, and it is the same class R3-1 (the
  maintainer's method round) holds pending: a check that agrees with you has
  told you less than one that does not.

## Harness gotchas

- On the true history the recorder reads CONTINUE at every round, this one
  included: R7-1 and R7-2 are HIGH. An earlier draft claimed a "quiet
  stretch" ended here; there was none - that reading came from the same stale
  checkout round 6's gotcha describes.
- R7-6 means the attribution figures carry two saves earned by findings that
  are retracted or superseded. Read `8.3` and `1.1` with that discount until
  a retraction path exists - round 8 builds it.
- Round-006 is left as written apart from its renumbering and corrections; its
  two resolved findings are closed here rather than edited there.

## What we ruled out

- **Editing round-006's findings.** Same rule as round-002: a logbook
  rewritten to look right is worse than one wrong in public. R6-12 and R6-13
  are closed here with the reason, and the original rows stand.
- **Treating the threads as one build record.** They share an author and
  nothing else structural - different stacks, domains, and deployment shapes.
  Merging them would recreate the single-sample premise this round retires,
  and would hide that the four backflow items were each invented in exactly
  one thread.
- **Building anything this round.** Every finding above is a rule or a format
  question, and R7-1 says the framework's problem is not a missing tool. The
  next build action should be whichever backflow item the doctrine accepts
  first, not a new mechanism.

## Stop decision (doctrine 8.3)

CONTINUE, and for the first time on evidence the framework did not generate
about itself. Rounds 1 through 5 were self-work, and round 6 read an outside
artifact with the same eyes; this round's findings come from ten trees that
were not built to test the doctrine.

The stop rule measures HIGH findings per round and nothing else. Neither its
reading here nor anywhere was ever about whether the hardening loop had
converged in the products - no thread's loop reports into it, which is R7-3.

The work this round justifies is collection, not construction: take the six
backflow items, decide which the doctrine accepts, and write those rules with
the thread that paid for them named as the scar. That is 8.1 operating the way
it was designed to and never yet has - a rule entering with the incident that
bought it, from a build that is not this one.
