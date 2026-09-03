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
The five items inherited from round 7 — B-10 (R7-5), B-11 (R7-7), B-12
(R7-4 and R7-9), B-13 and B-14 — had no deadline at all for seven rounds,
which is the difference this file is meant to make.

## The register

| id | source | what | evidence | rule | status | by-round | note |
|---|---|---|---|---|---|---|---|
| B-1 | Thread-B | `expectEffect` is blind to form state: `innerText` reports neither an input's value nor a button's disabled attribute, so the highest-stakes surface it is pointed at was the one it could not see | scar | 3.1 | adopted | 14 | landed as `readFormState` with a node selftest over the compiled source; mutation-verified |
| B-2 | Thread-B | `swallow_lint` walked vendor trees, so ~80 third-party findings buried the one real one and the guard was switched off that afternoon | scar | 2.1 | adopted | 14 | walk now excludes vendor dirs, reports the skip count, still honours an explicitly named path |
| B-3 | Thread-B, Thread-A, Thread-K, Thread-H | a check that cannot measure must refuse rather than pass — four threads invented this separately | scar | 2.9 | adopted | 14 | landed as rule 2.9; the tooling already knew it (33 INCONCLUSIVE references across `verify_guard` and `obsgate`) while the doctrine said it once, in passing |
| B-4 | Thread-A | a job that succeeds and produces nothing: a training loop ran 30 days at 0 rows under green status, because 6.6 counts jobs fired/succeeded/failed and a silent zero is a success | scar | 6.6 | owed | 15 | both mechanism halves already exist in the thread |
| B-5 | Thread-F | a golden file is a regression pin, not an oracle — theirs froze the engine's own output, locking in the bugs it was meant to catch | scar | 2.5 | owed | 15 | cheap: `golden.py` grows a required `oracle` field, valued `independent` or `pin` |
| B-6 | Thread-B | a contract gate across a process boundary: all six client upload purposes 400'd against the API, the error was swallowed, and three downstream features silently no-op'd. Neither side's tests could see it — the API's used valid values, the client's stubbed the service | scar | 2.3 | owed | 15 | 2.3 says test through the real seam; this seam has no single process, which is the gap |
| B-7 | Thread-K | a provenance tier per value, where a derived value inherits its weakest input's tier | scar | 5.1 | owed | 15 | the strong form of what 5.1 has owed since round 7 |
| B-8 | Thread-A, Thread-H, Thread-E | pre-registration with both a kill condition and a void condition — two validation windows were voided as "the protocol working, not a failure" | scar | 6.4 | owed | 15 | |
| B-9 | Thread-A | information-availability timestamps, so a backfill cannot date historical data to `now()` | scar | 2.5 | owed | 16 | second thread to invent this independently |
| B-10 | Thread-A | retraction as code: an RCA retracted 8 already-promoted results, and section 5 has no name for withdrawing a published number | scar | 5.1 | owed | 15 | this is R7-5, owed since round 7 and undecided until this register existed |
| B-11 | Thread-E | ADR supersession chains carrying `Extends (does not revoke)` | practice | 7.4 | owed | 16 | R7-7. `practice`, so it may only strengthen 7.4's mechanism — it cannot found a rule |
| B-12 | Thread-B | four-tier evidence tags `[V] [R] [I] [GAP]` on every ledger row, against this repo's binary provenance label | practice | 5.1 | owed | 16 | R7-4's concrete form: adopting `rounds.py` currently asks this thread to downgrade |
| B-13 | Thread-B | a Playwright port of `expectEffect`, written because the shipped Cypress template "could not run" in a pnpm monorepo | scar | 3.1 | owed | 15 | the only thread that actually uses the helper had to port it first — a distribution defect, not a design one |
| B-14 | Thread-D | a tamper-evident receipt on every routing decision and committed action | scar | 4.6 | owed | 16 | the mechanism is the private product's seed; only the genericized rule belongs here |
| B-15 | Thread-A | a gate must prove it gated the tree you are pushing, not some tree | scar | 2.2 | owed | 15 | sibling of 2.2's mutation requirement, aimed at the gate's subject rather than its sensitivity |
| B-16 | Thread-A | a file-ownership manifest for parallel agents | scar | 7.3 | owed | 16 | 7.3 states the rule and ships no mechanism; this is the mechanism |
| B-17 | Thread-B | presence-based coverage is not coverage — an i18n check counted keys present, not keys reachable | scar | 3.6 | owed | 16 | 3.6 already says selector counting measures nothing; this is the same defect in a second surface, which is evidence the rule needs a mechanism and not just a sentence |
| B-18 | Thread-H | coverage is part of the number: a metric that omits part of the delivered surface reports a real fix as a no-op | scar | 5.1 | owed | 15 | |
| B-19 | — | this repo's public `DOCTRINE.md` lags the maintainer's standing doctrine, and the two have diverged in section 2 as well. Two independent agents cited a section 6 rule that does not exist here | scar | 8.1 | owed | 15 | **numbering hazard**: reconciling them must not renumber published rule ids — `rounds.py` resolves every finding's citation against this file, and 89 findings cite them |
