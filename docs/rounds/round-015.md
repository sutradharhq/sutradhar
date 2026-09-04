# Round 15 - 2026-09-04

Lenses: agent-loop placement, hook honesty, live-doc verification, backflow

**What this round was.** The guards were already available to an agent: in
CI after the fact, and as MCP tools it can call mid-task. Both placements
depend on somebody choosing to run them, and the agent that forgets is the
one that needed them. This round put two of them inside the harness's own
lifecycle - a `PreToolUse` hook that gates `git commit`, and a `Stop` hook
that asks whether the guard on HEAD is real - and packaged them, the MCP
server and the two skills as a Claude Code plugin.

Nothing new is measured. Every verdict a hook reports was computed by a
guard that already existed; the hooks are placement plus an honest
partition of what each exit code means.

## The rule the whole round turns on

**A hook that crashes or cannot run must never block the user.**

This is 2.4 with the stakes raised. An instrument whose error branch cannot
say WHOSE failure it is reports the wrong outage with total confidence, and
always reports it about the subject - the R3-1 class. A hook's version of
that mistake does not merely mislabel a failure: it takes the commit away.
A guard harness that can wedge a session is not a harness, and the first
thing anyone does to one is delete it from their settings, taking every
guard behind it.

So both hooks catch everything, print `instrument failure: <ExceptionType>`
naming themselves, and allow. That branch is not trusted because it was
written; the mutation table below shows it failing.

## Verified against the live docs, not from memory

The plugin and hook surfaces were read on 2026-09-04 from
`code.claude.com/docs/en/{plugins-reference, plugins, hooks, hooks-guide,
discover-plugins}` (the `docs.anthropic.com` paths 301 there). Every URL is
recorded in `docs/design/agent-loop-hooks.md`, with the four things a
plausible memory would have got wrong.

One of the four was not a memory failure but a *reading* failure, and it is
filed below as R15-2: the first pass over the hooks reference was a fetched
**summary** of the page, and it reported the `Stop` decision field as
`hookSpecificOutput.continue`. No such field exists for that event. The raw
page says top-level `decision: "block"` with `reason`. A summariser is a
proxy for a surface, and a field name read off a proxy is not a reading of
the thing - the same class as the prototype that was wrong by 5x in round
13, arriving through a different door.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R15-1 | med | 2.9 | own test suite | fixed | the Stop hook's "already reported this HEAD" marker was keyed on session and commit sha, so two checkouts sharing a commit - a clone, a worktree, or the two identical fixture repos its own tests build in the same second - suppressed each other's report; the second one then went silent, which is indistinguishable from a pass. The repo path is now in the key, and the hook's `--selfcheck` holds it |
| R15-2 | high | 5.1 | self, mid-build | fixed | the first read of the hooks reference was a model summary of the page, and it named a `Stop` decision field (`hookSpecificOutput.continue`) that does not exist - close to the opposite of the real `continue`. Built on it, DECORATION would have silently failed to block on every turn, with a hook reporting success. The raw markdown of every doc page is now the source, and the design note records which fields came from where |
| R15-3 | med | 2.4 | self, design | fixed | the house convention - an unknown flag exits nonzero - would have made a typo in the hook's own configuration exit 2, which is the harness's BLOCK signal: our mistake would have denied the user's tool call. Hook usage errors exit 1 (a documented NON-blocking error), and a source ratchet over the AST of every hook script refuses `SystemExit(2)` and `shell=True` |
| R15-4 | med | 8.1 | self, backflow | deferred | the register's first enforced deadline was met by adopting one item of ten and re-deferring nine. Every reason is real and written down, and that is still a mechanism that has not yet changed behaviour: round 16 must land or reject the section-5 batch (B-7, B-10, B-18) rather than move it again. B-10 has now been deferred twice and was owed from round 7 |
| R15-5 | low | 6.6 | self, verification | deferred | `claude plugin validate ./plugin` is the harness's own schema check and it could not be run here - no `claude` on PATH in this environment. The plugin's conformance is asserted by a ratchet against the documented schema, which is a weaker witness than the validator, and the README says to run it before installing. Recorded rather than implied |
| R15-6 | low | 6.1 | self, operating | fixed | the `Guard-cmd:` trailer on this round's own commit named `python3 -m pytest python/tests/...`, which cannot import `sutradhar_guards` from the repo root and dies in collection. It reads correctly and does not run. Caught by running it rather than by reading it, and amended to the `cd python && python3 -m pytest tests/...` form CI uses. A trailer that does not run makes `verify_guard` answer INCONCLUSIVE forever, which is the honest verdict about a useless input and a silent hole in the per-commit check |
| B-15 | med | 2.2 | backflow | closed | closed by this round: a gate must prove it gated the tree you are pushing. The pre-commit gate reads the working tree, `git commit` takes the index, and the hook now names which one it measured and lists the staged paths that differ. Recorded under its register id so the register actually clears it |

## What was ruled out (7.4)

- **Blocking on INCONCLUSIVE.** 2.9 says a check that could not run has not
  passed, and the temptation is to make the Stop hook block on it. But its
  usual causes - dirty tree, merge commit, no git - cannot be fixed by the
  agent working longer, and a Stop block that cannot be satisfied is a loop
  the harness has to break after eight turns. It is reported by name, to the
  user, and never reads as a pass.
- **Running the test suite in the pre-commit hook.** It would catch the
  most and it costs 19 s on this repo. R14-2 is a correct guard that was
  switched off the same afternoon because its signal cost more than it paid;
  a gate on every commit has that failure with a shorter fuse.
- **A `SessionStart` hook injecting `agent/packs/CLAUDE-snippet.md`.** It
  would make the doctrine genuinely non-optional and would spend every
  session's context without asking. If it ships, it ships opt-in, with a
  measured token cost, in its own note.
- **Copying the MCP server or the skills into the plugin.** One server, one
  version: a copy is a second answer to "what does `verify_guard` do", and
  the first time they disagreed the copy would win silently. The plugin
  references both through `${CLAUDE_PLUGIN_ROOT}`, and a ratchet asserts one
  wrapper per canonical skill so a skill added later cannot be silently
  un-shipped.
- **A marketplace manifest for a one-command persistent install.**
  Distribution has its own surface - auto-update, pinning, catalogs - and
  `--plugin-dir` is documented, verified, and deliberately per-session,
  which is the right default for something that can deny a commit.
- **Installing the hooks into this repo's `.claude/settings.json`.** A
  blocking hook installed without the maintainer typing the command is
  precisely the failure this design exists to avoid. Doing it in the commit
  that ships the design would have been a fine joke and a bad commit.

## Budget (1.1)

`precommit-gate`: 10 gated commits, 2,500 ms, 16 MB, `ci_slack` 2.0.
Measured on the shipping hook over a real fixture repository: **155-172 ms**
per gated commit (1,548-1,722 ms for ten), fast path **28-29 ms** against a
bare interpreter's 14-15 ms, or **1.93-2.09x** of a ceiling of 3.0x.

The pre-code prototype said 269-284 ms - **1.7x too high**, because it
pointed both lints at the whole `python/` tree while the shipping hook
scopes `interpolation_lint` to the staged files. Wrong in the forgiving
direction, which is luck rather than method; the ceiling is set from the
shipping number, and both readings are kept in the note.

The ceiling was placed by asking what it must catch, not by scaling the
baseline: `verify_guard` in the pre-commit path adds ~700 ms per run, so ten
runs land near 8,600 ms and trip the enforced 5,000 ms. The habitual
"3x baseline, doubled for CI" would have been 9,600 ms and would have missed
exactly that regression.

## Mutation verification (2.2)

Every branch was shown able to fail before it was trusted. Red counts are
against `python/tests/test_agent_loop_hooks.py` (35 tests).

| guard | mutant | result |
|---|---|---|
| the honesty rule | catch-all removed from `main_guarded` | 2 red |
| | instrument failure denies instead of allowing | 5 red |
| | unknown flag exits 2 (the blocking code) | 3 red |
| exit-code partition | unknown code falls through to GREEN | 4 red |
| commit detection | `is_git_commit` becomes a substring match | 2 red |
| | `git commit -a` no longer widens the scope | 1 red |
| the verdict path | a red guard is allowed instead of denied | 3 red |
| | skips are not reported in the summary | 1 red |
| | the tree the gate measured is not named (B-15 reverted) | 1 red |
| Stop hook | INCONCLUSIVE is read as a pass | 2 red |
| | `stop_hook_active` ignored | 1 red |
| | marker key drops the repo path (the R15-1 regression) | 1 red |
| | the production+test reminder never fires | 1 red |
| budgets | a 450 ms sleep in the gate path (a slow guard moving in) | 2 red |
| | the fast path does git work before it knows it is a commit | 1 red |
| source ratchets | `shell=True` on a path that never runs | 1 red |
| plugin ratchets | `hooks.json` registers an event name that does not exist | 1 red |
| | a canonical skill loses its plugin wrapper | 1 red |
| backflow gate | B-15 returned to `owed` at round 15 | exit 1, naming the item (exit 0 when the decision is restored) |

## End-to-end smoke (6.1)

The gate was driven against this repository for real, not only through the
test fixtures:

| case | outcome |
|---|---|
| a staged file with an f-string SQL interpolation, `git commit -m red` | **deny**, reason carried `interpolation_lint`'s own text including the file, line and `{tenant}`, plus `rounds OK` and `swallow_lint skipped (no swallow_baseline.json)` |
| the same file modified after staging | the deny reason added `1 staged path(s) differ from the working tree`, naming it |
| nothing staged, `git commit -m x` | **allow**, one line: `rounds OK`, both lints named as skipped |
| `ls -la` | **allow**, silent, no guard spawned |
| `SUTRADHAR_HOOK_SELFTEST=raise` | **allow**, `instrument failure: RuntimeError`, nothing denied |
| `SUTRADHAR_GUARD_DIR=/nope/nothing` | **allow**, `instrument failure`, the path named, nothing denied |
| the Stop hook against this repo's own HEAD, trailer present | **silent** - and silence was not taken as the witness: `verify_guard` was then run directly on the same commit and answered **VERIFIED** (6 production files reverted, the test file kept, red by assertion without them) |
| the `Guard-cmd:` trailer as first written | **not runnable** - see R15-6 |

370 tests before, 405 after.
