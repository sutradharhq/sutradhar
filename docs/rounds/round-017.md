# Round 17 - 2026-09-05

Lenses: backflow, doctrine reconciliation

**What this round was.** Round 16 left the backflow gate red on purpose:
thirteen register items were overdue and a security round had decided none
of them. This round decided all thirteen - and B-4 and B-6, which came due the
moment round 17 was recorded - under one rule from the maintainer: adopt unless the item is redundant with a rule already in
`DOCTRINE.md` or narrows what an adopter may build. Nothing was rejected.
Thirteen landed as doctrine text in one commit; two are mechanisms to build
and are re-deferred with the decision written down (B-13, B-16).

The largest single change is B-19: five rules the maintainer's standing
doctrine has carried for some time - and which two agents in earlier rounds
cited here by number while they did not exist (R14-5) - were appended as
6.7 through 6.11. Ids were added and none renumbered, so every one of the 89
findings across the round records still resolves against the rule it named.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R17-1 | low | 8.1 | self, review | fixed | the two agent packs carried the exit-codes-in-pairs rule under borrowed ids `[6.3, 6.6]`, because the rule that states it (6.7) did not exist in this file. Both packs now cite 6.7. The class is B-19's: a rule that lives in the maintainer's head and not in the doctrine gets cited by whatever number is nearest |

## What each item became

| item | decision | landed in |
|---|---|---|
| B-4 | adopted | 6.6: a job's success carries its output count |
| B-5 | adopted | 2.5: a golden is a pin, not an oracle |
| B-6 | adopted | 2.3: a cross-process contract is tested by one test that crosses it |
| B-7 | adopted | 5.1: tier per value, weakest input wins |
| B-8 | adopted | 6.4: pre-registered kill AND void condition |
| B-9 | adopted | 2.5: availability timestamps on historical data |
| B-10 | adopted | 5.1: retraction is a status of its own |
| B-11 | adopted | 7.4: extends/revokes, labelled practice |
| B-12 | adopted | 5.1, folded into B-7 as the gap marker |
| B-13 | adopt, deferred to 18 | the Playwright port is work, not a sentence |
| B-14 | adopted | 4.6: a consequential action leaves a tamper-evident record |
| B-16 | adopt, deferred to 18 | 7.3 names the manifest; the guard is owed |
| B-17 | adopted | 3.6: the i18n scar |
| B-18 | adopted | 6.10, via B-19 |
| B-19 | adopted | 6.7-6.11 appended, none renumbered |

## What was ruled out (7.4)

- **Rejecting any of the thirteen as redundant.** Each was read against the
  rule it targets. B-17 and B-18 come closest: 3.6 already says selector
  counting measures nothing, and B-18 is 6.10 by another name. B-17 entered
  as a scar on 3.6 rather than a rule, and B-18 entered once, as 6.10, not
  twice.
- **Syncing section 2.** The public section 2 is a superset of the standing
  one (2.7, 2.8 and 2.9 exist only here) and 2.2 differs by one sentence
  that names `verify_guard.py`. No id conflicts, nothing to carry across.
- **Marking B-13 and B-16 `adopted`.** Both are decided; neither is built. A
  row that says `adopted` over an unbuilt mechanism is the register
  reporting success for a decision, which is the defect the register exists
  to catch one level up.
- **Building the `oracle` field for `golden.py` (B-5) in this round.** The
  sentence is the crossing; the field is a later mechanism with its own
  false-positive surface, and this round is records-only.

## Guards touched

None. `rounds.py --backflow` goes green by decision, not by code.
