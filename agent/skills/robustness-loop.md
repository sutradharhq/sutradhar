# Skill: robustness loop - one adversarial depth sweep

A repeatable procedure for hardening a codebase with an agent. Hand this
file to the agent verbatim ("run one robustness round") on a recurring
schedule. The goal of a round is NOT a report: it is fixed code, with
guards, with the residual register smaller than you found it, and a record
that stops the next round from re-diagnosing anything you touched.

On the codebase this framework distills, 25+ of these rounds found (among
much else): a cross-tenant billing leak, an 11x metric overstatement, a
purge that deleted nothing while reporting success, and a detector whose
"never fires" guard was a tautology that could never fire. Converged areas
regrew defects within a few rounds; the loop is a standing guard pass, not
a one-time audit.

## Ground rules (non-negotiable)

1. Every fix ships with a GUARD in the same commit. Preference order:
   extend an existing class ratchet, then add a case to an existing themed
   test file, then a new per-defect pin only when subtle arithmetic demands
   it. At most one NEW ratchet file per round.
2. Honest labels everywhere: simulated stays marked simulated, degrade
   paths say they degraded. A number in a doc you cannot verify gets marked
   ESTIMATE or measured, never left as a confident unverified claim.
3. One worktree per agent if running as a subagent. Stage named files only.
4. Finish the full scope. Do not stop after a subset to ask whether to
   continue; do not end a phase with "next I would" - do it.
5. Bounded waits only, no endless polling.

## Phase 0: harness

Stand up the test environment ONCE and keep it warm for the whole round.
Record the exact invocation. Write down every harness fact that costs more
than five minutes to learn (mounts, env vars, known-slow suites) in the
round record; the next round starts from that list.

## Phase 1: baseline before touching anything

Run the FULL suite in every tier (default, integration-gated, any
separately-run nets) and record the exact counts and exit codes.

- A truncated run looks like a pass. Exit 137 with a green tail is a KILLED
  run. Compare passed+skipped against the expected total every time.
- Audit the SKIP GATES, not just the failures: for every env-gated tier,
  verify something actually sets the variable. A skip marker nothing sets
  is indistinguishable from a deleted test. (This exact audit found ~86
  tests, including an entire billing arithmetic, running in NO environment
  while the suite reported green.)
- Any failure at baseline is a real finding of this round. Triage it before
  writing new code.

## Phase 2: orient

Read the residual register (the round-over-round backlog), the previous
round's record, and the recent commit log. Closed items are closed; do not
re-flag them.

## Phase 3: fan out adversarial lenses

Pick 3 to 5 lenses this round; ROTATE so consecutive rounds differ (a
rested lens regrows findings). The proven set:

- **Dead features**: documented + gated + tested, yet never runs. Grep for
  helpers with zero production callers, tests that monkeypatch renamed
  functions, artifacts that load but error on use.
- **Authz/tenancy**: cross-boundary reads via IDs, routes missing the scope
  guard, fail-open on cache outage.
- **Numeric correctness**: cumulative vs interval confusion, unit and
  timezone drift, boundary rows dropped at batch seams.
- **Concurrency/failure injection**: cursor-advance vs durable-write
  ordering, races on upsert, idempotency of retries. Inject the failure and
  look for a fail-safe default that reads as success.
- **Scale**: every "works fine" was observed at demo scale. Hunt unbounded
  queries, N+1 sweeps, sync work on async paths. The nastiest shape: an
  unbounded query whose timeout is swallowed into an empty result - a
  silently WRONG answer, not an error.
- **Docs-vs-code honesty**: claims the code no longer supports, unverified
  numbers stated as fact.
- **Test quality**: tests that are green but cannot fail. Assertions that
  do not discriminate, guards unit-tested as helpers but never through a
  route, golden files with no re-baseline trail.

## Phase 4: verify the premise, then fix

- Check the premise against the code before implementing; backlog
  one-liners are wrong in both directions.
- Prove pre-existing vs regression before touching a failure: run the same
  test at the baseline commit in a scratch worktree.
- Fix standards: pure functions stay pure, honest degrade over silent
  fallback, all-or-nothing semantics on multi-part writes, tests for the
  pathological cases (wraparound, reset, out-of-order, first-item), not
  just the happy path.
- Test through the ROUTE. A helper-level unit test cannot see a NameError
  in the handler.
- Fix your own guard rather than allowlisting around it. A net that cries
  wolf gets muted, and a muted net is worse than none.
- Delete your own unreachable code; the honest move is subtraction.

## Phase 5: verify like you do not trust yourself

- Rerun touched suites AND a known-good neighbor suite in one invocation
  (shared failure means harness, not regression).
- For data fixes, verify in the datastore directly, independent of test
  assertions.
- End the round with the full suite green, exit 0, exact counts recorded.

## Phase 6: record, commit, close

1. Write the round record to `docs/rounds/round-NNN.md`. Prose first - the
   record is a document people read - with one machine-readable table so the
   flight recorder can compute the stop rule, the residual register, and
   which doctrine rules earned their keep:

   ```markdown
   # Round 7 - 2026-08-08

   Lenses: authz, numeric, scale

   | id | severity | rule | found-by | status | summary |
   |---|---|---|---|---|---|
   | R7-1 | high | 2.7 | swallow-lint | fixed | metering read swallowed to {} |
   | R7-2 | med  | 2.6 | scale lens   | deferred | sweep uncapped above 50k |
   | R6-3 | med  | 3.1 | -            | closed | picker effect asserted |
   ```

   `severity` is high/med/low, `status` is fixed/deferred/closed, `rule` is
   a doctrine id or `-`. **Fill the `rule` column**: it is the only record of
   which rule caught what, and doctrine 8.1 cannot prune the doctrine
   without it. A round that found nothing still writes the table with no
   rows - that is what distinguishes "we looked and found nothing" from
   "nobody wrote it down".

2. The residual register is now derived, not maintained by hand: a deferred
   finding stays open until a later round lists the same id as closed or
   fixed. Strike nothing manually; close it in the next record.
3. Then the prose the record has always carried: corrected premises (they
   matter more than the fixes), and harness gotchas.
4. Run the recorder and read what it says before deciding to run another
   round:

   ```bash
   python scripts/rounds.py docs/rounds/ --floors .
   ```
5. Commit messages carry the why and the evidence, one logical change per
   commit.

## Exit criteria

The loop rests when two consecutive full rounds surface zero HIGH findings.
Then it runs on a longer cadence, because converged areas regrow.

That criterion is now computed rather than remembered: `rounds.py` reads the
round records and answers CONTINUE, REST, or INSUFFICIENT. Ask it every
round. *The scar behind doctrine 8.3 is that it took 24 rounds before anyone
asked whether the next one was worth running; the tool asks for you, and it
refuses to answer at all on fewer than two rounds rather than guessing.*
