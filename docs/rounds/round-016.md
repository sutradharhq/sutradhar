# Round 16 - 2026-09-04

Lenses: security audit, distribution, token budget, mutation honesty

**What this round was.** Round 15 put two guards inside the agent's own
loop and packaged them as a plugin. A security audit of that plugin, run
after it shipped, found two doors: one that let a model choose a shell
command, and one that let the author of whatever commit happened to be at
HEAD choose a command that ran on the developer's machine. Reading the
plugin distribution docs at the same time found a third thing, which is not
a security problem and is arguably worse: the plugin only worked in the
layout it was built in.

Nothing in this round was found by the test suite. Two findings came from an
audit, one from reading a documentation page, one from a measurement nobody
had taken, and two from reviewing the round before it. The suite that went
from 405 tests to 453 was green throughout.

## The two doors

**A guard command was a shell command.** `verify_guard` ran `--guard-cmd`
through `shell=True`, with the caller's environment, as the caller. That is
fine when the string is typed by a person and reviewed by the same person.
It stopped being fine the moment the same function sat behind an MCP tool
whose `guard_cmd` argument is free text written by a model, with the output
returned into context. `--setup-cmd` was the same door with a different sign
on it.

The fix is a seam rather than a guard (1.2): the string is `shlex`-split
into an argv list and spawned directly, so a pipeline is not something the
tool declines to run, it is something the tool cannot express. One prefix
survives, because every `Guard-cmd:` trailer in this repository's history
uses it and R15-6 is what happens when a trailer stops running: `cd <dir>
&&`, where the directory must resolve inside the worktree.

**A commit trailer was a command.** The Stop hook read `Guard-cmd:` off
HEAD's commit message and passed it to `--guard-cmd`. HEAD is whatever is
checked out. Checking out a pull request, pulling upstream, or merging a
contributor is enough to make somebody else's commit message the input, and
the command then ran when the developer's session ended. The throwaway
worktree is not a sandbox: same uid, same `$HOME`, same environment
variables, same network.

The hook now compares HEAD's author email with `git config user.email` and
runs nothing when they differ, or when the repository has no identity at
all. It says whose commit it is, why it did not run the trailer, and the
exact one-line command to run it by hand - because a silent refusal reads
exactly like a pass (2.9).

## Tested only in the layout it was built in

The third finding has no attacker in it. `plugin/.mcp.json` and
`_hooklib.guard_dir()` both pointed at
`${CLAUDE_PLUGIN_ROOT}/../python/sutradhar_guards`. Round 15 chose that
deliberately - referenced, not copied, so there would be one server and one
version - and the reasoning was good. What it did not know is that **Claude
Code copies an installed plugin into `~/.claude/plugins/cache`, and files
outside the plugin directory are not copied.** The documentation says it
outright.

So `../` was not a lighter-weight alternative to copying. It was a plugin
that worked from a checkout and would have been missing its guards the first
time anybody installed it. Every test passed, because every test ran from
the checkout. That is the class: **tested only in the layout it was built
in**, and it is invisible from inside that layout by construction.

The round-15 argument is answered rather than dropped. The eight guard
programs the plugin runs are bundled under `plugin/guards/`, and a test
fails on a one-byte divergence from `python/sutradhar_guards/`. Two answers
to "what does `verify_guard` do" are only dangerous while nothing compares
them.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R16-1 | high | 2.3 | docs, read directly | fixed | the plugin referenced `${CLAUDE_PLUGIN_ROOT}/../python/sutradhar_guards` from both `.mcp.json` and `_hooklib.guard_dir()`, so it worked from a checkout and would have failed the first time anyone installed it from a marketplace - installed plugins are copied without the files around them. Found by reading the distribution docs, not by a test; the class is "tested only in the layout it was built in", which no test inside that layout can see. Fixed by bundling the eight guard programs the plugin runs under `plugin/guards/`, pinned byte-for-byte to their sources by `test_plugin_bundle.py`, plus a ratchet refusing `${CLAUDE_PLUGIN_ROOT}/..` in any plugin config |
| R16-2 | high | 1.2 | security audit | fixed | the Stop hook read a `Guard-cmd:` trailer off HEAD's commit message and ran it as a shell command, with no author check and no filtering. Whoever authored HEAD chose a command that ran on the developer's machine when their session ended - checking out a pull request, pulling upstream or merging a contributor is enough to reach it, and the throwaway worktree shares uid, `$HOME`, environment and network. The hook now runs a trailer only when HEAD's author email matches `git config user.email`, treats an unset identity as "not mine", and otherwise names the author and prints the command to run by hand |
| R16-3 | high | 1.2 | security audit | fixed | `verify_guard.run_guard()` ran the guard command with `shell=True`, inherited environment, same user - and the MCP `verify_guard` tool takes `guard_cmd` as free text from the model, so that tool was an arbitrary shell with its output returned into context. `--setup-cmd` was the same door. Fixed as a seam rather than a guard: the command is parsed into an argv list and spawned directly, one program with arguments plus an optional `cd <dir> &&` prefix that must resolve inside the worktree; anything a shell would be needed for is refused as INCONCLUSIVE. The MCP tool now opens its description with the warning, and every tool's `repo` argument is confined to the git toplevel of the server's own cwd |
| R16-4 | med | 1.1 | measurement | fixed | the nine MCP tool schemas serialised to 20,718 bytes - roughly 5,200 tokens - spent in every session whether or not a tool was ever called, and the per-call output cap of 65,536 bytes per stream was ~16k tokens worst case. Neither number was declared and neither had a test: 1.1 pointed at the resource an agent actually runs out of. `tools/list` is now 7,270 bytes under a declared ceiling of 8,192, cut by moving repetition into the server's `instructions` rather than by dropping facts; the output cap is 8,192, and a truncated call's full output is written to a file the notice names |
| R16-5 | med | 2.8 | self, review | deferred | `interpolation_lint` detects f-string interpolation into a query-language string and does not detect `%`-format: `"SELECT * FROM t WHERE n = '%s'" % name` is the same hole in an older spelling and passes clean. Not fixed in this round - it is a detector change with its own false-positive surface, and shipping it inside a security round would mix a fix with a redesign. Recorded as backflow B-20 with a by-round, so it cannot quietly wait |
| R16-6 | med | 2.2 | self, review | deferred | three mutation attempts during the review of round 15 edited a declaration or a non-executing string instead of the runtime seam, and each reported "no change" - which reads as "the guard is decoration" when it means "the mutation never ran". This is the third occurrence of the class across rounds 13-15. It is a practice, not a rule: 2.2 already says revert the fix and watch it go red, and what is missing is the habit of asking WHICH line executes before editing it. Recorded as backflow B-21 |
| R16-7 | low | 6.6 | self, verification | deferred | `claude plugin validate .` still has not been run - there is no `claude` CLI on this build machine. The plugin's conformance to the manifest and marketplace schemas is asserted by ratchets written against the documented shapes, which is a weaker witness than the validator itself, and the README tells an installer to run it. R15-5 recurring, recorded rather than implied |
| R16-8 | med | 1.1 | CI, Linux runner | fixed | the PreToolUse fast path - the branch that fires on every Bash call and must cost about a bare interpreter start - imported `pathlib`, `subprocess` and (through both) `re` at module level, before it had established that the command was a commit. On macOS that measured 1.9x a bare start, under the 3.0x ceiling; on the Linux runner, where the interpreter itself starts faster, the same imports measured 3.2x and CI went red on 2efaca5. The push was reported as "CI queued" and not followed up; the red was found one push later. Fixed by importing all three inside the functions that need them and by refusing to tokenise at all unless the raw command contains `commit` once quotes and backslashes are stripped (a necessary condition for any token to normalise to it). Re-measured on the same machine: 1.47x, from 1.88x. Two guards: the ratio test now takes the minimum over its rounds rather than the mean, because a startup cost has a floor and noise only adds; and a deterministic ratchet (`test_fast_path_loads_none_of_the_heavy_modules`) runs the fast path under `-X importtime` and fails if `pathlib`, `subprocess` or `shlex` was loaded, because the ratio's slack is machine-dependent and this is not. The first draft of the fix put the lazy `pathlib` import at the top of `gate()`, above the early return - the ratchet caught that before the ratio test could |

## The backflow register comes due, and this round did not answer it

Recording round 16 makes thirteen register items overdue at once: **B-5,
B-7, B-8, B-9, B-10, B-11, B-12, B-13, B-14, B-16, B-17, B-18 and B-19**
all carry `by-round: 16` and are still `owed` or `deferred`. The gate
therefore fails:

```
python3 python/sutradhar_guards/rounds.py docs/rounds/ --backflow docs/backflow.md
```

**That is the mechanism working, and it is left failing on purpose.** R15-4
said in as many words that round 16 must land or reject the section-5 batch
rather than move it again, and this round was a security round: it did not
do that work, and re-deferring thirteen items to make a gate go green would
be exactly the behaviour R15-4 was filed to stop. A red gate that names
thirteen undecided items is an honest report of where the register stands.
Deciding them is the next round's first job, not a tidy-up at the end of
this one.

## Measured, not estimated

| Number | Before | After |
|---|---|---|
| serialised `tools/list` payload | 20,718 bytes (~5,200 tokens) | **7,270 bytes**, ceiling 8,192 |
| `verify_guard`'s own schema entry | 2,895 bytes | 1,330 bytes |
| shared output schema, per tool x9 | 961 bytes (8,649 total) | 62 bytes (558 total) |
| `MAX_OUTPUT_BYTES` per stream | 65,536 (~16k tokens/call) | **8,192**, with the remainder spilled to a named file |
| tests | 405 | **453** |

The `tools/list` figure is measured over the real transport by
`test_tool_schemas_fit_a_token_budget`, not computed from the table: the
bytes that cost anything are the ones that cross the pipe. The cut is
repetition, not facts - the `repo` and `timeout_s` argument descriptions and
the field-by-field shape of a result object identical for all nine tools now
appear once, in the server's `instructions`, instead of nine times.

## Mutation verification (2.2)

Every fix was shown able to fail before it was trusted. Commands are given
because "mutation-verified" without them is a claim about work nobody can
repeat.

Each mutant was applied by editing the file, running the named test file
with `cd python && PYTHONPATH=. python -m pytest tests/<file> -q`, and
restoring from a backup taken first.

| commit | mutant | result |
|---|---|---|
| `time.sleep(0.05)` at the top of `gate()`, the fast path | **1 red**: `fast path 84.3 ms vs bare interpreter 13.3 ms = 6.3x, over the declared 3.0x` |
| 1 | `shell=True` restored in `verify_guard.run_guard`, early parse removed | **7 red** in `test_verify_guard.py` |
| 1 | the author check deleted from `verify_before_done.check` | **2 red** in `test_agent_loop_hooks.py` |
| 1 | `confined_cwd()` replaced by the old `arguments.get("repo") or os.getcwd()` | **3 red** in `test_mcp_server.py`, one of them the server's own `--selfcheck` |
| 2 | one newline appended to `plugin/guards/rounds.py` | **2 red** in `test_plugin_bundle.py` |
| 2 | a tool whose `module` is `no_such_guard` added to the MCP table | **4 red** in `test_plugin_bundle.py` |
| 2 | `guard_dir()` reverted to `parents[2] / "python" / "sutradhar_guards"` | **1 red** in `test_plugin_bundle.py`, and by hand: the gate reported `instrument failure: no guard directory` instead of denying - R16-1 reproduced |
| 3 | the spill write replaced by `spilled = ""` | **1 red** in `test_mcp_server.py` |
| 3 | `TOOLS_LIST_MAX_BYTES` raised to 65,536 | **1 red** (the note/constant mirror) |
| 3 | the shared result-field list pasted back into one tool description (8,266 bytes) | **2 red**, one of them the `--selfcheck` |

The `shell=True` mutant is worth quoting, because it did not only redden the
new tests - it reproduced the older defect underneath. With a shell,
`sutradhar-no-such-program-anywhere --now` came back as **exit 127, read as
the guard going RED**: a verdict about a process that never started. Without
one it is an `OSError` that says the program could not be started, and the
verdict is INCONCLUSIVE.

## End-to-end drill: the installed layout (6.1)

The R16-1 fix is not asserted, it is witnessed. `plugin/` was copied to a
temporary directory with nothing around it - which is what an install is -
and both hooks were driven there against a fresh fixture repository, with
every `SUTRADHAR_*` variable stripped from the environment.

| case | outcome |
|---|---|
| pre-commit gate, a staged f-string SQL interpolation | **deny**, carrying `interpolation_lint`'s own text and the `dirty.py:2` line |
| the same drill, as a committed test | `test_the_hooks_find_their_guards_when_the_checkout_is_not_there` - a drill nobody re-runs is a memory (6.1), so it asserts the **deny** rather than the absence of a crash |
| Stop hook, HEAD carrying a trailer, author matches | ran `verify_guard` from the bundle and reported its real verdict |
| the same drill with `guard_dir()` reverted to `../python` | **`instrument failure: no guard directory`** - R16-1, reproduced exactly, and note that it allows rather than blocks |
| bundled `plugin/guards/mcp_server.py` over real stdio, temp cwd, `PYTHONPATH` stripped, no env overrides | `tools/list` returned all nine tools and a `tools/call` ran a guard green |
| `python3 plugin/guards/mcp_server.py --selfcheck` | exit 0 in 0.19 s, run against the COPY rather than the source |

## What was ruled out (7.4)

- **Deciding the thirteen overdue backflow items to make the gate green.**
  See above. The register is a mechanism for making an unmoved item cost
  something; spending this round's last twenty minutes moving all thirteen
  would have cost nothing and proved R15-4's point a second time.
- **Fixing R16-5 (`%`-format interpolation) in this round.** It is a
  detector change with its own false-positive surface - `"...%s..." % x`
  where the string is not a query, `%`-formatting inside a logging call -
  and a security round is the worst place to also redesign a lint. Filed as
  B-20 with a deadline instead.
- **Making R16-6 a doctrine rule.** "Mutate what runs, not what you can
  see" is a practice with three occurrences and no recorded cost beyond
  wasted review time. 8.1 says a rule enters with the incident that paid for
  it, and the backflow register's own `evidence` column refuses a
  `practice` item founding a new rule. B-21 is filed as `practice` against
  2.2, where it can strengthen a mechanism and not found one.
- **Extending `framework_only.py` to scan `plugin/guards/` as a second
  guard surface.** It would look like the careful thing and would be
  redundant: the bundle is byte-identical to `python/sutradhar_guards/` by
  test, and no file may sit in the bundle without appearing in the sync
  list, so a third-party import in a copy is impossible without the same
  import in the source - which `framework_only.py` already scans. Recorded
  because the next session will otherwise reach for it.
- **Exposing the spill file through an MCP tool.** A tool that reads back
  its own truncated output is a second unbounded read wearing a helpful
  face. The path is named; reading it is a `cat`.
- **Blocking, rather than reporting, when HEAD was authored by somebody
  else.** The Stop hook allows and says so. Nothing is wrong with the user's
  work, and a hook that stops a turn over the provenance of a commit
  somebody else wrote is a hook that gets uninstalled (R14-2).
- **Lifting the MCP `repo` confinement by default for multi-repository
  sessions.** Real, and it needs a session-level answer rather than a
  per-call one. `SUTRADHAR_MCP_ANY_REPO=1` is the deliberate escape hatch
  and the refusal message names it.

405 tests before, 453 after.
