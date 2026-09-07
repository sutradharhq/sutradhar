# Round 20 - 2026-09-08

Lenses: the backflow register, the two mechanisms it was owed

**What this round was.** It decided the register rather than adding to it.
Round 19 left eight items overdue and said so; recording round 20 brought a
ninth due the same day. All nine are decided here under one rule, the
round-17 rule repeated by the maintainer: **adopt unless the item is
redundant with a rule already in `DOCTRINE.md`, or would narrow or choke
what an adopter may build.** Applied evenly, it adopted eight and rejected
one.

Nothing was re-deferred. That is the difference between this round and
rounds 16, 18 and 19, each of which left the gate red on purpose rather
than move a deadline - and the reason those refusals were right is that
they made this round's work exist rather than disappear.

The register added no item this round. `rounds.py docs/rounds/ --backflow
docs/backflow.md` exits 0 for the first time since round 17.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R20-1 | med | 6.11 | the new guard's first run | fixed | `ownership_lint`'s selfcheck drives `main()` on purpose - the CLI is the real seam (2.3), and a case that pokes `audit` directly cannot see a broken argument parser - while `main()` runs the selfcheck before scanning, as every other lint here does. Those two correct decisions are mutual recursion, and the file's first execution was a `RecursionError`: not a red verdict but the absence of one, which is 6.11's whole subject and the third occurrence of that shape in three rounds. Broken with an explicit re-entrancy flag whose comment says why it exists, rather than by dropping either half |
| R20-2 | med | 2.2 | the mutation run | fixed | the seam mutant for `interpolation_lint` - `_quoted_at` forced to `True`, which should flood the report with `LIMIT %d` - killed one behavioural test and left the SELFCHECK green. Its only unquoted negative case interpolated `n_limit`, which the numeric-suffix heuristic exempts whatever the quoting says, so the case would have passed for a second reason and proved nothing about quoting. A negative case that is also true for another reason is not a negative case. Rewritten with a name carrying no safe suffix; the mutant now kills the selfcheck too |
| R20-3 | low | 7.2 | wiring a fifth guard into the pre-commit gate | fixed | `docs/design/agent-loop-hooks.md` listed the three guards the gate ran when it was written. Round 19 added `framework_shape` to `_plan` and did not add the row, so the note described a three-guard gate while the code ran four - the stale-status-doc shape 7.2 is about, inside the design note that documents the mechanism. Both missing rows added |
| R20-4 | med | 2.2 | cold-start drill on the public clone | fixed | `bootstrap.sh` copied `framework_shape.py` into the adopter's `scripts/` and the next-steps text told them to run it, and `ci/guards.yml` named it in a step. In an adopter's tree that gate scans only its own declared surface directories, which there hold nothing but the files just copied, so it cannot fail: simulated a product with `1,240 kWh` and a dollar amount in `src/` and it exited 0. A guard that cannot fail where we tell somebody to run it is decoration, and shipping one teaches a green that means nothing. `framework_only.py` was already correctly not copied for the same reason - both gate a promise only this repository makes. Removed from the bootstrap python layer, from the next-steps text and from the template, each with the reason written where the step would have been. `ci_step_lint` caught the half-finished change: the template still named a script bootstrap no longer copies, which would have failed an adopter's first push on file-not-found |
| R20-5 | high | 1.2 | independent review, a different model | fixed | the Stop hook ran a `Guard-cmd:` trailer when HEAD's author email matched the local `git config user.email` (R16-2's fix). That control was decoration: an author email is self-asserted, unverified by anything git records, and public in every commit, so a hostile commit sets it to the victim's and checking out the branch is enough. Reproduced end to end - a commit authored as the local identity whose trailer wrote a sentinel; the sentinel appeared, and the hook returned `block` with a verdict *after* the code had already run. The "not run through a shell" parser does not help: it refuses stray operators, and accepts `bash -c '...'` or `python3 -c '...'` as argv, because they are one program with arguments. Fixed as a seam rather than a stronger check: by default the hook executes nothing a commit chose - it reports the trailer and hands over the one-line command - and `SUTRADHAR_RUN_TRAILERS=1` opts a tree you control back in, with the author check kept and named as a speed bump. A test now carries the hostile fixture and its pair; SECURITY.md and the plugin README say what the parser is and is not |
| R20-6 | med | 6.10 | independent review | fixed | SECURITY.md said "no network calls" and "no network code anywhere in the plugin or the guards", and the plugin README's table said `network: no` for every row. `obsgate.py` imports `urllib.request` and opens whatever URL its `metrics` argument names, and it is bundled in the plugin and exposed by the MCP server, whose `metrics` argument was not confined the way `repo` is - so a model could make the server fetch any URL as the user. The false sentence was written in round 16 by this project's own reviewer, who grepped `mcp_server.py` and `plugin/scripts/` for socket code and then wrote a claim about "the guards", a larger surface than was measured (6.10 exactly). Fixed: the documents now name `obsgate` as the one guard that makes a request, only to a source you pass it; the MCP server refuses a URL in `metrics` as a caller error unless `SUTRADHAR_MCP_ANY_URL=1` and confines a path as it confines `repo`; three transport tests hold it |
| R20-7 | low | 2.4 | independent review | fixed | `bootstrap.sh`'s printed next steps carried a dangling half-sentence, `2i. ONLY IF WHAT YOU SHIP IS A FRAMEWORK - keep it from speaking your`, with no command after it. R20-4's edit deleted the command line and the second half of the label and left the first half. It is the first thing an adopter reads after running the install, and it was broken by the fix that made the install honest |
| R20-8 | med | 2.4 | the maintainer, on the fix | fixed | R20-5 and R20-6 were fixed by refusing: the Stop hook executed no trailer at all, and the MCP server refused every URL in `metrics`. Both were safe and both were unusable. The hook's whole job is to check the guard on the commit you just made, and `obsgate` exists to read a running surface - a dev stack answers on loopback, so refusing URLs left the tool unable to do the thing it is for. Safety bought by removing the capability is not a fix, it is the gate being switched off later by someone with a deadline (R14-2). Replaced both with a question that separates the cases: the hook runs a trailer when HEAD is not yet on any remote, which an attacker cannot arrange and which is exactly your own unpushed work; the server reads loopback unasked and refuses other hosts. The first draft of the URL check also refused IPv6 loopback, because the alternation matched a bare `[` before the bracketed form |

## What each item became

| item | evidence | decision | landed in |
|---|---|---|---|
| B-13 | scar | **rejected** | nowhere. Its lesson is R16-1's class and was adopted in round 18; the remainder is a Playwright port |
| B-16 | scar | adopted, **built** | `python/sutradhar_guards/ownership_lint.py`, the mechanism 7.3 has named since round 17 |
| B-20 | practice | adopted, **built** | `interpolation_lint` reads `%` and `.format()`; 2.8 gained one clause and no rule |
| B-21 | practice | adopted | 2.2: mutate the line that RUNS |
| B-22 | scar | adopted, **as a skill** | `agent/skills/ops-drill.md`: boot in dependency order, assert what an operator sees |
| B-23 | scar | adopted, **as a skill** | `agent/skills/ops-drill.md`: a lockfile's one claim, and the second machine that tests it |
| B-24 | scar | adopted, **as convergence** | 6.6's existing rows-per-run sentence; its scar now names both instances |
| B-25 | scar | adopted | 2.6: a cap must count the unit that GROWS |
| B-26 | scar | adopted | 6.6: a claim about a running system is verified against the running system |

Four rules gained text - 2.2, 2.6, 2.8 and 6.6 - and one scar in 6.6 was
extended. **No rule was added and none renumbered**, so all 127 findings
across the round records still resolve against the rule they name.

## B-24, and why convergence is not a second rule

B-24 is a document generator that exits 0 having written a file with no
entries in it. 6.6 already says a job's success carries its output count and
that a silent zero is a failure - adopted in round 17 from B-4, a training
loop that ran thirty days at zero rows under green status. Two threads, no
contact between them, the same sentence.

The tempting move is a second rule, or at least a second sentence, because
the row is new. Both would be wrong. 8.1 says a rule enters with the
incident that paid for it; it does not say each incident buys a rule, and
8.2 says the accretion is the default failure. What a second independent
instance buys is **confidence in the sentence already there**, so it landed
in that sentence's scar and the register row says it landed as convergence
rather than as text. Convergence at that width is what 8.1 treats as its
strongest evidence - the same argument 2.9 was admitted on, where four
threads arrived at the same shape from four directions.

The mechanism half - a rows-per-run floor as a first-class `obsgate` check -
is still not built, exactly as round 17's B-4 note said. Two threads paying
for it moves that from "an idea" to "the next mechanism somebody should
cost", and it is not costed here.

## B-13, and what rejecting it does not throw away

B-13's scar is real and expensive: a shipped Cypress template could not run
in a package-manager layout its author had not tried. That LESSON is already
adopted. It is the class of R16-1 - tested only in the layout it was built
in - and round 18 answered it by bundling the plugin's guards so an
installed copy no longer reaches outside its own directory, with a test that
reproduces the installed condition rather than the checkout.

What is left in the row is a **Playwright port of `expectEffect`**. That is
a second UI-runtime binding this repository cannot run, cannot test in CI,
and would ship untested beside the Cypress one - which is precisely the
"narrows or chokes what an adopter may build" half of the rule, aimed at the
framework rather than at the adopter: a harness that ships two bindings and
exercises one has widened its promise and not its evidence. `README.md`
already says the port is mostly mechanical and that the row appears when it
ships. It belongs to the JS kit's own register when that repository exists.

This is the register's first rejection in twenty rounds, and it is worth
saying that a register that has never rejected anything is not obviously
working either.

## B-16: the guard 7.3 has been owed since round 17

7.3 gained the manifest sentence in round 17 and the guard was re-deferred
to round 18, which did not build it, and then sat through round 19.
`ownership_lint.py` is it.

It reads a `<owner>: <glob> ...` manifest and the paths in the index - the
stage is what 7.3 is about, and the moment before a commit is the last one
at which a collision is still cheap. Four answers, all printed:

- a path owned by ANOTHER owner: refused, **with the owner named**, exit 1.
  A refusal that does not say who to hand the file back to leaves the reader
  with a verdict and no next step.
- a path owned by THIS owner: allowed.
- a path owned by NOBODY: allowed, and **counted**. Most of a repository is
  unowned on any given day; a skipped path nobody counts is an exclusion the
  operator cannot see, which is 6.7's shape.
- a path claimed by two owners: allowed, and the overlap reported. Two
  agents who each believe they own a file collide exactly the way B-16 did,
  so resolving it silently in favour of whoever ran first is the behaviour,
  not the fix.

A missing manifest is an **instrument condition and not a violation**: exit
0, and a line saying nothing was checked. This is the one place in the
toolkit where "could not measure" is deliberately spelled the same as "did
not fail", and it is a deliberate trade - the guard is opt-in, and a gate
that blocked every repository without a manifest is muted by lunchtime
(R14-2). The printed line is the whole of what keeps that zero honest, and
the selfcheck asserts the line is there rather than only the exit code.

An unreadable manifest row is refused, never skipped. A typo that drops an
owner makes every path they hold read as unowned, which is the guard
reporting green over the exact collision it exists to refuse (2.9, in the
instrument). git failing is reported as git's failure or the guard's, by
name, and never as a verdict on anybody's stage (6.8).

## B-20: one dialect of a class, wearing the class's name

`"SELECT * FROM t WHERE n = '%s'" % name` passed `interpolation_lint` clean
for sixteen rounds while the f-string two lines above it was caught. Round
16 found it by reading (R16-5). The docstring called it a known limitation,
which is the worst available place for it: a lint that looks total and is
not is worse than one whose edges are written down, because nobody reads a
green report twice.

Both older spellings are now read on the same terms as the f-string: the
literal at the call site is searched for query keywords, each placeholder is
resolved to the argument that fills it, and the same quoted-position and
same-site-escaping rules decide. Three details that are the difference
between a guard and a nuisance:

- `%%` consumes no argument and is skipped, so a literal percent sign does
  not shift every positional index after it and name the wrong variable.
  6.9: a finding that names the wrong thing sends the reader the wrong way
  with total confidence.
- an argument that cannot be matched to its placeholder (`"..." % params`,
  `.format(**kw)`) is judged against ALL the call's arguments and is safe
  only if every one is safe. "Cannot tell" must not resolve to "clean".
- a format string held in a module constant is **not seen**, and that is
  written into the docstring as a limitation rather than half-handled.

Run over this repository's own `python/` tree it finds nothing new, and the
worked example still trips it. Adopters are a different matter, and the
CHANGELOG says so: a codebase carrying `%`-format query holes will see them
on the first run after taking this, and they are real.

`practice` evidence, so it strengthened 2.8's mechanism and founded nothing.
2.8 gained one clause naming the two spellings.

## B-22 and B-23: 6.1 owes a mechanism this repository cannot ship

Both are 6.1, both came from the same adopter thread, and both asked for a
mechanism rather than a sentence - 6.1 already states the discipline, and
what this repository ships for it is `agent/skills/ops-drill.md`, a playbook
a person follows rather than a command with a gate.

**No guard was written, and that is the decision rather than a shortcut.** A
working drill is inherently application-specific: the layers, the gates and
the commands are all the adopter's. A guard here could only check that a
file exists - which is 3.6's complaint about counting presence - or invent a
runtime this framework does not have, which is the first step of a framework
becoming a product (`framework_only.py` exists because that step is easy to
take by accident). So the skill carries the mechanism, and both register
rows say that and why.

What the skill gained: dependency order written down before anything boots;
one layer at a time, asserting between them, because booting everything and
checking at the end tells you the stack works and cannot tell you which
layer was ready when; assert what an OPERATOR would see rather than what the
code returns, since a health route is written by the same code that is
broken and will report itself healthy; and a named defect class to hunt - a
layer that started before its dependency answered - with its four usual
shapes and two ways to provoke it deliberately. Then B-23's half: a lockfile
is not numeric truth to be frozen (2.5), it makes one claim, and the only
thing that tests that claim is installing on a second machine, from an empty
cache, on a different OS or architecture, with the resolved set diffed by
command rather than eyeballed.

## B-23 was not in the brief, and came due on recording this round

The maintainer's brief named eight overdue items. B-23 carried by-round 20
and status `owed`, so writing this record made it overdue the same day - the
same mechanic that brought B-4 and B-6 due on recording round 17.

The adoption rule was applied to it evenly, which is what the rule says to
do, and the rule's answer is adopt: 6.1 says run cold-start drills, and it
does not say what a lockfile's single claim is or what tests it. The
register's own note put B-23 with the JS kit on the grounds that this
repository has no lockfile of its own. That is an argument about where a
GUARD would live; the lesson is a drill shape and needs no lockfile in this
tree to be written down.

It is flagged here, in the register row, and in the report to the maintainer,
because a round that quietly decides an item its brief did not mention is
doing the thing this register exists to make visible.

## Mutation verification (2.2, as amended by B-21 this round)

Every mutant below was applied **to a line that executes**, which is the
sentence B-21 put into 2.2 four commits earlier in this round. Each was
applied by editing the file, running the named command, and restoring from a
backup taken first.

| mutant | result |
|---|---|
| `ownership_lint.audit`: the refusal branch `refused.append(...)` changed to `owned.append(...)` | **red**, 13 of 27 tests. The behavioural one is `assert "python/guards/a.py" in said.err` failing as `assert 'python/guards/a.py' in ''`; the selfcheck printed "a path owned by alice was not refused for bob" |
| `ownership_lint.parse_manifest`: an unreadable row skipped (`continue`) instead of refused | **red**, 15 of 27, including `DID NOT RAISE OwnershipError` on two of the four planted manifest rows |
| `interpolation_lint.check_source`: the two dispatch lines for `BinOp`/`Call` deleted | **red**, 12 of 27, first as `assert len(hits) == 1` / "assert 0 == 1 where 0 = len([])", and the selfcheck as "`%`-format into a quoted query position: 0 finding(s), expected 1" |
| `interpolation_lint._quoted_at` forced to `True` | **red** on `assert check_source(pct, SQL) == []` / "assert [(1, 'page')] == []" - and GREEN in the selfcheck on the first attempt, which is R20-2 |
| the same mutant, after R20-2's fix | **red** in the selfcheck too: "`%` and `.format()` on strings that are not injectable queries: 2 finding(s), expected 0" |

The `ownership_lint` numbers are two mutants each killing about half the
file's tests, which is what a guard with one central decision looks like;
the interesting number is not the count but that the selfcheck died in every
case, because the selfcheck is what an adopter's CI runs.

## Measured, not estimated

| Number | Before | After |
|---|---|---|
| tests | 761 | **808** |
| guard modules | 17 | **18** |
| guard programs bundled in the plugin | 9 | **10** |
| guards the pre-commit gate can run | 4 | **5** |
| register items decided this round | - | **9** (8 adopted, 1 rejected) |
| register items still `owed` or `deferred` | 9 | **0** |
| doctrine rules | 49 | **49** |

## What was ruled out (7.4)

- **A CI step for `ownership_lint`, in this repository or in
  `ci/guards.yml`.** In CI the index is empty on a checkout, so the guard
  would read zero paths, refuse nothing, and print green on every push
  forever - a check that cannot fail, which is 3.7 built on purpose. Its
  home is the moment before a commit. `ci/guards.yml` carries the reasoning
  as a comment where the step would have gone, so nobody adds it later
  thinking it was an oversight.
- **A `.sutradhar-owners` manifest in this repository.** One agent works
  this tree at a time; a manifest here would be a fixture pretending to be a
  practice, and the guard's own selfcheck already exercises every branch
  against real manifests in temp directories.
- **A design note for `ownership_lint`.** `docs/multi-agent.md` states the
  discipline and the register carries the incident. A note declaring no
  budget would add a file and no constraint - the same reasoning round 19
  applied to `framework_shape`.
- **A second doctrine sentence for B-24.** The subject of its own section
  above. Convergence strengthens a sentence; it does not buy a new one.
- **Re-deferring B-23 rather than deciding it.** Legitimate - a re-deferral
  with a reason is one of the three ways out - and refused, because the
  reason would have been "the brief did not mention it", which is not a
  reason about the item. The adoption rule applies evenly or it is not a
  rule.
- **Rewriting B-13's row to keep the port alive as a deferral.** It has been
  deferred twice already. A third would be the R15-4 shape with better
  manners; a rejection with the reasoning written down is a decision the
  next reader can overturn in one commit.
- **Extending `interpolation_lint` to a format string held in a constant.**
  It needs to follow a name to its assignment, which is a different class of
  analysis with its own false-positive surface, and the honest version of
  "not done" is the limitation in the docstring plus the test that pins it.
- **Adding `ownership_lint` to the MCP tool table.** The commit gate is the
  placement that does not depend on anyone remembering; a second that does
  is not what B-16 was about. Round 19 ruled the same way for
  `framework_shape`, and the two decisions should stay consistent or one of
  them should be revisited on purpose.

## Guards touched

`ownership_lint.py` (new), `interpolation_lint.py` (the `%` and `.format()`
halves), `plugin/sync_guards.py` and `plugin/guards/` (the tenth bundled
guard), `plugin/scripts/precommit_gate.py` (the fifth planned guard),
`.github/workflows/selftest.yml` (both selfcheck lists and the bootstrap
copied-set), `ci/guards.yml` (a comment, deliberately not a step),
`bootstrap.sh`, `README.md`, `python/README.md`,
`docs/design/agent-loop-hooks.md` (R20-3), `agent/skills/ops-drill.md`,
`DOCTRINE.md` (2.2, 2.6, 2.8, 6.6 - text only, no rule added or renumbered)
and `docs/backflow.md`.

761 tests before, 808 after.

## R20-4: the drill an evaluator runs

This one came from operating the repository as a stranger would rather than
from reading it: clone the public URL on a clean path, run the command the
README leads with, then bootstrap into an empty repo and run what the
next-steps text says to run.

Most of it held. Seven of seven planted defects caught from a cold clone,
all eighteen guard selfchecks green with plain `python3` and nothing
installed, every relative link resolving. What did not hold was the advice:
we were telling an adopter to run a gate that cannot fail in their tree.

Two things are worth keeping from it. The first is that the fix was
incomplete and a guard written two rounds ago caught it - removing the file
from `bootstrap.sh` left `ci/guards.yml` naming a script that would no
longer be there, which is R18-3's class exactly, and `ci_step_lint` refused
it before it shipped. The second is that the first run of the drill
reported exit 127 and it was `timeout`, absent on this platform, inside the
drill's own wrapper rather than anything in the repository (6.4). A false
finding about your own front door is still a false finding.

## R20-5 to R20-7: the outside mind

Rule 8.4 says one family of agents shares blind spots with itself, and this
round tested that literally: after v0.5.0 was cut, a reviewer running on a
different model was given the public URL, the release notes and the
instruction to find what would embarrass the author in front of a
security-literate stranger. It found three things in under fifteen minutes
that twenty rounds of self-review had not.

The first is the one that matters. The plugin's most security-sensitive
control, added in round 16 to close a door an audit had found, was itself
decoration: it compared a field anyone can set with a field anyone can
read. It passed against an honest stranger and failed against a real one,
which is the defect this whole project exists to name, sitting in the one
place it could do the most harm. The fix is not a better check. It is to ask a
question an attacker cannot answer for you - is HEAD already published? -
and the first attempt at it, which refused everything, is recorded as
R20-8: safe, and useless.

The second is a sentence this project's own reviewer wrote into
`SECURITY.md` in round 16 after measuring a smaller surface than the claim
covered. It was false when written, it was repeated in the plugin README's
table, and it stood through three releases of review by the same lineage.
6.10 was adopted in round 17. It did not help, because the person who
needed to apply it had already written the sentence.

The third is a broken line of install text left by the previous round's
fix. Small, and in the first place a stranger looks.

What the reviewer did not find is recorded too: every doctrine citation
resolves, every declared budget is enforced, the suite is green on 3.9 and
3.13, and the "never blocks because it broke" property held under a
deliberate crash. The review was asked to say so rather than pad, and it
did. Its closing line is the one to keep: a framework whose pitch is that
green checks lie shipped a security control that was itself a lying green
check. That is the reason 8.4 is a rule and not advice.
