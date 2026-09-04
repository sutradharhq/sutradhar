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
| R17-2 | med | 6.7 | ratchet, on merge | fixed | the August branch `guard/dead-route-assertions` was merged this round (two commits, `24ef4d3` and `5dd0294`: `dead_route_lint.py`, its tests, rule 3.7). Two ratchets written after the branch refused it: its selfcheck exited 0 and printed nothing, so a pass could not be told from a check that never ran; and it ignored an unknown flag, so `--selfcheck` proved only that the module imported. Both are the 6.7 class the ratchets exist for, on a guard whose subject is assertions that cannot fail. Fixed: the selfcheck names the pairs it exercised, and the CLI refuses an unknown argument with exit 2, matching `detectors.py` |

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

## Merged: `guard/dead-route-assertions`

The one open branch on the remote, authored in August and 35 commits behind
main, carried a guard and a rule: `dead_route_lint.py` (a weak-assertion
detector and a dead-route detector, route-source agnostic) and doctrine
3.7, *an assertion that cannot fail is not a test - and the target must
exist*. It was merged rather than rebased, so its two commits keep their
dates and their `Guard-cmd`-less history.

3.7 was read against 3.6 and 2.2 before merging. 3.6 mentions dead routes in
one parenthesis; 2.2 is about fixes. 3.7 carries the weak-assertion half
that exists nowhere else, its own scar (44 assertions, 28 aimed at nothing,
months of green), and its own mechanism, so it enters as a rule and not as
a sentence on 3.6. Section 3 now has seven rules; the count is 49.

The merge conflicted in two files: `__init__.py`, where main had replaced
eager imports with a lazy export table (the two functions were added to the
table), and `CHANGELOG.md` (both entries kept). The guard was wired into
`bootstrap.sh` (the `python` layer copies it to `tests/sutradhar/`), both
selfcheck lists in CI, and the README tree. Mutation: with the
weak-assertion regex replaced by one that never matches, the selfcheck exits
1 and two of its eight tests go red.

## Guards touched

`dead_route_lint.py`, merged and given a real command line (R17-2).
`rounds.py --backflow` goes green by decision, not by code.
