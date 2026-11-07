# Round 25 - 2026-10-04

Lenses: the improvement round's first unattended run, rule 8.2 from the uncovered queue, what the round's own cross-case sweep found, what a round that stops leaves behind

**What this round was.** The first improvement round run unattended, on
its schedule; its commit is stamped Mon Oct 5 01:36 +0530, the round
branch is named for 2026-10-04. It took rule 8.2 from `corpus/uncovered.json`, wrote
the corpus case `helper-with-test-and-no-caller` citing the 8.2 scar, added
`find_test_only_helpers` to `detectors.py`, and committed all three as
96a6e6e (R25-1). Then it ran the four-command gate, and the second command,
`corpus.py --sweep detectors`, exited 1: detectors flagged the clean twin
of `swallow-behind-a-byte-order-mark`. The session ended while it was
investigating. It left no memo and no record of what it read or ruled
out, so from outside a stopped round looked like a quiet one (R25-5).
The maintainer reproduced the failure and showed it was older than the
round: main at b86ef92 flags the same twin. `detectors.py` read source as
`utf-8`. R24-27 had moved three lints to `utf-8-sig` and missed this
sibling (R25-2). A second session finished the round on 2026-10-16 on the
same branch, adding commits on top of 96a6e6e without rewriting it. It
fixed the class, not the instance. A class ratchet now walks every guard
module by AST. On its first run the ratchet found a third sibling,
`framework_only.py` (R25-3), that no sweep could have reached. CI now runs
the cross-case sweep for every guard (R25-4). This memo is that second
session's record. What the first session read before it chose its target
is not known, beyond what 96a6e6e contains.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R25-1 | med | 8.2 | the improvement round, target rule 8.2 from corpus/uncovered.json | fixed | detectors find_test_only_helpers flags a module-level private helper that a test references and no production file does, the alibi class 8.2 names: a test is not a caller. Deliberately narrow: public names, decorated functions, names in __all__ and helpers nothing references are skipped, and a production file that does not parse makes the walk refuse rather than flag. Case helper-with-test-and-no-caller, whose manifest cites the 8.2 scar, declared count 56 to 57, 8.2 removed from the uncovered queue, all in 96a6e6e. Gate at the branch head: case 0, sweep detectors 0, full corpus 0. verify_guard against 96a6e6e reverts to an import red: exit 2 INCONCLUSIVE with expect naming four 8.2 tests, exit 0 VERIFIED weak without it, because the kept test file imports a function the revert deletes (R25-6). The evidence that counts is the detection line, detectors.py line 400 if not prod_refs and alibis: blinded to if False and ..., three 8.2 tests red and the case MISSED; inverted to if prod_refs and alibis, four tests red, the case FALSE_POSITIVE and the selfcheck red. Restored, sha256 956ece02 before and after. |
| R25-2 | med | 2.9 | this round's own gate, corpus.py sweep detectors, on another case's clean twin | fixed | detectors read source as utf-8, so a byte-order mark reached ast parse as a character it refuses, and a file Python imports and runs was reported does not parse by the import finder and helper callers unknowable by the 8.2 finder. Pre-existing: v0.6.1 and main at b86ef92 flag the same twin, and the twin has existed since v0.6.0 (R24-27). R24-27 moved swallow, interpolation and conflated-degrade to utf-8-sig and missed this sibling, a sibling fix with no class check behind it. The other half was a false negative: find_order_by_without_limit returned the empty list for source that did not parse, the exact shape R24-27 removed from the lints. Fixed as a class. One parse helper feeds all three detectors: it reads utf-8-sig, drops one leading U+FEFF for callers that decoded as utf-8, and catches SyntaxError, ValueError, RecursionError and MemoryError. A file that still cannot parse stays a named does-not-parse violation, which is the library's analogue of the lints' NotJudged: detectors has no CLI exit partition, the violation list is its only channel to the ratchet that banks it, and raising would crash that ratchet and hide every other finding in the walk (6.11). The ORDER BY finder now returns that violation too. The class ratchet in test_parse_encoding_ratchet.py walks every module by AST, propagates ast parse sinks to a fixed point across modules, follows each argument back to its read, and fails on any encoding but utf-8-sig, on any feed it cannot follow, and if a known reader contributes no read. Mutants red: detectors read reverted to utf-8 (the ratchet names detectors.py line 97); the strip and the encoding removed together (four behavioural tests, the selfcheck and the sweep); the strip alone (the decoded-BOM test); the old empty return (its test and the selfcheck). Against the pre-R24-27 lints at 9dfc73c the ratchet names all three. |
| R25-3 | low | 2.9 | the R25-2 class ratchet, on its first run | fixed | framework_only read each guard as utf-8 before parsing its imports, so a BOM-prefixed stdlib-only guard was reported could not parse. A third sibling of R24-27, found by the ratchet and by no sweep: no corpus case gives framework_only a BOM-prefixed guard. Fixed to utf-8-sig, plugin copy re-synced, pair test that a marked stdlib import is clean and a marked third-party import is still the finding. Mutant red: the read reverted to utf-8 reddens the ratchet, naming framework_only.py line 138, and the pair. |
| R25-4 | med | 6.10 | finishing R25-2, asking why CI never saw it | fixed | CI scored each corpus case against its own guard and never swept, so a guard that flagged another case's clean twin was invisible to every CI run. R25-2 lived through a release that way, and only a hand-run sweep found it. Fixed with one corpus.py flag, sweep-all, which runs the sweep for every guard in the registry, so a guard added later is swept with no workflow edit. A new selftest step runs it. Exit precedence is the single sweep's: 2 if any guard measured nothing, else 1 if any flagged a clean twin, else 0. Measured on this laptop, an M2: fifteen separate sweeps 44.1 s, sweep-all 35.0 s, well inside the job's 10-minute timeout, so it was not deferred. Mutants red: the exit line set to 0; the registry read replaced by the fifteen names spelled out; the workflow step absent; detectors put back to 96a6e6e (sweep-all exits 1 naming detectors). |
| R25-5 | med | 2.9 | the maintainer, finding the branch with a commit, a red gate and no memo | deferred | The round's session ended mid-gate and left no memo. Phase 5 says to write the memo even when nothing was proposed, so that a quiet week says so. It says nothing about a round that cannot finish. A stopped round left a commit and a branch, and nothing said the gate was red, which command, or what had been tried. From outside it read like a quiet round. Phase 0b would also have refused next Monday's round on the unmerged branch without saying why it was stuck. Deferred to the maintainer, because skill text changes after review, as with R23-6 to R23-9: the skill should say that a round writes or updates its memo before each gate command, with the step it is on and the last exit code, so a stop leaves a record that names itself as stopped. |
| R25-6 | low | 2.2 | re-running the gate's third command | deferred | The skill accepts only 0 0 0 0 and requires expect naming the new test. It also warns that a brand-new guard reverts only to an import red. Those cannot all hold for a new function in an existing module. With expect, verify_guard reports INCONCLUSIVE and exits 2, because a collection error names no test. Without expect it reports VERIFIED weak and exits 0. So the gate can never read 0 0 0 0 for the case its own warning describes, and the detection-line mutation is the real evidence. Deferred to the maintainer with R25-5: the skill should say the third command reads 2 INCONCLUSIVE or VERIFIED weak there, and that the detection-line mutation replaces it. |
| R25-7 | low | 2.9 | writing the R25-2 ratchet | deferred | The ratchet cannot see Python held in string constants, which is how corpus.py builds its runner bodies. The detectors runner read twins as utf-8 and was invisible to the ratchet. It now reads utf-8-sig, and the detectors strip a leading U+FEFF, so it is safe twice over. A future runner body could still regress unseen. Deferred: following code held in strings means parsing string constants as Python, a heuristic that wants its own false-positive pair before it lands. The ratchet's docstring states the blind spot. |
| R25-8 | low | 2.7 | the maintainer's review of this round | deferred | detectors _module_exports still returns the same None when a module does not parse as when it re-exports with a star - the R24-6 conflation, unchanged. Its baseline entry left only because the handler moved into the new parse helper, where conflated_degrade_lint cannot follow it, so the floor dropped while the defect stayed. Tracked here so the residual register carries it; the fix is to make the two cases distinguishable, as R24-3 did for _json_verdict. |

## What the procedure got wrong

1. **"Write the round memo even when nothing was proposed"** (rule 3 and
   phase 5). The skill covers a quiet round, but not a round that stops.
   This one stopped between phase 3's commit and phase 4. It left a branch
   that phase 0b would hold against the next round, and nothing on that
   branch said why. R25-5.
2. **"accept only on `0 / 0 / 0 / 0`"** with **"`--expect` names the new
   test"** and **"A brand-new guard module only reverts to an import
   error"** (phase 3). For a new function, the three together give 2 on
   the third command every time. R25-6.
3. **Phase 4, "Amend the round commit".** Not followed here, on purpose.
   The finishing session was told never to rewrite 96a6e6e. The gate
   evidence is in the commit messages of 4f379fc and 280d2eb and in this
   memo, and 96a6e6e's message carries none of it. Anyone reading the
   branch reads the evidence in the later commits.
4. **The skill's commands use `python3` for pytest.** On this laptop
   `python3` has no pytest, so the third command was run with
   `--guard-cmd "/usr/bin/python3 -m pytest ..."`. That is a fact about
   the machine, not the skill, and is recorded so the command is not
   copied as written.

## The backflow register

B-48 to B-57 are owed by round 26. Recording round 25 makes none of
them due, and `rounds.py --backflow` exits 0 with this record in place.
This round decided no backflow item.

## Ruled out, and why

- **Raising instead of returning a violation in detectors.** The lints
  raise NotJudged because their CLI has a third exit state. A detector's
  caller is a ratchet whose only states are "shrank" and "did not", so a
  raise is a crash that hides the walk's other findings (6.11). The named
  violation keeps 2.9 and the walk together.
- **Fifteen CI steps, one per guard.** They drift as the registry grows,
  and a guard added without a step is unswept, which is the 2.6 shape of a
  cap that does not count the unit that grows. One flag reads the
  registry.
- **A wall-time budget for sweep-all in docs/design.** Declaring one
  would need a test that runs every guard over the corpus, about 35 s,
  and nothing here has gone slow yet. The measurement is in the commit
  message and the step's comment. It is not a budget.

## Baselines that moved

`.github/sutradhar/conflated_degrade_baseline.json` loses
`detectors.py::_module_exports`. The handler moved into the new parse
helper, so the lint no longer sees an `except` there. The R24-6
conflation itself is unchanged: `_module_exports` still returns None both
for a module that does not parse and for a star re-export, and the
docstring at the site still says so. The entry left because the code's
shape changed, not because the conflation was fixed.

## The perfect score

`INVESTIGATE: perfect score` asks what changed. One case was added and
scores CAUGHT: `helper-with-test-and-no-caller`. It landed in 96a6e6e in
the same commit as the detector, so whether it was written first cannot
be shown from the tree. The finishing session did not edit it or any
other twin. The detectors fix changed what detectors does on
the BOM case's clean twin, which it was never scored against. The two
open cases still score MISSED.
