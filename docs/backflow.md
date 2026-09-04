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

**Round 16 did not answer it.** Thirteen items came due at round 16 - B-5,
B-7, B-8, B-9, B-10, B-11, B-12, B-13, B-14, B-16, B-17, B-18 and B-19 - and
round 16 was a security round that decided none of them. The gate is
therefore RED, deliberately, and the round record says so out loud rather
than moving thirteen deadlines to make it green. Moving them is exactly the
behaviour R15-4 was filed to stop, and a register that clears itself by
re-deferring is the mechanism failing while reporting success. Deciding the
thirteen is round 17's first job.

**Round 17 decided all thirteen, and the two that came due on recording it
(B-4, B-6).** The rule given was: adopt unless the item is redundant with a
rule already here or narrows the harness. Thirteen were adopted into the
doctrine in one commit (2.3, 2.5, 3.6, 4.6, 5.1, 6.4, 6.6, 7.3, 7.4, and the
five rules 6.7-6.11 that B-19 owed). Two - B-13 and B-16 - are
decided as ADOPT and re-deferred to round 18 because each is a mechanism to
build, not a sentence to write, and a row marked `adopted` with nothing built
would be the register lying. None was rejected: nothing in the thirteen
duplicated a rule, and none constrains what an adopter may build.

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
| B-4 | Thread-A | a job that succeeds and produces nothing: a training loop ran 30 days at 0 rows under green status, because 6.6 counts jobs fired/succeeded/failed and a silent zero is a success | scar | 6.6 | adopted | 17 | round 17: 6.6 now says a job's success carries its output count and a silent zero is a failure. The obsgate half - a rows-per-run floor as a first-class check - is not ported; `obsgate --effects increased` already witnesses a counter that must rise after an action, which is the mechanism's nearer half |
| B-5 | Thread-F | a golden file is a regression pin, not an oracle — theirs froze the engine's own output, locking in the bugs it was meant to catch | scar | 2.5 | adopted | 17 | round 17: 2.5 gained the sentence and the scar. The `oracle` field for `golden.py` is not built; the rule is the crossing, the field is a later mechanism |
| B-6 | Thread-B | a contract gate across a process boundary: all six client upload purposes 400'd against the API, the error was swallowed, and three downstream features silently no-op'd. Neither side's tests could see it — the API's used valid values, the client's stubbed the service | scar | 2.3 | adopted | 17 | round 17: 2.3 now says a cross-process contract is tested by one test that crosses it. The gate itself has no owner here, as the round-15 note said; the rule is the crossing, and an adopter with both sides in one repo builds the test |
| B-7 | Thread-K | a provenance tier per value, where a derived value inherits its weakest input's tier | scar | 5.1 | adopted | 17 | round 17: 5.1 is now per value, weakest input wins, with B-12's gap marker folded in |
| B-8 | Thread-A, Thread-H, Thread-E | pre-registration with both a kill condition and a void condition — two validation windows were voided as "the protocol working, not a failure" | scar | 6.4 | adopted | 17 | round 17: 6.4 gained the pre-registered kill AND void condition. The worked example the round-15 note asked for is still owed by whoever next runs a validation window |
| B-9 | Thread-A | information-availability timestamps, so a backfill cannot date historical data to `now()` | scar | 2.5 | adopted | 17 | round 17: 2.5 gained the availability-timestamp sentence |
| B-10 | Thread-A | retraction as code: an RCA retracted 8 already-promoted results, and section 5 has no name for withdrawing a published number | scar | 5.1 | adopted | 17 | round 17: 5.1 names retraction as a status of its own. Owed since round 7 (R7-5), deferred twice, landed |
| B-11 | Thread-E | ADR supersession chains carrying `Extends (does not revoke)` | practice | 7.4 | adopted | 17 | round 17: 7.4 gained the extends/revokes practice sentence, labelled practice, founding nothing |
| B-12 | Thread-B | four-tier evidence tags `[V] [R] [I] [GAP]` on every ledger row, against this repo's binary provenance label | practice | 5.1 | adopted | 17 | round 17: folded into B-7's sentence in 5.1 as the gap marker; the four-letter tag set itself is the thread's spelling, not the rule |
| B-13 | Thread-B | a Playwright port of `expectEffect`, written because the shipped Cypress template "could not run" in a pnpm monorepo | scar | 3.1 | deferred | 18 | decided in round 17: ADOPT. A port is work, not a sentence; it lands with the JS kit in round 18 and this row closes when it does. Re-deferred with the decision made, which is not the R15-4 shape |
| B-14 | Thread-D | a tamper-evident receipt on every routing decision and committed action | scar | 4.6 | adopted | 17 | round 17: 4.6 gained the genericized rule - a consequential action leaves a tamper-evident record - and nothing of the mechanism |
| B-15 | Thread-A | a gate must prove it gated the tree you are pushing, not some tree | scar | 2.2 | adopted | 15 | adopted in round 15 by the pre-commit hook: the gate reads the working tree, `git commit` takes the index, and the hook now NAMES which one it measured and lists the staged paths that differ. Stashing or checking out the index would gate the exact committed tree and is refused - a gate that can lose someone's work is not an improvement |
| B-16 | Thread-A | a file-ownership manifest for parallel agents | scar | 7.3 | deferred | 18 | decided in round 17: ADOPT. 7.3 now names the manifest as its mechanism; the guard that refuses a foreign-owned path lands in round 18 and closes this row |
| B-17 | Thread-B | presence-based coverage is not coverage — an i18n check counted keys present, not keys reachable | scar | 3.6 | adopted | 17 | round 17: 3.6 gained the scar. The mechanism the round-15 note asked for is the reachability half of 3.6, still prose |
| B-18 | Thread-H | coverage is part of the number: a metric that omits part of the delivered surface reports a real fix as a no-op | scar | 5.1 | adopted | 17 | round 17: landed as 6.10 through B-19's reconciliation, with the scar |
| B-19 | — | this repo's public `DOCTRINE.md` lags the maintainer's standing doctrine, and the two have diverged in section 2 as well. Two independent agents cited a section 6 rule that does not exist here | scar | 8.1 | adopted | 17 | round 17: 6.7-6.11 appended from the standing doctrine, ids added and none renumbered, so all 89 findings still resolve. Section 2 is a superset here (2.7-2.9) and differs by one sentence in 2.2; nothing to sync |
| B-20 | — | `interpolation_lint` sees f-string interpolation into a query-language string and not `%`-format: `"SELECT ... = '%s'" % name` is the same hole in an older spelling and passes clean | practice | 2.8 | owed | 18 | R16-5, and `practice` because nothing has been paid for it yet - it is a detector gap found by review, not an incident. 2.8 already carries its own justification, so this may only strengthen the mechanism. Round 18 rather than 17 because round 17 already owes the thirteen items that came due at 16, and a deadline nobody can meet is not a deadline |
| B-21 | — | mutate what RUNS, not what you can see: a mutation applied to a declaration, a constant or a non-executing string reports "no change", which reads as "the guard is decoration" and means "the mutation never ran" | practice | 2.2 | owed | 18 | R16-6, third occurrence across rounds 13-15. `practice`: the cost is wasted review time and one nearly-wrong verdict, not a recorded incident, so it cannot found a rule - 2.2 already says revert the fix and watch it go red. What it can strengthen is the mechanism: the mutation step in `agent/skills/robustness-loop.md` should require naming the line that executes before editing it, and the round record should carry the command that showed the mutant red |
