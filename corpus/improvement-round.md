# Skill: improvement round - one mechanized step of the self-improving loop

Hand this file to the agent verbatim ("run one improvement round") on the
Monday schedule, ahead of the weekly review. One round proposes ONE
candidate guard, proves it on the defect corpus, and commits to a local
branch for human review. It never pushes.

What stays human, permanently: scars come from reality, merges are
reviewed, doctrine prose lands via backflow decisions. After this skill
ships, the claim is "the loop is mechanized except reality and review",
never "autonomous self-improvement".

**Where this runs.** A checkout of this repository, from its root. Every
command below uses this repository's own paths. The corpus scorer does
not ship to adopters yet (a scorer with no cases can only ever refuse),
so neither does this skill: it lives beside the corpus, not in
`agent/skills/`, whose every file ships. Both move into the copy set
together, and the skill gets its plugin wrapper then.

The ground rules live in `agent/skills/robustness-loop.md` -
one worktree per agent, stage named files only, bounded waits, honest
labels, finish the scope. Read that file first if you have not run a
round before; this file does not restate it. **Its command paths are
written for an adopter's bootstrapped tree (`scripts/rounds.py`); in this
repository every guard runs from `python/sutradhar_guards/`.** Translate;
do not edit that file, which is correct where it ships. Three rules are
specific to this loop and non-negotiable here:

1. Case before guard, always. Never author a case from guard output.
2. One candidate at a time. Commit locally, never push.
3. Write the round memo even when nothing was proposed (2.9: a quiet
   week says so explicitly, or silence reads as success).

Every command's exit code is read on its own, never through a pipe (6.3).

## Phase 0 - read the stop rule first

```bash
python3 python/sutradhar_guards/rounds.py docs/rounds/ --floors .
```

- On `CONTINUE`, go on to phase 0b.
- On `REST`, propose pruning or corpus work, NOT new guards.
- On `INSUFFICIENT`, say so and stop. A round that cannot read its own
  stop rule has nothing to steer by.
- If the report lists deletion candidates (8.1), read them before anything
  else: pruning a rule nobody cites is a round's worth of work on its own.

## Phase 0b - one in flight at a time

```bash
git branch --list 'improvement/*' --no-merged main
```

If that prints anything, stop: the previous round's branch is still
unreviewed. Two candidate branches are two competing claims about the same
corpus, and the review cannot hold both at once. Say which branch is
waiting and end the round with the memo (phase 5).

Otherwise create `improvement/<YYYY-MM-DD>` in a worktree of its own
(`git worktree add ../round-<date> -b improvement/<date>`), or, if you were
launched already isolated in a worktree, with `git checkout -b` there.

## Phase 1 - pick the target, in one sentence

```bash
python3 python/sutradhar_guards/corpus.py corpus/ --rounds docs/rounds/ --backflow docs/backflow.md
```

Read its open/MISSED lines and its coverage line, then
`corpus/uncovered.json` (the queue: every uncovered rule with the case idea
it is waiting for), the residual register (phase 0 prints the first twelve;
the rest are the `deferred` rows of the round records), and the backflow
register (`docs/backflow.md`). Pick the highest-yield target and say why in
one sentence: an open case closest to a guard, a MISSED case whose guard
exists but does not catch, or an uncovered rule whose case idea is concrete
enough to write today.

## Phase 2 - the case, before the guard

**If the target is an existing open case**, do not author a new one. Run
its `--case` below and confirm it still scores MISSED; write the guard
(phase 3); then flip its frontmatter `expected: open` to `expected: caught`
and revise the manifest prose that says it is waiting. The twins stay
byte-for-byte as they were authored - that is what keeps rule 1.

**Otherwise** write the manifest in `corpus/cases/` following
`corpus/README.md`: frontmatter, defective/clean twins, helper fences
before the twins, engineering vocabulary only. Author it from the rule's
scar in `DOCTRINE.md` and the finding it cites - never from what a guard
prints. A case citing a finding of this round needs that row in the round
record first, or its scar does not resolve.

```bash
python3 python/sutradhar_guards/corpus.py corpus/ --case <case-id>
```

It must print MISSED, which exits **1** - expected here, not a failure.
Anything else means the case is wrong, not early: fix the twins, not the
verdict. (Once the guard catches it, `--case` exits 0 even while the
manifest still says `open`; only the full run refuses that.)

## Phase 3 - write the guard, commit, then run the gate

Write the guard and its test. Prefer extending an existing guard and its
themed test file; a guard you extend gets its embedded selfcheck extended
with the new pair (a known-bad it must flag, a known-good it must not).
Commit guard, test and case on the round branch first: `verify_guard`
reverts a commit, so the gate needs one to exist. If the case newly covers
a rule, remove that rule from `corpus/uncovered.json` in the same commit.

Selection is composed, not built - four commands, four exit codes,
accept only on `0 / 0 / 0 / 0`:

```bash
python3 python/sutradhar_guards/corpus.py corpus/ --case <case-id>
python3 python/sutradhar_guards/corpus.py corpus/ --sweep <guard-name>
python3 python/sutradhar_guards/verify_guard.py --repo . --commit HEAD \
  --guard-cmd "python3 -m pytest python/tests/<test-file>.py -q" \
  --expect <new-test-name>
python3 python/sutradhar_guards/corpus.py corpus/ --rounds docs/rounds/ --backflow docs/backflow.md
```

The second command is the cross-case sweep: the guard over EVERY clean
twin, which catches a guard that flags everything. Read its count line:
twins it could not read are not-applicable, and a sweep that measured
zero exits 2. The third proves the guard red on the revert; `--expect`
names the new test, because a test file you extended holds other tests
whose red would otherwise read VERIFIED. The fourth holds the denominator
and the coverage floor. It prints `INVESTIGATE: perfect score` on every
clean run and still exits 0: answer it in the memo by saying what changed
and that no case was edited to fit the guard.

**A brand-new guard module only reverts to an import error.** When the
commit adds the module, `verify_guard` deletes it and the test dies at
collection - a red it reports as `VERIFIED (weak)`, because a crash is not
the named test failing. That proves the test imports the module, nothing
more. So also weaken the detection line itself (the line that RUNS, 2.2)
and show the test go red; that mutation is the evidence that counts. It
is required for an extended guard too. Print the line before and after
the edit, and prove the restore by sha256.

## Phase 4 - record the evidence in the commit

Amend the round commit so its message quotes the gate's four exit codes
and the detection-line mutation that showed the guard red, with the
command that ran it. The amend changes the hash `verify_guard` reported,
so re-run the third gate command against the amended HEAD and quote that
run too. Never push: the maintainer runs the gates, does their own
mutation at the runtime seam, and pushes.

## Phase 5 - memo, even when quiet

Write the round memo to `docs/rounds/round-NNN.md` in the format of the
records already there (`# Round N - date`, `Lenses:`, a `## Findings`
table with the six-cell header; never a bar character inside a cell),
and commit it after the round commit. Closing a deferred finding means a
row with its old id and status `closed`. A round that proposed nothing
records what it read, what it ruled out, and why - un-recorded dead ends
get re-explored at full price.

**Writing the memo records the round, and a recorded round can make
backflow items fall due.** The round never decides backflow items; it
lists each newly due item in the memo as awaiting the maintainer. Expect
`rounds.py --backflow` to exit 1 for exactly those items and no other
reason - check that its output names only them.

## Closing checklist

Each command alone, its exit code read on its own:

```bash
python3 python/sutradhar_guards/framework_only.py .
python3 python/sutradhar_guards/framework_shape.py .
python3 python/sutradhar_guards/rounds.py docs/rounds/ --check
python3 python/sutradhar_guards/rounds.py docs/rounds/ --designs docs/design/
python3 python/sutradhar_guards/rounds.py docs/rounds/ --backflow docs/backflow.md
python3 python/sutradhar_guards/budget.py docs/design/ --tests python/tests/
python3 plugin/sync_guards.py --check
python3 python/sutradhar_guards/ci_step_lint.py .github/workflows
bash examples/run-the-guards.sh
cd python && PYTHONPATH=. python3 -m pytest tests/ -q
```

- A guard that has a copy in `plugin/guards/` is re-synced with
  `python3 plugin/sync_guards.py` before `--check`.
- The change gets a `CHANGELOG.md` entry under Unreleased, citing the
  round's finding ids.
- All exit 0 except `--backflow`, which may exit 1 for the newly due items
  the memo names.
