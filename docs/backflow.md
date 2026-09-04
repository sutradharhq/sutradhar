# Backflow register

The doctrine here was distilled from several independent build threads. Those
threads did not stop. They kept inventing, and for seven rounds nothing carried
the inventions home: four of them had independently solved problems this
doctrine still listed as open, and the distillation was quietly behind its own
sources. That is finding **R7-1**, filed high and deferred, and it stayed
deferred because recording an owed item cost nothing — so it sat.

This register is the mechanism R7-1 asked for. It is gated:

```bash
python python/sutradhar_guards/rounds.py docs/rounds/ --backflow docs/backflow.md
```

An item whose **by-round** has arrived and which is still `owed` or `deferred`
**fails the gate**. There are exactly three ways out, and all of them are
decisions: adopt it, reject it with a reason, or re-defer it to a later round
with a reason. Nothing here can quietly wait. That is the whole point — every
crossing that happened before this register existed happened as a side-effect
of somebody building a tool, never because anyone decided.

## Columns

| column | meaning |
|---|---|
| `id` | `B-<n>`, stable forever |
| `source` | the thread it came from, using the `Thread-A…K` labels of `docs/rounds/round-007.md` |
| `what` | the innovation, in one line |
| `evidence` | `scar` — an incident with a recorded cost. `practice` — a documented intention with no recorded cost |
| `rule` | the doctrine rule it lands in, or `new` for a proposed rule |
| `status` | `owed` / `adopted` / `rejected` / `deferred` |
| `by-round` | the round by which it must be decided |
| `note` | required for `rejected` and `deferred` |

**The `evidence` column is load-bearing.** Doctrine 8.1 says a rule enters with
the incident that paid for it, and a charter, protocol or ADR is an intention,
not an incident. So a `practice` item may strengthen the *mechanism* of a rule
that already carries a scar; it may not found a new one. The gate enforces
that: `practice` + `new` is refused. This is the discipline that stops a survey
of well-run repos from inflating the doctrine with things nobody has paid for.

`Thread-K` is an eleventh thread, younger than the ten surveyed in round 7 and
not present in that record's table.

**Round 14 is the register's first round.** Three items were decided in it -
the two adopter-reported defects and the rule four threads had each invented
separately. The rest carry round 15 or 16, and the gate will refuse them then.

**Round 15 is the first round the gate actually refused.** Ten items came
due; one was adopted (B-15, by the pre-commit hook naming the tree it
measured) and nine were re-deferred with reasons. That ratio is recorded as
finding **R15-4** rather than left to read as routine: every reason is real
and written down, and a mechanism whose first enforced deadline is met by
moving 90% of it has not yet changed behaviour. Round 16 owes a decision on
the section-5 batch - B-7, B-10 and B-18 - and B-10 has now been deferred
twice while owed since round 7.
The five items inherited from round 7 — B-10 (R7-5), B-11 (R7-7), B-12
(R7-4 and R7-9), B-13 and B-14 — had no deadline at all for seven rounds,
which is the difference this file is meant to make.

## The register

| id | source | what | evidence | rule | status | by-round | note |
|---|---|---|---|---|---|---|---|
| B-1 | Thread-B | `expectEffect` is blind to form state: `innerText` reports neither an input's value nor a button's disabled attribute, so the highest-stakes surface it is pointed at was the one it could not see | scar | 3.1 | adopted | 14 | landed as `readFormState` with a node selftest over the compiled source; mutation-verified |
| B-2 | Thread-B | `swallow_lint` walked vendor trees, so ~80 third-party findings buried the one real one and the guard was switched off that afternoon | scar | 2.1 | adopted | 14 | walk now excludes vendor dirs, reports the skip count, still honours an explicitly named path |
| B-3 | Thread-B, Thread-A, Thread-K, Thread-H | a check that cannot measure must refuse rather than pass — four threads invented this separately | scar | 2.9 | adopted | 14 | landed as rule 2.9; the tooling already knew it (33 INCONCLUSIVE references across `verify_guard` and `obsgate`) while the doctrine said it once, in passing |
| B-4 | Thread-A | a job that succeeds and produces nothing: a training loop ran 30 days at 0 rows under green status, because 6.6 counts jobs fired/succeeded/failed and a silent zero is a success | scar | 6.6 | deferred | 17 | re-deferred to 17: this is an obsgate change (a job that succeeded and produced nothing must not read as success), and it needs the thread's two mechanism halves ported rather than reinvented from the one-line summary |
| B-5 | Thread-F | a golden file is a regression pin, not an oracle — theirs froze the engine's own output, locking in the bugs it was meant to catch | scar | 2.5 | deferred | 16 | cheap: `golden.py` grows a required `oracle` field, valued `independent` or `pin`. Re-deferred once, to round 16, as the first item of that round rather than a rider on round 15's session-hook thread |
| B-6 | Thread-B | a contract gate across a process boundary: all six client upload purposes 400'd against the API, the error was swallowed, and three downstream features silently no-op'd. Neither side's tests could see it — the API's used valid values, the client's stubbed the service | scar | 2.3 | deferred | 17 | re-deferred to 17: a contract gate across a process boundary has no owner in this repo - neither side's tests can see the seam, which is the finding. It needs a thread that holds both sides, and naming a round for it here would be a deadline nobody can meet |
| B-7 | Thread-K | a provenance tier per value, where a derived value inherits its weakest input's tier | scar | 5.1 | deferred | 16 | re-deferred to 16 with B-10 and B-18 as one section-5 batch. Deciding these one at a time has produced no crossing in eight rounds; per-value tiers, retraction and coverage-of-the-number are one mechanism argued three ways |
| B-8 | Thread-A, Thread-H, Thread-E | pre-registration with both a kill condition and a void condition — two validation windows were voided as "the protocol working, not a failure" | scar | 6.4 | deferred | 16 | re-deferred to 16: 6.4 already says prove the null; the addition is a VOID condition, which needs a worked pre-registration example in `docs/` before it means anything mechanically |
| B-9 | Thread-A | information-availability timestamps, so a backfill cannot date historical data to `now()` | scar | 2.5 | owed | 16 | second thread to invent this independently |
| B-10 | Thread-A | retraction as code: an RCA retracted 8 already-promoted results, and section 5 has no name for withdrawing a published number | scar | 5.1 | deferred | 16 | re-deferred to 16 in the section-5 batch with B-7 and B-18. This is R7-5, owed since round 7 - the second time it has been re-deferred, which is recorded as R15-4 rather than left to look routine |
| B-11 | Thread-E | ADR supersession chains carrying `Extends (does not revoke)` | practice | 7.4 | owed | 16 | R7-7. `practice`, so it may only strengthen 7.4's mechanism — it cannot found a rule |
| B-12 | Thread-B | four-tier evidence tags `[V] [R] [I] [GAP]` on every ledger row, against this repo's binary provenance label | practice | 5.1 | owed | 16 | R7-4's concrete form: adopting `rounds.py` currently asks this thread to downgrade |
| B-13 | Thread-B | a Playwright port of `expectEffect`, written because the shipped Cypress template "could not run" in a pnpm monorepo | scar | 3.1 | deferred | 16 | re-deferred to 16, where it belongs with the plugin's own distribution question: round 15 shipped a Claude Code plugin and did not touch the Cypress helper's portability, which is the same class of gap one layer down |
| B-14 | Thread-D | a tamper-evident receipt on every routing decision and committed action | scar | 4.6 | owed | 16 | the mechanism is the private product's seed; only the genericized rule belongs here |
| B-15 | Thread-A | a gate must prove it gated the tree you are pushing, not some tree | scar | 2.2 | adopted | 15 | adopted in round 15 by the pre-commit hook: the gate reads the working tree, `git commit` takes the index, and the hook now NAMES which one it measured and lists the staged paths that differ. Stashing or checking out the index would gate the exact committed tree and is refused - a gate that can lose someone's work is not an improvement |
| B-16 | Thread-A | a file-ownership manifest for parallel agents | scar | 7.3 | owed | 16 | 7.3 states the rule and ships no mechanism; this is the mechanism |
| B-17 | Thread-B | presence-based coverage is not coverage — an i18n check counted keys present, not keys reachable | scar | 3.6 | owed | 16 | 3.6 already says selector counting measures nothing; this is the same defect in a second surface, which is evidence the rule needs a mechanism and not just a sentence |
| B-18 | Thread-H | coverage is part of the number: a metric that omits part of the delivered surface reports a real fix as a no-op | scar | 5.1 | deferred | 16 | re-deferred to 16 in the section-5 batch with B-7 and B-10; the maintainer's standing doctrine already carries this as a scar, so B-19's reconciliation is its natural carrier |
| B-19 | — | this repo's public `DOCTRINE.md` lags the maintainer's standing doctrine, and the two have diverged in section 2 as well. Two independent agents cited a section 6 rule that does not exist here | scar | 8.1 | deferred | 16 | re-deferred to 16. The blocker is not effort but the numbering hazard: 89 findings resolve against these ids, so reconciliation must ADD ids and never renumber. Round 16 owes the append-only plan, not the merge |
