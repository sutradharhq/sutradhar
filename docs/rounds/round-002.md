# Round 2 - 2026-08-08

Lenses: self-application, docs-vs-code honesty, pedagogy

**What this round was.** The second half of the v0.3 pass: the flight
recorder and the worked example. Recorded because it produced real findings
against real code, and because a recorder with a fabricated history would be
the exact defect 5.2 names.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R2-1 | med | 2.2 | rounds selfcheck | fixed | round-heading regex lacked re.MULTILINE, so no round record was ever parsed and an empty history reported as cheerfully as a real one |
| R2-2 | med | 6.4 | building the example | fixed | the example's CI comment named BILLING_TESTS, satisfying the textual skip-gate audit and making the demo pass vacuously |
| R2-3 | low | 8.2 | review | fixed | a stale "planned" entry for a shipped item survived in the roadmap; the doc contradicted the tree |
| R1-7 | med | 2.2 | - | deferred | verify_guard still mechanises only the revert half of 2.2 |
| R1-8 | med | 1.1 | - | deferred | budget enforcement detection remains a text match |
| R1-9 | low | 1.1 | - | deferred | budget latency check remains a single-sample ceiling |

## Corrected premises

- **"A demo is a low-risk artifact."** It is the opposite. A walkthrough
  that has silently stopped catching its planted defects fails in front of
  the one person whose opinion the repo is trying to earn. R2-2 was that
  failure in miniature, caught only because the runner was written to fail
  loudly rather than report what it found.
- **"The refusals are edge cases."** In the flight recorder they turned out
  to be the product. A reporter that always answers confidently would make
  8.1 delete doctrine rules on the strength of a quiet week, so the thin-data
  refusal is the load-bearing behaviour and the selfcheck guards it hardest.

## Harness gotchas

- All four tools now ship a `--selfcheck`; run them before trusting any
  green suite, because three of the four found a real defect in their own
  first run.
- Every verification in rounds 1 and 2 was performed by the author. That is
  the WEAKER form (ops-drill rule 7). No outside mind has read this code.

## Stop decision (doctrine 8.3)

v0.3 closes here at four of seven planned items. Items 5-7 remain unbuilt
deliberately: the marginal value of another tool is now below the value of
one outside reader, and every claim in this repo has been validated against
a single codebase by a single reviewer. Restarting is justified by evidence
from someone else's repo, not by the backlog still having entries.

**Note the disagreement, because it is instructive.** `rounds.py` reports
CONTINUE on this same history, and it is right to. The tool mechanises 8.3's
*convergence* half - two consecutive rounds with zero HIGH findings, which
has not happened - and that is the half about whether the HARDENING loop has
run dry. We are stopping on the other half of 8.3, the one about the next
cheapest activity, which no tool here computes because it needs a comparison
against work outside the repo entirely.

So: the recorder is not being overruled, it is being read for what it
measures. A tool that had answered REST here would have been agreeing with a
decision it has no evidence for, which is the failure mode the thin-data
refusal exists to prevent. Recorded rather than smoothed over, because a
framework whose own artifacts quietly disagree with its actions is back to
being ceremony.
