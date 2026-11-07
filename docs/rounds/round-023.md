# Round 23 - 2026-09-23

Lenses: the improvement round's first execution, exit-code discipline in CI wiring

**What this round was.** The first run of `corpus/improvement-round.md`,
supervised as a dry run: one real candidate taken end to end, and a record
of every place the written procedure failed or left the agent guessing
when it was actually executed. The candidate closes R22-3: `ci_step_lint`
now refuses a `run:` step that pipes a command into another with no
pipefail, the open corpus case `ci-pipe-swallows-exit-code` scores CAUGHT
with its round-22 twins unchanged, and 6.3 leaves the uncovered queue. The
four-command gate read 0 / 0 / 0 / 0. The procedure itself held at every
gate that decides anything; where it failed, it failed at the edges - a
step for the case the queue actually offers, the witness of its sweep, and
a ground-rules file that still speaks an adopter's layout. Recording the
round made two backflow items overdue, and the backflow gate is left red
on purpose for the maintainer to decide.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R23-1 | med | 6.3 | the improvement round, target ci-pipe-swallows-exit-code | fixed | ci_step_lint flags a pipe in a run step unless set -o pipefail runs earlier in the step or the effective shell (step, job defaults, workflow defaults, any key order) is plain bash, which GitHub runs with -o pipefail. A step with no shell key runs as bash -e with no pipefail, so a piped build reported the filter's status. Refusals: double bar, a bar inside quotes, an expression or a comment, an echo or printf upstream, a non-command shell. Selfcheck carries the new pair. Gate 0/0/0/0; detection-line mutant red (7 tests). |
| R22-3 | med | 6.3 | - | closed | Closed by R23-1. The open case is flipped to expected caught with twins unchanged, and 6.3 leaves corpus/uncovered.json in the same commit: 13 covered, 11 excluded, 25 banked. |
| R23-2 | med | 6.11 | the detection-line mutation | deferred | A guard whose embedded selfcheck fails exits 1, the finding code, on every input. Under the round's mutant the case scored FALSE_POSITIVE and the sweep flagged all 53 clean twins, including 49 that hold no workflow at all. The broken instrument reads as a finding everywhere: the exit-1-traceback-as-verdict shape, reached at the CLI rather than the adapter. The corpus stays honest here only because it also scores the clean twin; a single CI run would read red as a finding. |
| R23-3 | med | 2.9 | running the gate's second command | fixed | corpus.py --sweep printed nothing on success and counted no twins, and exit 2 from a twin is silence by design. A guard that could read none of the clean twins swept 0 exactly like one that read them all and flagged none. For ci_step_lint, 4 of 53 clean twins carried a workflow; the sweep could not say so. Fixed: every sweep prints its measured-silent, not-applicable, flagged and invalid counts, and exits 2 when it measured zero twins, pinned by a test pair and a pair in corpus.py's own selfcheck. |
| R23-4 | low | 6.7 | probing the scanner while extending it | deferred | steps() ignores a working-directory key that follows run in the same step; YAML key order is free. Probe: a step with run then working-directory backend resolves from the root. The new shell lookup reads step keys in any order; the reachability half still does not. |
| R23-5 | low | 6.3 | the same probe | deferred | A run block opened with a keep or indentation indicator (bar-plus, bar-2) is not read by steps() at all, so both checks see only the indicator. And a pipe inside a double-quoted command substitution is not read by the pipe check, because quoted text is stripped before the scan. A third, from the maintainer's review: a bar inside heredoc data would be read as a pipe, because the scan does not know where a heredoc begins or ends. All three are stated blind spots, not fixed this round. |
| R23-6 | med | 7.2 | executing the skill | fixed | improvement-round.md has no step for the target its own phase 1 surfaces. All three candidates were pre-existing open cases; phase 2 says to author a case and never says to flip expected open to caught, to revise the manifest prose that says the case waits on a guard, or that the flip is mandatory. The agent learns it from the full run's refusal line. Fixed: phase 2 now opens with the existing-open-case path - confirm MISSED, write the guard, flip to caught, revise the prose, twins untouched. |
| R23-7 | low | 6.7 | executing the ground rules the skill points to | fixed | agent/skills/robustness-loop.md, which the skill says to read first, ends phase 6 with python scripts/rounds.py docs/rounds/ --floors . and scripts/ does not exist in this repository. Correct for an adopter's tree, where that file ships; wrong where the Monday round runs. The R22-5 shape, surviving one file away from the fix. Fixed in the skill, not in that file: improvement-round.md now says its paths are an adopter's and that this repository runs every guard from python/sutradhar_guards/. |
| R23-9 | med | 8.1 | the repository gates, run after the memo was written | fixed | Writing this record is what makes B-45 and B-46 overdue: both carry by-round 23, and the backflow gate turned from exit 0 to exit 1 the moment round-023.md existed. The skill never mentions the backflow register past reading it, so a Monday round turns the repository's own CI red on any week an item falls due. Left red deliberately; see below. Fixed in the procedure: phase 5 now says a recorded round can make items due, the round never decides them, the memo lists them as awaiting the maintainer, and --backflow may be red for exactly those items. |
| R23-10 | med | 6.7 | the maintainer's review | fixed | ci_step_lint read pwsh, powershell and cmd as pipe shells, and read a step with no shell key on a windows runner as bash, so an ordinary pwsh pipeline was flagged and the adopter was told to add set -o pipefail, a bash command that breaks pwsh. Rule 6.7 because the defect is a missing known-good: the selfcheck carried pairs for pipefail and for shell bash but none on the runner axis, so an exit 1 on a windows job was never tested against a case that must exit 0. Fixed: only bash, sh and zsh are read, and an unshelled step in a job whose runs-on names windows is skipped; the pair is in the tests, the selfcheck, and corpus case ci-pipe-windows-default-shell, whose clean twin the sweep now runs forever. |
| R23-8 | low | 2.2 | phase 4 | fixed | Amending the round commit after the gate changes its hash, so the commit verify_guard names (abcdd65) is not on the branch. The tree is identical (7f29814 before and after, diff empty), and verify_guard was re-run on the amended HEAD with --expect naming two tests: VERIFIED. The skill said neither. Fixed: phase 4 now requires re-running verify_guard, with --expect, against the amended HEAD. |

## What each register item became

Decided by the maintainer. The round made both items due and, correctly, decided neither (R23-9).

| item | evidence | decision | landed in |
|---|---|---|---|
| B-45 | scar | rejected | one instance of domain statistics; no second thread in rounds 22 or 23 |
| B-46 | scar | adopted | 7.3: clean up by the record of what the run created, never by the names it expects |

## What the procedure got wrong

Quoted from `corpus/improvement-round.md` unless marked. Each is what the
text said, then what happened when it was executed.

After the maintainer's review the skill text was revised for items 1 to 11
and 13 to 15. Still open: the `GUARD FLOORS` line (1), the squash-merged
branch that `--no-merged` would hold forever (2), whether a baseline suite
run is owed before the change (11), and the pycache advice the agent
harness refused (12, a harness fact, not the skill's).

1. **"On `REST` ... On `INSUFFICIENT` ..."** (phase 0). The run printed
   `CONTINUE`, the one verdict the text gives no instruction for. Proceeding
   is the obvious reading, but it is a reading. The same output printed
   `GUARD FLOORS ... no baseline files found`, which the skill never
   mentions either way.
2. **"Otherwise create this round's branch in a worktree of its own:
   `improvement/<YYYY-MM-DD>`"** (phase 0b). No command is given, and an
   agent already launched in an isolated worktree has one. The branch was
   created in place with `git checkout -b improvement/2026-09-23`. The
   check itself printed nothing and exited 0, as it should; note that it
   cannot tell "no branch" from "a squash-merged branch", which would stay
   `--no-merged` forever and block every later round.
3. **"then `corpus/uncovered.json` ..., the residual register, and the
   backflow register"** (phase 1). No command for either register. The
   residual register printed by `rounds.py --floors` stops at 12 of 37
   entries ("... and 25 more") and `rounds.py` has no flag that prints the
   rest; the round 22 record was read directly instead.
4. **"Write the manifest in `corpus/cases/`"** (phase 2). The target was
   an existing open case, so there was nothing to author, and the text has
   no branch for that (R23-6). The twins were left exactly as round 22
   wrote them - rule 1, case before guard - and only the frontmatter and
   the prose that described the case as waiting were changed.
5. **"It must score MISSED before the guard exists."** It did, but
   `--case` exits 1 on MISSED and the text does not say so. An agent
   reading exit codes as verdicts (the house habit) would stop on it.
   Conversely, once the guard caught it, `--case` exited 0 while the case
   still said `expected: open`; only the full run (command four) refused.
6. **`--guard-cmd "python3 -m pytest python/tests/<new-test>.py -q"`**
   (phase 3). This presumes a new test file, while the ground rules
   prefer extending a themed one. The tests went into
   `python/tests/test_ci_step_lint.py`, so the guard command runs 37 tests
   and any red among them reads VERIFIED. The skill never mentions
   `--expect`; it was added on a second run to name the tests that must go
   red.
7. **"A brand-new guard module only reverts to an import error."** True,
   and not this round's case: extending an existing module reverts to the
   old module, which imports, so the red was by assertion and graded
   strong. The text covers only the new-module path.
8. **The second gate command, `--sweep`.** It printed only its selfcheck
   line and exited 0, with no count of twins read (R23-3). Its sensitivity
   was witnessed separately with a flag-everything mutant: exit 1, all 53
   twins flagged - but through the failed selfcheck, not through the
   scanner (R23-2).
9. **The fourth gate command** prints `INVESTIGATE: perfect score` on
   every clean run and still exits 0. The skill does not say what the
   agent owes it. This record answers it below.
10. **"Amend the round commit so its message quotes the gate's four exit
    codes"** (phase 4). The amend changes the hash the gate reported
    (R23-8).
11. **"Read that file first"**, pointing at `agent/skills/robustness-loop.md`.
    Its phase 6 recorder command names `scripts/rounds.py`, absent here
    (R23-7). Its phase 1 asks for a full baseline suite before touching
    anything; the improvement round never says whether that applies, and
    this round did not run one before the change (the full suite was run
    after, green).
12. **"Run each in-place mutant with a fresh `PYTHONPYCACHEPREFIX`"**
    (robustness-loop.md, phase 5). The agent harness refused to run a
    command that sets that variable. The mutant changed the file's size
    and its mtime was bumped with `touch`, which the same paragraph offers
    as the alternative; the restore was proved by sha256.
13. **Phase 5 memo format.** "The house format" is defined only by the
    ground rules' phase 6 example, which shows no `## Findings` heading
    and three statuses; the records on disk carry the heading and
    `rounds.py` also accepts `retracted`. The skill also does not say
    whether the memo joins the round commit or follows it, or to run
    `rounds.py --check` on it. It was committed separately and checked.
14. **Gates beyond the four.** The skill's gate proves the candidate on
    the corpus; it does not name the repository gates (framework, shape,
    round records, budget, plugin sync, this repo's own workflow, the
    demo, the full suite), the CHANGELOG, or the plugin sync for a bundled
    guard. The maintainer's brief supplied them. `ci_step_lint.py` is not
    bundled in `plugin/guards/`, so no copy needed syncing; `--check`
    exited 0.
15. **"Write the round memo to `docs/rounds/` ... either way"** (phase 5).
    Doing so made two backflow items overdue and the backflow gate red
    (R23-9). Nothing in the skill says that recording a round is itself a
    deadline for the register, or who decides what falls due.

## The backflow gate is red, deliberately

B-45 and B-46 came due with this record and this round decided neither.
Deciding a backflow item is one of the things the skill keeps human
("doctrine prose lands via backflow decisions"), and the register's own
history is plain about the alternative: moving a deadline to make the gate
green is R15-4's exact shape. So `rounds.py --backflow` exits 1 on this
branch, and the maintainer decides both - adopt, reject with a reason, or
re-defer with a reason - before it merges.

## Ruled out, and why

- **verify-guard-collision-warning.** Waiting on a warning becoming a
  verdict in `verify_guard`, which is a design decision about that tool's
  exit partition, not a guard a round can write against a case.
- **exit-1-traceback-as-verdict.** Its twins are placeholders by its own
  prose, and the defect lives in the caller's mapping, which no registry
  guard runs. R23-2 gives it a concrete CLI-level shape to author against
  next time.
- **Special-casing the Windows default shell.** A Windows runner with no
  `shell:` key runs pwsh; the guard reads that step as bash and would flag
  a pipe there. pwsh pipelines also report the last command's status, so
  the finding is not obviously false, and no workflow in reach runs on
  Windows. Not built.

## The perfect score

`INVESTIGATE: perfect score` asks what changed. One case moved from open to
caught. Its twins are byte-for-byte those round 22 wrote from the 6.3 scar
before the check existed; the check was written against the doctrine text
and its own tests, and the case was not edited to fit it. The other two
open cases still score MISSED.

## Harness notes

- A mutation run on a scratch copy of `python/` reddens the two tests that
  read this repository's own workflow and CI template, because the copy has
  neither. A null mutation reproduces exactly those two; they are the
  harness, not the mutant.
- This repository's own `selftest.yml` has no pipe in any `run:` step; the
  guard reports it clean, which is correct. `ci/guards.yml` has one pipe,
  inside a quoted command substitution after `set -euo pipefail`, and is
  not a target of this guard.
- Full suite after the change: 1012 passed, exit 0 (15 new tests).
