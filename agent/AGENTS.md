# Operating rules for coding agents

Drop-in rules for any AI coding agent working on this codebase. Append to
your `CLAUDE.md` / `AGENTS.md` / rules file, or reference it from there.
Every rule below was earned by a real defect; the full stories are in
[DOCTRINE.md](../DOCTRINE.md).

## Before building anything

1. **State cardinalities and budgets first.** Name the N this must survive
   (rows, users, requests/s) and the latency/memory envelope, as numbers, in
   the plan or PR description. If you cannot name N, find out before writing
   code.
2. **Write the failure story.** For each dependency touched: what does the
   user see when it is down, slow, or partial? "Same as success" means the
   design is not done.
3. **Orient before starting.** Read the owning plan or tracker AND
   spot-check its claims against the tree. Parallel sessions finish things;
   a two-minute grep beats a day of duplicate work. Trust the tree, not the
   doc.

## While building

4. **Verify against runtime state, not appearance.** Backend: exercise the
   real seam (route, transport, public function) and read the actual
   response, the actual DB rows. Frontend: assert on network responses,
   store values, and console via runtime observation; never eyeball a
   screenshot to conclude "works".
5. **Exit-code discipline.** Never pipe a build or test through anything
   that swallows `$?`. Capture exit codes explicitly. An exit-137 run with a
   green-looking tail is a killed run, not a passing one; compare the test
   count against the expected total every time.
6. **Honest degradation.** Failures state themselves. No silent fallbacks,
   no fabricated values, no empty result that reads as "genuinely nothing
   here" when the truth is "the read failed". Never return "ok" wrapping an
   error.
7. **No unbounded reads.** Any query or sweep over a collection that grows
   with usage gets a cap and an honest too-large refusal.

## Before committing

8. **Every fix ships with a guard in the same commit.** Prefer extending an
   existing class ratchet over adding a point test. New test files are the
   exception, not the rule.
9. **Mutation-verify the guard.** Revert the fix: the test must go red.
   If you cannot make the guard fail, the guard is decoration - fix the
   guard, not the report. Do not do this by hand and do not claim it
   without running it:

   ```bash
   python scripts/verify_guard.py --guard-cmd "<the command that runs your guard>"
   ```

   Exit 0 = the guard is real. Exit 1 = it passed without the fix and is
   decoration. Exit 2 = inconclusive, which is never a pass. Paste the
   verdict into the PR; "I verified it" is not evidence.
10. **Test through the route, not just the helper.** A helper-level test
    structurally cannot see an import error in the handler that calls it.
11. **Stage only named files. Never `git add -A`.** Check
    `git status --porcelain` after staging, before committing, every time.
    Never touch other sessions' work-in-progress.
12. **Update the docs the same commit.** A stale status doc misleads every
    future session, including your own next one.

## When investigating

13. **Verify a finding refutes the null before filing it.** Prove the test
    itself is valid first. A false finding costs more trust than no
    finding.
14. **Prove pre-existing vs regression before touching a failure.** Run the
    same test at the baseline commit (a worktree makes this cheap). Date
    root causes with `git log -S`.
15. **Check the premise against the code before implementing.** Backlog
    one-liners are wrong in both directions; read the actual call path
    first.
16. **Record what you ruled out** where the next session will look.

## Multi-agent hygiene

17. **One worktree per agent.** Explicit staging is not sufficient
    protection on a shared tree; a parallel session's `git add <file>` can
    capture your unstaged edits.
18. **Serialize runs that share a backend.** Concurrent test runs against
    one service poison each other's verdicts.
19. **Bounded waits only.** No endless polling. If a wait loop's producer
    dies, the loop spins forever.

## Honesty in output

20. **Report outcomes faithfully.** Tests failed: say so, with the output.
    A step was skipped: say that. Never present a truncated run as
    complete.
21. **Every number you publish carries its provenance** - measured,
    estimated (with assumptions), or illustrative. In the artifact, not in
    your head.
