# Round 8 - 2026-08-17

Lenses: deletion pass, instrument validity, register hygiene

*Third record from the same parallel session, first numbered round 7;
renumbered 8. "Round 6" and "round 7" below are this session's DSH cross-read
and thread survey.*

**What this round was.** The first run of the question 8.1 exists to ask:
which rules earn their keep? Crossing five rounds lifted the recorder's
attribution refusal and it named twenty-four never-cited rules as deletion
candidates. This round reads each one, sweeps the residual register against
the tree, and disposes of both lists.

The headline verdict first: **zero rules are deleted, and the tool that
proposed the list was wrong to propose it.** The recorder's refusal floor
counted rounds and not time; a burst of rounds in nine days satisfied it
while 8.1's own condition - MONTHS of silence - had not begun to run. The
list was evidence about the instrument, not about the rules. The instrument
is fixed earlier in this branch (R8-1); the per-rule reading below stands as
the recorded baseline for when the 60-day clock has actually run.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R8-1 | med | 8.1 | reading the tool against its rule | fixed | the deletion floor counted rounds, not time: a burst of rounds in nine days named candidates while "months of silence" had not begun to run; a 60-day span floor added, mutation-verified, and an unparseable date now reads as too-thin rather than long-enough |
| R8-2 | med | 7.1 | consolidation postmortem | fixed | 7.1 cited twice in one session, compounding: a rebase first read a stale origin as current (false REST verdict), and then the renumbering meant to DODGE that collision itself collided - rounds were shifted clear of upstream rounds 3-4 without spot-checking the tree for round 5, which existed (the 6.6 promotion). Orient-against-the-tree was skipped at the exact step meant to fix skipping it |
| R8-3 | low | 5.1 | scar inventory | deferred | the preamble says every rule entered with the incident that paid for it, but many rules carry no inline scar; the entry claim is unverifiable exactly where attribution is also silent |
| R7-6 | med | 8.1 | - | closed | fixed by the `retracted` status shipped earlier in this branch: a retracted finding now leaves the register and takes its rule-attribution save with it |
| R6-13 | med | 1.1 | - | retracted | re-marked with the new status so its 1.1 save leaves attribution; R6-12 stays closed, not retracted - its fact was true and its 8.3 save stands |

R3-1 and R4-5 are NOT in this table, though an earlier draft closed them
here. The maintainer's round 5 already closed both by promoting 6.6; the
deletion pass only verified that against the tree (6.6 carries the
queryable-proxy scar inline and names round 3; `docs/operations.md` titles
its floor "(doctrine 6.6)" and points at `obsgate.py`). Re-closing an
already-closed finding is the same double-count R6-8 fixed for attribution,
one register over - so the sweep notes them resolved and touches nothing.

## The never-cited rules, read one at a time

Because the clock floor (R8-1) now refuses a deletion-candidate list until
the history spans 60 days, this table is not an action list - it is the
baseline reading for when the clock legitimately runs. Columns: inline scar
in DOCTRINE.md; mechanism shipped in this repo; field evidence seen this
cycle (the round 6-7 thread survey - evidence the recorder cannot read,
which is R7-3). `keep/field` means a thread's ledger shows the rule's class
caught in practice; `keep/scar` means the rule entered with a named incident
and no round has entered its domain; `keep/bare` means neither scar nor
citation - the rule rests on the origin record alone.

| rule | scar | mechanism | field evidence this cycle | verdict |
|---|---|---|---|---|
| 1.2 | yes | none (pattern) | - | keep/scar |
| 1.3 | yes | none | Thread-B D9: 21 properties x 5k cases, real payslip defect found | keep/field |
| 1.4 | yes | design-note template | - | keep/scar |
| 2.5 | no | golden.py | - | keep/bare |
| 2.6 | yes | detectors.py (ORDER BY) | Thread-B D13: reads proven index-served at 73k rows | keep/field |
| 2.8 | no | interpolation_lint.py, installed in all six guard-adopting repos | no recorded catch anywhere | keep/bare - the first honest deletion test when the clock runs |
| 3.1 | yes | expectEffect | Thread-B ported it to Playwright and asserts control effects | keep/field |
| 3.2 | no | route sweep | - | keep/bare |
| 3.3 | no | runtime probe | - | keep/bare |
| 3.4 | yes | inked-bounds detector | - | keep/scar |
| 3.5 | yes | none (practice) | - | keep/scar |
| 4.1 | no | claim_check.py | Thread-B D7-02: scripted voice fabricated a weight, now gated off by default | keep/field |
| 4.2 | no | none | - | keep/bare - flagged with 2.8: no scar, no tool, no citation |
| 4.3 | no | none | DSH independently validates at every model/tool JSON boundary (convergence, not a save) | keep/bare |
| 4.4 | no | none | - | keep/bare |
| 4.5 | no | none | - | keep/bare |
| 4.6 | no | none | Thread-D ships tamper-evident receipts per committed action (backflow item 5) | keep/field |
| 5.2 | no | none | Thread-A retracted 8 promoted results rather than let demo numbers stand | keep/field |
| 6.1 | yes | ops-drill skill | - | keep/scar |
| 6.2 | yes | none | - | keep/scar |
| 6.6 | yes | obsgate.py | entered the doctrine two days before this round | too young - just entered, not a candidate by construction |
| 7.3 | yes | none | Thread-G runs worktree-per-agent in practice | keep/scar |
| 7.5 | no | none | this session's parallel-session collision is a 7.5-shaped event, but it was filed under 7.1 (R8-2) - the shared-logbook lesson landed on the orient rule this time | keep/bare |
| 8.5 | no | none (stance) | round 7's backflow register is 8.5 operating: first outside contact adding what nothing here anticipated | keep - a stance, not a checkable practice; candidate for rewording, never for deletion by silence |

Tallies of the 24: 6 field-evidenced, 7 scar-backed with their domain
unentered by any round, 9 bare, 1 too young (6.6), 1 stance (8.5). Deleted:
none.

The bare nine are the real product of this reading: no inline scar, no field
evidence, no citation, resting on the origin record alone. They are not
deletion candidates today - the clock has not run - but 8.1 will come for
them first when it can legitimately ask. 2.8 and 4.2 are the honest first
tests: 2.8's mechanism is installed in every adopting repo and has never
recorded a catch; 4.2 has nothing behind it but the origin record's memory.
7.5 sits among them by an accident of filing - the collision that would have
cited it landed on 7.1 - and is the clearest case where the never-cited list
undercounts a rule's real activity.

## Corrected premises

- **"The deletion-candidate list is evidence about the rules."** It was
  evidence about the instrument. The recorder mechanised the round-count
  half of 8.1's evidence floor and silently dropped the time half, so the
  gate was satisfiable without the rule's condition being met - a check
  cheap to satisfy and expensive to verify, trusted because it printed. The
  same class as the vacuous `--selfcheck` the maintainer's round 4 caught,
  one layer up: this time the vacuous check was inside the tool that audits
  the rules.
- **"Closed and retracted are the same bookkeeping."** They differ by
  exactly one thing: whether the save was real. R6-12 (fact true, diagnosis
  wrong) closes and keeps its save; R6-13 (fact false) retracts and gives it
  back. Round 7 could not express that distinction and asked readers to hold
  a discount in their heads; the ledger now holds it.

## Harness gotchas

- The deletion-candidate list stays refused until the recorded history spans
  60+ days. When it returns, read it against the disposition table above -
  that is what the table is for.
- The register sweep verified R3-1 and R4-5 already closed in the maintainer's
  round 5, per 7.2 (trust the tree, not the doc) - not re-closed here.

## What we ruled out

- **Deleting any rule.** 8.1's own condition is unmet on nine days of
  history, and where evidence exists at all (the thread ledgers), it runs in
  the uncited rules' favour. Deleting on this record would have been the
  recorder's premature list acted on at face value - the exact failure R8-1
  names.
- **Citing convergence or field adoption as saves.** Thread-B's port of
  `expectEffect` and DSH's boundary validation appear in the disposition
  column, not the findings table, for round 6's stated reason: counting
  agreement as a save corrupts the attribution 8.1 depends on. A save
  requires a defect surfaced here, in this logbook.
- **Backfilling the missing scars this round.** R8-3 stays deferred. The
  scars exist in the origin build record; recovering them is archaeology
  worth one focused pass, not a footnote to a deletion round.

## Stop decision (doctrine 8.3)

CONTINUE - round 7 carried two HIGH, this round none, and no two consecutive
quiet rounds exist on the true history.

The cleanup this round asked for is done, and its yield was characteristic:
the mess was not the rules, it was the instrument that named them and the
register rows nobody had swept against the tree. Both are now smaller than
they were found. What remains for a future round is the backflow register
(six items, untouched by design this round) and the bare rules above, whose
day comes when the clock has honestly run.
