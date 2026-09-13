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
not present in that record's table. `Thread-L`, added in round 18, is a
twelfth: an adopter thread whose report brought B-22 to B-26, likewise absent
from round 7's table. `Thread-M`, added in round 21, is a thirteenth: a build thread whose report
brought B-27 to B-36. `Thread-A` and `Thread-F` returned in the same round
with B-37 to B-47.

**Round 14 is the register's first round.** Three items were decided in it -
the two adopter-reported defects and the rule four threads had each invented
separately. The rest carry round 15 or 16, and the gate will refuse them then.

**Round 16 did not answer it.** Thirteen items came due at round 16 - B-5,
B-7, B-8, B-9, B-10, B-11, B-12, B-13, B-14, B-16, B-17, B-18 and B-19 - and
round 16 was a security round that decided none of them. The gate was
therefore RED, deliberately, and the round record said so out loud rather
than moving thirteen deadlines to make it green. Moving them is exactly the
behaviour R15-4 was filed to stop, and a register that clears itself by
re-deferring is the mechanism failing while reporting success. Deciding the
thirteen is round 17's first job.

**Round 18 did not answer its four.** Recording round 18 makes B-13, B-16,
B-20 and B-21 overdue, and round 18 was a guards round: it built neither the
Playwright port nor the ownership manifest nor the `%`-format detector. The
gate was RED again, deliberately, and the round record said so out loud
rather than moving four deadlines to make it green - which is R15-4's exact
shape.
Round 18 added three items (B-22, B-23, B-24) and decided none, because an
item recorded with a deadline is what this register is for and a row marked
`adopted` over nothing built is the register lying.

**Round 19 did not answer its eight either,** and said so. Recording round
19 left B-13, B-16, B-20 and B-21 overdue from round 18 and added B-22,
B-24, B-25 and B-26 to the overdue set. Round 19 built one guard and none
of these; it moved no deadline, which is the same refusal rounds 16 and 18
made.

**Round 20 decided all nine, and the gate is GREEN by decision.** Eight were
the overdue set; the ninth, B-23, came due on recording round 20, exactly as
B-4 and B-6 came due on recording round 17. The rule was the round-17 rule
repeated: adopt unless the item is redundant with a rule already here or
would narrow what an adopter may build. Eight adopted - three as doctrine
sentences (2.2, 2.6, 6.6), one as convergence evidence extending a scar
already in 6.6 with no new text (B-24), two as skill text on 6.1 (B-22,
B-23), and two as built mechanisms: `ownership_lint.py` for 7.3 (B-16) and
the `%`/`.format()` half of `interpolation_lint` for 2.8 (B-20). One
rejected: B-13, whose lesson was already adopted as R16-1's class and whose
remainder is a second UI-runtime binding this repository cannot test. The
record is `docs/rounds/round-020.md`.

**Round 21 recorded twenty-one items and decided nineteen of them in the same
round.** The rule was the round-17 rule once more: adopt unless redundant with a
rule already here or narrowing what an adopter may build. Sixteen adopted - five
as mechanisms built in the round (B-27, B-28, B-29, B-31, B-37), three as
sentences inside existing rules (2.2, 4.2, 4.5), two as scar extensions (6.1,
7.2), one as skill text (B-34), and five as convergence with no text at all
(B-39, B-40, B-41, B-43, B-44). Three rejected with reasons (B-35, B-36, B-47).
Two deferred to round 23, each a single instance (B-45, B-46). The record is
`docs/rounds/round-021.md`.

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
| B-13 | Thread-B | a Playwright port of `expectEffect`, written because the shipped Cypress template "could not run" in a pnpm monorepo | scar | 3.1 | rejected | 18 | round 20: REJECTED, and the lesson was already adopted. Its scar is a shipped Cypress template that could not run in a package-manager layout its author had not tried - the class of R16-1, fixed in round 18 by bundling the plugin's guards so an installed copy no longer reaches outside itself. What is left in the row is a Playwright PORT: a second UI-runtime binding this repository cannot run, cannot test, and would ship untested beside the Cypress one, which is the narrows-or-chokes half of the adoption rule. It belongs to the JS kit's own register when that repository exists |
| B-14 | Thread-D | a tamper-evident receipt on every routing decision and committed action | scar | 4.6 | adopted | 17 | round 17: 4.6 gained the genericized rule - a consequential action leaves a tamper-evident record - and nothing of the mechanism |
| B-15 | Thread-A | a gate must prove it gated the tree you are pushing, not some tree | scar | 2.2 | adopted | 15 | adopted in round 15 by the pre-commit hook: the gate reads the working tree, `git commit` takes the index, and the hook now NAMES which one it measured and lists the staged paths that differ. Stashing or checking out the index would gate the exact committed tree and is refused - a gate that can lose someone's work is not an improvement |
| B-16 | Thread-A | a file-ownership manifest for parallel agents | scar | 7.3 | adopted | 18 | round 20: BUILT. `python/sutradhar_guards/ownership_lint.py` reads a `<owner>: <glob> ...` manifest and refuses any staged path another owner claims, naming the owner; an unowned path is allowed and counted; a missing manifest is an instrument condition that exits 0 and says nothing was checked. Wired into bootstrap, both CI selfcheck lists, the READMEs and the plugin's pre-commit gate. NOT a CI step, on purpose: the index is empty in CI, so the step could never fail. Mutation-verified on two lines that run |
| B-17 | Thread-B | presence-based coverage is not coverage — an i18n check counted keys present, not keys reachable | scar | 3.6 | adopted | 17 | round 17: 3.6 gained the scar. The mechanism the round-15 note asked for is the reachability half of 3.6, still prose |
| B-18 | Thread-H | coverage is part of the number: a metric that omits part of the delivered surface reports a real fix as a no-op | scar | 5.1 | adopted | 17 | round 17: landed as 6.10 through B-19's reconciliation, with the scar |
| B-19 | — | this repo's public `DOCTRINE.md` lags the maintainer's standing doctrine, and the two have diverged in section 2 as well. Two independent agents cited a section 6 rule that does not exist here | scar | 8.1 | adopted | 17 | round 17: 6.7-6.11 appended from the standing doctrine, ids added and none renumbered, so all 89 findings still resolve. Section 2 is a superset here (2.7-2.9) and differs by one sentence in 2.2; nothing to sync |
| B-20 | — | `interpolation_lint` sees f-string interpolation into a query-language string and not `%`-format: `"SELECT ... = '%s'" % name` is the same hole in an older spelling and passes clean | practice | 2.8 | adopted | 18 | round 20: BUILT. `interpolation_lint` now reads `%`-formatting and `str.format()` on the same terms as an f-string - literal at the call site, placeholder resolved to its argument, same quoted-position and same-site-escaping rules. `%%` does not shift positional indices; an argument that cannot be matched is judged against all of them, since cannot-tell must not resolve to clean. 2.8 gained one clause naming the two spellings and no rule was added, because `practice` may only strengthen a mechanism |
| B-21 | — | mutate what RUNS, not what you can see: a mutation applied to a declaration, a constant or a non-executing string reports "no change", which reads as "the guard is decoration" and means "the mutation never ran" | practice | 2.2 | adopted | 18 | round 20: 2.2 gained the sentence - mutate the line that RUNS, and a mutation reporting no change more often never executed than found decoration. Labelled practice, founding nothing. Sixth occurrence, and the two most recent are named generically in the scar: a review comparing object representations that embedded the line numbers under test, and a test parametrised over the configuration list it was written to pin, which went from 205 green to 204 green when an entry was deleted |
| B-22 | Thread-L | an operating drill that boots the stack in dependency order and asserts what an OPERATOR would see at each layer, rather than what a health endpoint returns | scar | 6.1 | adopted | 19 | round 20: landed as a SKILL and not a guard, which is the decision rather than a shortcut. 6.1 already states the discipline, and a working drill is inherently application-specific - the layers, gates and commands are the adopter's - so a guard here could only check that a file exists or invent a runtime this framework does not have. `agent/skills/ops-drill.md` now carries the boot shape: dependency order written down first, one layer at a time, and after each layer assert what an OPERATOR would see rather than what the code returns, with a layer that started before its dependency answered named as the class to hunt |
| B-23 | Thread-L | a lockfile that resolves only on the machine that generated it, because platform-specific optional dependencies were pruned out of it | scar | 6.1 | adopted | 20 | round 20: adopted, and it came due on RECORDING round 20 rather than being in the round's brief - the same way B-4 and B-6 came due on recording round 17. Landed beside B-22 in `agent/skills/ops-drill.md`: a lockfile is not numeric truth to be frozen, it makes one claim - a second machine resolves the same tree - and the only thing that tests it is installing on a second machine, from an empty cache, on a different OS or architecture, with the resolved set diffed by command. The register's note put this with the JS kit; that is an argument about where a GUARD would live, and the lesson is a drill shape that needs no lockfile in this tree to be written down |
| B-24 | Thread-L | a generator that exits 0 while writing a document with no entries in it | scar | 6.6 | adopted | 19 | round 20: adopted as CONVERGENCE EVIDENCE on text already in the file, with no second sentence written. 6.6's rows-per-run sentence, adopted in round 17 from B-4, already carries this class exactly; what B-24 adds is a second, independent instance - a document generator exiting 0 having written a file with no entries in it - so it extends that sentence's scar rather than founding anything. Two threads paying separately for one sentence is the strongest evidence 8.1 accepts, and a second rule for it would be the accretion 8.2 is about |
| B-25 | Thread-L | a cap that counts the wrong unit: the limit counted inbound items while what grew was their expansion, so one inbound item fanning out per interval admitted roughly a hundred thousand rows under a limit of a thousand | scar | 2.6 | adopted | 19 | round 20: 2.6 gained the sentence - a cap must count the unit that GROWS, since a limit on inbound items does not bound the output when one item fans out. The sharper half is in the scar: the expansion was added by the change immediately before the cap, so the cap and the thing it caps never appeared in one diff |
| B-26 | Thread-L | answer "what is actually running" from the deployment, not from the tree: a claims audit fetched the live site and found production nine commits and a month behind, still serving a name the repository documents as wrong, and 404ing its own security page | scar | 6.6 | adopted | 19 | round 20: 6.6 gained the sentence - a claim about a running system is verified against the running system, and that includes claims made in public copy. The mechanism named is a build/version surface the deployment serves about itself, so what is running can be asked rather than inferred from what was merged. No guard: this repository deploys nothing, and a gate over a deployment it does not have would be a check that cannot fail |
| B-27 | Thread-M | three lints printed OK and exited 0 over a directory holding no file they read, so a scan pointed at the wrong path was green on every run | scar | 2.9 | adopted | 21 | round 21: BUILT as R21-2. `swallow_lint`, `interpolation_lint` and `conflated_degrade_lint` exit 2 - the code the other guards already use for could-not-run - naming each path and why it held nothing, and `--update-baseline` refuses the same way. The pre-commit gate reports it as skipped in the guard's own words, and the MCP error leads with that sentence. A class ratchet hands every module in the package an empty directory and fails on exit 0 or an OK line, with one exemption carrying its reason |
| B-28 | Thread-M | a mutation verifier certified an import crash as an assertion: the test runner printed the same word for a test module that did not import as for an assertion that failed, and the grader matched the word | scar | 2.2 | adopted | 21 | round 21: BUILT as R21-3. `verify_guard` grades unittest output by its own counts - errors and no failures is a weak red - and pytest grading is unchanged. Four end-to-end cases on throwaway repositories pin both runners, the wording as well as the flag |
| B-29 | Thread-M | pin both invocation forms of a copied tool: the package form a repository's own tests use, and the by-path form an adopter uses | practice | 2.3 | adopted | 21 | round 21: BUILT as R21-4. The selfcheck reachability ratchet runs every module both ways, the by-path form with the package deliberately not importable. Both forms worked; only one was pinned. Practice, strengthening the mechanism of 2.3's seam rule and founding nothing |
| B-30 | Thread-M | a layered defence is verified per layer with the layers beneath it removed first, or a lower layer that still refuses masks a dead one above it | practice | 2.2 | adopted | 21 | round 21: 2.2 gained the sentence, labelled practice. Only the verification practice is adopted; the three-layer server that carried it is B-35 and is rejected |
| B-31 | Thread-M | name which tests each mutant must turn red, instead of accepting any red | practice | 2.2 | adopted | 21 | round 21: BUILT as R21-7. `verify_guard --expect <test-id>`, repeatable, certifies VERIFIED only when every named test is among the failures. A red elsewhere names what went red and is DECORATION when the named test is seen passing, INCONCLUSIVE when it is not seen at all; output with no readable test id is INCONCLUSIVE. Not exposed through the MCP server this round, for the reason in the round record |
| B-32 | Thread-M | eval cases authored independently of the system they grade, and a perfect score investigated as contamination before it is trusted | practice | 4.2 | adopted | 21 | round 21: 4.2 gained the sentence, recorded as convergence with 2.5's golden-file sentence (B-5) arrived at from the prompt side |
| B-33 | Thread-M | enforce human review by absence: the model-facing surface has no approve action, and a ratchet fails if that name ever appears | practice | 4.5 | adopted | 21 | round 21: 4.5 gained the sentence. No new guard, because `ratchet.py` with an empty baseline already expresses the ratchet |
| B-34 | Thread-M | a manual in-place mutation can execute stale bytecode when the edit keeps the file size and lands in the same second, and then reports no change | practice | 2.2 | adopted | 21 | round 21: landed as SKILL text in `agent/skills/robustness-loop.md` and not as doctrine - it is a detail of one language's cache, and 2.2 already says to mutate the line that runs. A fresh `PYTHONPYCACHEPREFIX` or an mtime bump; `verify_guard` is immune because it works in a fresh worktree. Every in-place mutant in round 21 ran that way |
| B-35 | Thread-M | a three-layer read-only server as the mechanism behind a review-gated surface | practice | 2.2 | rejected | 21 | round 21: REJECTED as a mechanism. It is product-shaped - a server an adopter builds around their own data, not a check this framework can ship generically - and the lesson inside it, verify each layer with the others removed, is adopted as B-30 |
| B-36 | Thread-M | attach a written reason to every swallow-baseline entry | practice | 2.7 | rejected | 21 | round 21: REJECTED. The swallow baseline is per-file counts with no per-site identity, so a reason has nothing stable to attach to, and 2.7 already asks for a comment at the site of an intended swallow. A keyed baseline with reasons would be a format change for no recorded incident |
| B-37 | Thread-A, Thread-F | vendored copies of a guard ran weeks behind the public repository, missing a later injection detection, and nothing in either adopting tree could say which release it held | scar | 6.6 | adopted | 21 | round 21: BUILT as R21-6. `bootstrap.sh` writes `.sutradhar-bootstrap` - the release and a sha256 per copied file - and `bootstrap.sh --check`, offline and from any checkout, reports each file current, stale, modified locally or missing; `--track` starts a record in an older tree. Landed on 6.6 as convergence with B-26: what is running is answered from the running copy, and a copied guard is a deployment of it |
| B-38 | Thread-A | a documented safety control existed in three docstrings and in no code | scar | 7.2 | adopted | 21 | round 21: 7.2 gained it as its scar - trust the tree, not the doc, and here the doc was the code's own docstrings. It was caught only because the value read unmeasured rather than zero, which is also convergence evidence for 2.9 |
| B-39 | Thread-A | refusals that happened and that nobody could see | scar | 2.9 | adopted | 21 | round 21: adopted as CONVERGENCE on 2.9's existing clause - give the third state a name and make it reportable as a rate - with no sentence written. A further thread arriving at the refusal rate is confidence in text already there |
| B-40 | Thread-A | reconstructed data was never tagged as reconstructed, so it read as observed | scar | 5.1 | adopted | 21 | round 21: adopted as CONVERGENCE on 5.1's per-value tier and gap marker and on 2.5's availability timestamp, with no sentence written |
| B-41 | Thread-A | failures that name whose failure they are | practice | 6.8 | adopted | 21 | round 21: adopted as CONVERGENCE on 6.8, with no sentence written |
| B-42 | Thread-F | a full guard suite was green and mutation-verified, and thirty seconds of using the running product found two defects | scar | 6.1 | adopted | 21 | round 21: extends 6.1's scar - a verified suite is still not a drill |
| B-43 | Thread-F | a probe that answered the same whether its subject was present or absent | scar | 6.7 | adopted | 21 | round 21: adopted as CONVERGENCE on 6.7 - an answer is evidence only in pairs - with no sentence written |
| B-44 | Thread-F | a verdict that changes nothing downstream is a survey: wire it to a consequence or delete it | practice | 3.1 | adopted | 21 | round 21: adopted as CONVERGENCE on 3.1 and not as an 8.2 sentence. Every wording tried for 8.2 restated 3.1 with control replaced by verdict - an output must change something, and something must show that it did - and a second sentence for one idea is the accretion 8.2 warns against. The delete-it half is 8.2's existing sentence about a thing with a test and no product |
| B-45 | Thread-A | an alarm threshold set inside the measured normal range | scar | 6.6 | deferred | 23 | one instance, and its substance is domain statistics - where the normal range sits is the adopter's measurement, not a rule this framework can state generically. 6.6 also keeps alerting out of the doctrine until an incident pays its way in; decide at round 23 whether a second thread has paid for the same shape |
| B-46 | Thread-F | cleanup that deleted a hardcoded list of names instead of what the run itself had created | scar | 7.3 | deferred | 23 | one instance. Clean up by the record of what you created, never by the names you expect - close to 7.3's own-what-you-touch and to 2.4, and one thread is not yet enough to say which it belongs to. Re-decide at round 23 |
| B-47 | Thread-A | one cap, one home: every limit defined in exactly one place | practice | 2.6 | rejected | 21 | round 21: REJECTED. No incident is attached and it is general hygiene; the part of cap placement anything here has paid for is 2.6's sentence that a cap must count the unit that grows |
