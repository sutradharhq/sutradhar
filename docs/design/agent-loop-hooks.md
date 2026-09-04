---
sutradhar_scar: R16-1, R16-2, R16-3
sutradhar_scar_argument: This note entered on `distribution` in round 15 - no finding said a missing session hook had lost anything, and what it argued was placement rather than a new guard. Round 16 paid for it. R16-1 (the plugin referenced `${CLAUDE_PLUGIN_ROOT}/../python`, so it worked only from a checkout and would have failed after a marketplace install), R16-2 (the Stop hook ran a `Guard-cmd:` trailer written by whoever authored HEAD, on the developer's machine) and R16-3 (`verify_guard` ran its command through a shell, reachable from an MCP tool argument written by a model) are all defects in the mechanism this note designs. Two older findings still shape its constraints without founding it and are cited in the text: R14-2 is why it carries a latency budget at all, and R3-1 is why a broken hook allows.
sutradhar_budget: precommit-gate
n: 10
n_unit: gated commits
p95_ms: 2500
memory_mb: 16
ci_slack: 2.0
---

# Design note: the harness inside the agent's loop

<!-- Written before the code (1.1). The doc URLs below were read on the day
     stated; the numbers were measured first and chosen second. -->

## What and why

Every placement of these guards so far has been something a person or a
pipeline chooses to run. CI runs them after the agent has stopped.
`mcp_server.py` makes them callable mid-task — but only by an agent that
decides to call them, and an agent that forgets is exactly the agent that
needed them.

This is the third placement, and the first that does not depend on anyone
remembering. Claude Code fires hooks at fixed points in its own lifecycle;
a hook on the tool event that precedes `git commit` runs whether or not the
agent thought of it. That is the whole claim: **available** becomes
**non-optional**, for the one session that installs it.

Nothing here is a new guard. Two hooks, both stdlib Python, both shelling
out to guard CLIs that already exist, wrapped in a plugin that also carries
the MCP server and the two skills.

## Verified, not remembered <!-- 6.6 -->

The Claude Code plugin and hook surfaces were read on **2026-09-04**:

| Page | URL |
|---|---|
| Plugins reference (layout, manifest schema, `.mcp.json`, `${CLAUDE_PLUGIN_ROOT}`, `hooks/hooks.json`, component discovery) | <https://code.claude.com/docs/en/plugins-reference> |
| Create plugins (`--plugin-dir`, skills layout, migration) | <https://code.claude.com/docs/en/plugins> |
| Hooks reference (event list, per-event input, decision control, exit codes) | <https://code.claude.com/docs/en/hooks> |
| Hooks guide (`stop_hook_active` loop cap, timeouts, troubleshooting) | <https://code.claude.com/docs/en/hooks-guide> |
| Discover and install plugins (marketplace vs local install) | <https://code.claude.com/docs/en/discover-plugins> |

`docs.anthropic.com/en/docs/claude-code/*` answers **301** to
`code.claude.com/docs/en/*`; the redirect target is the live page.

Three things a plausible memory would have got wrong, and one thing a
plausible *reading* did:

- The manifest is `.claude-plugin/plugin.json`, and **every other component
  directory sits at the plugin root, not inside `.claude-plugin/`.** The
  docs call the inverse the common mistake.
- The plugin-root variable is spelled **`${CLAUDE_PLUGIN_ROOT}`**, and it is
  substituted into skill and agent *content*, hook `command` and `args`, and
  MCP `command`/`args`/`env` — which is what makes reference-not-copy
  possible below.
- `PreToolUse` and `Stop` do **not** share a decision shape. `PreToolUse`
  puts its verdict in `hookSpecificOutput.permissionDecision`
  (`allow`/`deny`/`ask`/`defer`) with `permissionDecisionReason`; top-level
  `decision`/`reason` are **deprecated for that event**. `Stop` uses the
  top-level `decision: "block"` + `reason`, and additionally accepts
  `hookSpecificOutput.additionalContext` for feedback that continues the
  conversation without being reported as a hook error.
- **The thing a reading got wrong.** The first pass over the hooks
  reference was a fetched *summary* of the page, and it reported `Stop` as
  taking `hookSpecificOutput.continue`. No such field exists for `Stop`;
  `continue` is a universal field meaning "stop processing entirely", which
  is close to the opposite. The raw page, read directly, says
  `decision: "block"`. A summariser is a proxy for a surface, and a number
  — or a field name — read off a proxy is not a reading of the thing
  (5.1, and the same class as the prototype that was wrong by 5x in
  [mcp-server.md](mcp-server.md)). Every field name in this note comes from
  the raw markdown of the page, not from a summary of it.

## The two hooks

### `PreToolUse` — the pre-commit gate

Matcher `Bash|PowerShell` (the docs are explicit that a `Bash`-only matcher
never fires on Windows where the PowerShell tool is primary). The hook
reads `tool_input.command`, and **exits immediately unless that command
actually runs `git commit`** — including inside `&&` chains and `$(...)`,
and excluding the spellings that are not a commit (`git commit --help`,
`git log ... commit`, `git commit-graph`).

When it is a commit, it runs the fast guards over the repo:

| Guard | Run when | Scope |
|---|---|---|
| `interpolation_lint` | any `.py` file is staged | the staged `.py` paths only |
| `swallow_lint` | a `swallow_baseline.json` exists | the whole tree, against that baseline |
| `rounds --check` | `docs/rounds/` exists | that directory |

Red → **deny**, with the guard's own stdout/stderr as
`permissionDecisionReason`. Not a paraphrase: the agent gets the text a
person would have seen, so it can act rather than re-run the guard to find
out what happened.

Not applicable → **allow**, and say so. A guard that did not run is
reported as not run, never folded into a green verdict (2.9). The commonest
case is the honest one: an adopter with no `swallow_baseline.json` has no
ratchet to violate, and a gate that blocked on the absence of its own
instrument would be uninstalled within the hour.

**Which tree the verdict is about** (backflow B-15: *a gate must prove it
gated the tree you are pushing, not some tree*). These guards read the
working tree. `git commit` commits the index. Those are the same tree only
when nothing staged differs from what is on disk, and a hook that quietly
implies otherwise is claiming a measurement it did not take. So the gate
names its subject: it compares `git diff --cached --name-only` against
`git diff --name-only`, and when any path appears in both — staged content
that is not what is on disk — the message says the working tree was
measured and names the paths where the two disagree. It does not stash, it
does not check out, and it does not pretend.

### `Stop` — verify-before-done

Fires when the agent finishes responding. Reads `stop_hook_active` first
and exits 0 the moment it is true: the docs cap a `Stop` hook at eight
consecutive continuations, and a hook that has to be overridden by the
harness is a hook that will be removed by the user.

Then it greps HEAD's commit message for a `Guard-cmd:` trailer — the
convention `ci/guards.yml` already reads — and:

| HEAD | Verdict | What the hook returns |
|---|---|---|
| `Guard-cmd:` present, author is not you | **not run** | exit 0 with `systemMessage` naming the author and the command to run by hand |
| `Guard-cmd:` present, `verify_guard` says VERIFIED | pass | exit 0, silent |
| `Guard-cmd:` present, DECORATION | block | `decision: "block"` + `reason` carrying the verifier's own text |
| `Guard-cmd:` present, INCONCLUSIVE | **inconclusive** | exit 0 with `systemMessage` naming it INCONCLUSIVE and what would resolve it |
| no trailer, commit touches production **and** test files | reminder | exit 0 with `systemMessage` |
| no trailer, anything else | pass | exit 0, silent |

**Whose command is it** (R16-2). The author row comes first because it is
checked first, before the trailer is anywhere near a subprocess. A
`Guard-cmd:` trailer is a command, and HEAD is whatever is checked out:
checking out a pull request, pulling upstream, or merging a contributor all
make somebody else's commit message the input to this hook, and the command
then runs on this machine, as this user, when the turn ends. The throwaway
worktree `verify_guard` builds is not a sandbox — same uid, same `$HOME`,
same environment, same network.

So the hook compares HEAD's author email (`git log -1 --format=%ae`) with
`git config user.email` in that repository and runs the trailer only when
they match. An unset `user.email` is treated as *not* a match and said so by
name: a repository with no identity cannot assert that the commit is yours,
and defaulting to "run it" would switch the check off on exactly the
machines least configured to have one. The message names the author, says
the hook only runs trailers written by the current git user, and prints the
exact one-line `verify_guard` invocation — because a silent refusal reads
exactly like a pass (2.9).

**And what the command may be** (R16-3). `verify_guard` no longer runs its
`--guard-cmd` or `--setup-cmd` through a shell. The string is `shlex`-split
into an argv list and spawned directly; the only prefix that survives is
`cd <dir> &&`, whose directory must resolve inside the worktree. Everything
else a shell would be needed for — a pipe, a redirection, `;`, a stray
`&&`, a backtick, `$(`, a bare `$` — is refused, and a refusal exits 2
(INCONCLUSIVE) because no guard ran. That is 1.2 rather than a filter: a
pipeline is not something the tool declines to run, it is something the tool
cannot express.

INCONCLUSIVE is not a pass and is not a block. It is reported under its own
name, to the user, in a message that says what the verifier could not
determine and why (2.9). Blocking on it was considered and rejected below.

**Once per HEAD per session.** `Stop` fires on every turn, and
`verify_guard` builds a worktree and runs a test suite twice. Re-running it
every turn — and re-blocking every turn — is how this hook would earn its
own uninstall, so a marker under the system temp directory (never the
user's repo) records that a HEAD has been reported. That also means a
DECORATION verdict blocks at most once and can never drive the harness's
8-continuation cap.

The marker's key is `(session, repo path, sha)`, and the repo path is in it
because of **R15-1**: keyed on `(session, sha)` alone, two checkouts sharing
a commit — a clone, a worktree, a fork, or the two identical fixture repos
this hook's own tests build in the same second — suppress each other's
report. The second one then goes silent, which is indistinguishable from a
pass. It was caught by a test that expected a message and got nothing, which
is the only reason it is in this note and not in production.

## The honesty rule <!-- 2.4, and the R3-1 class -->

**A hook that crashes or cannot run must never block the user.** It prints
what failed, names itself as the failing party, and allows.

This is not politeness. An instrument whose error branch cannot distinguish
*"the subject failed"* from *"I failed"* reports the wrong outage with total
confidence, and it always reports it about the subject — the R3-1 scar, and
the same distinction `mcp_server.py` turns on. A hook has a sharper version
of the problem: its error branch does not merely mislabel a failure, it
**takes the user's commit away**. A guard harness that can wedge a session
is not a harness; it is a hostage-taker, and the first thing anyone does to
one is delete it from their settings.

So both hooks wrap everything — payload parse, git calls, subprocess spawn,
their own logic — in a single top-level catch that prints
`[sutradhar-hooks] instrument failure: <ExceptionType>: <msg>` and exits 0.
The message says `instrument failure` and names the exception **type**,
because "something went wrong" attached to a commit is read as a finding
about the commit. The catch is verified by mutation, not by inspection: a
`SUTRADHAR_HOOK_SELFTEST=raise` environment variable makes the hook raise
inside its own body, and a test asserts the process still exits 0, prints
the marker, and denies nothing.

Three narrower cases are covered by the same rule:

- A guard file that is missing or not executable is an instrument failure,
  not a red guard.
- A guard that exceeds its per-guard timeout is reported as timed out, and
  allows. The agent is told the guard was killed — never that the code
  passed.
- A guard that exits on a code outside its documented partition (the
  partition is the one `mcp_server.py` already established, quoted below)
  is an instrument failure. An unrecognised exit code is not a verdict.

| Guard | Result exit codes | Instrument failure |
|---|---|---|
| `verify_guard` | `0` VERIFIED, `1` DECORATION, `2` INCONCLUSIVE | anything else |
| `swallow_lint`, `interpolation_lint`, `rounds` | `0` OK, `1` FINDINGS | `2` (usage) and anything else |

## Cardinalities and budgets <!-- 1.1 -->

| Dimension | Design N | Enforced by |
|---|---|---|
| gated commits in one measured run | 10 | `test_precommit_gate_holds_its_declared_envelope` |
| wall clock for those 10 gate runs | 2,500 ms (x2 CI slack) | same |
| peak Python heap in the parent across them | 16 MB (x2 CI slack) | same |
| fast-path cost, as a multiple of a bare interpreter start | 3.0 (`FAST_PATH_BUDGET_FACTOR`) | `test_fast_path_costs_about_what_the_interpreter_costs`, `test_fast_path_factor_matches_the_design_note` |

**Why latency is the number this note enforces.** R14-2 is a guard that was
correct, useful, and *switched off that afternoon*, because its signal cost
more to read than it paid. A gate wired into every commit has the same
failure mode with a shorter fuse: the second it is the reason a commit feels
slow, it comes out of `settings.json`, and every guard behind it leaves with
it. The budget is not here to make the gate fast. It is here to make the
gate's slowness a **test failure** instead of an uninstall.

**Provenance of these numbers** (5.1). Ceilings are *chosen*; the baseline
is *measured*, on this repo, on a 2026 laptop, three runs each.

A pre-code prototype — a stdin-reading Python parent that spawns
`interpolation_lint`, `swallow_lint` and `rounds --check` over `python/` and
`docs/rounds/` — cost **269, 272 and 284 ms** per gated commit, and **23–24
ms** per *non*-commit Bash call, of which ~20 ms is CPython startup and the
rest is JSON parsing and a substring test.

**Re-measured against the shipping hook**, over the fixture repository the
budget test builds (a real `git init`, this repo's `docs/rounds/` and
`DOCTRINE.md`, an empty `swallow_baseline.json`, one staged `.py` file — so
all three guards are applicable and green): 10 gated commits cost **1,722,
1,548 and 1,583 ms** — **155–172 ms each**, including four `git` calls and
three guard subprocesses per run. The fast path costs **28–29 ms** against
a bare `python3 -c pass` of **14–15 ms** on the same runs: **1.93x, 1.95x
and 2.09x**.

The prototype was **1.7x too high**, because it pointed both lints at the
whole `python/` tree while the shipping hook scopes `interpolation_lint` to
the staged files. Wrong in the forgiving direction this time, which is
luck, not method: a proxy that agrees with itself three times is still not
the thing ([mcp-server.md](mcp-server.md) kept its 5x error for the same
reason). Both readings stay here, and **the ceiling is set from the
shipping number.**

2,500 ms for 10 runs is ~1.5x the shipping baseline, and `ci_slack: 2.0`
makes the enforced ceiling 5,000 ms — ~3x, the convention in
[obsgate-depth.md](obsgate-depth.md) and [lint-scan.md](lint-scan.md). The
looseness is checked against the regression it is for rather than eyeballed:
`verify_guard` in the pre-commit path adds ~700 ms per run, which puts 10
runs at ~8,600 ms and **trips the gate**. A 3x-of-baseline ceiling (4,800,
doubled to 9,600) would not have. The tripwire was placed by asking what it
has to catch, not by scaling the baseline out of habit.

The wall-clock ceiling is a tripwire, not a fit. The regression it exists to
catch is not drift of a few milliseconds — it is **a slow guard moving into
the fast path**. `verify_guard` alone costs 688–778 ms per call by the
measurements in [mcp-server.md](mcp-server.md), and a test suite costs
seconds; either one in the pre-commit path lands 10 gate runs one to two
orders of magnitude past this ceiling. A tripwire that far from the wire
does not need to be tight, and a tight one on a machine-dependent number
would flake on a shared runner, which is its own way of getting a gate
switched off.

The memory ceiling measures the **parent's** Python heap with
`tracemalloc`, so it sees the hook's own accumulation and nothing the guard
subprocesses allocate. It is a tripwire for the one bug it can see: a hook
that retains every guard's captured output. Stated plainly because a
16 MB figure otherwise reads as a claim about the whole gate, which it is
not.

The fast path is budgeted as a **ratio**, not a duration: the hook must add
no more than `3.0x` a bare `python3 -c pass` measured in the same test run.
An absolute millisecond figure for a path dominated by interpreter startup
measures the machine, not the change. The ratio does not: it goes red when
the hook starts doing work — a `git` call, a directory walk, an import —
before it has established that the command is even a commit.

**Bounded output.** Guard output is capped at 8,192 bytes per stream before
it becomes a `permissionDecisionReason`, and truncation is stated in the
text (`[truncated: N of M bytes]`). Two reasons, one of them documented:
the docs cap hook output strings at 10,000 characters and replace anything
longer with a preview plus a file path — an uncapped denial reason would be
silently rewritten into something the agent cannot read. The other is 2.6:
a denial reason goes straight into the model's context.

**The MCP server's two token budgets** live in
[mcp-server.md](mcp-server.md), which is where that mechanism is designed,
and they are named here because they are the same 2.6 argument in the same
session: the serialised `tools/list` payload is capped at **8,192 bytes**
(`TOOLS_LIST_MAX_BYTES`, measured at 20,718 before round 16 and 7,270
after, enforced over the real transport by
`test_tool_schemas_fit_a_token_budget`), and captured output is capped at
**8,192 bytes per stream** (`MAX_OUTPUT_BYTES`, enforced by
`test_output_cap_truncates_and_says_so`). Neither is in this note's
`sutradhar_budget` frontmatter: that block declares exactly one budget id
per note with the dimensions `n` / `rps` / `p95_ms` / `memory_mb`, this note
already declares `precommit-gate`, and there is no byte dimension to declare
a schema ceiling in. Rather than bend the frontmatter, both numbers are
declared in mcp-server.md's cardinalities table with their enforcing test
named, and each is pinned to its constant by a mirror test so the note and
the code cannot drift apart.

## Failure story <!-- 1.4 -->

| Dependency | Down | Slow | Partial |
|---|---|---|---|
| the guard CLI file | missing / unreadable -> `[sutradhar-hooks] instrument failure`, path named, **allow** | n/a | present but exits outside its partition -> instrument failure, the exit code quoted, explicitly not attributed to the code |
| the guard subprocess | `OSError` on spawn -> instrument failure, exception type printed, allow | exceeds the per-guard timeout -> killed, reported as timed out, **allow**; never "passed" | killed by a signal -> instrument failure; a signal is not a verdict |
| the guard's findings | exits red -> **deny**, with the guard's own text | a slow-but-finishing guard is charged to the budget above | output over the cap -> denial reason carries the truncation marker |
| `git` | not installed, or cwd is not a repo -> instrument failure, allow; the gate never claims a clean tree it could not read | `git diff --cached` hangs -> per-call timeout, the staged-paths scope degrades to "could not determine", stated in the message, allow | index and working tree disagree -> the message names the paths and says which tree was measured (B-15) |
| the hook's own code | any exception -> caught at top level, `instrument failure: <Type>`, exit 0, **nothing denied**; mutation-verified via `SUTRADHAR_HOOK_SELFTEST=raise` | the harness cancels the hook at its configured `timeout` -> the tool call proceeds (the docs treat a cancelled hook as non-blocking) | malformed / empty stdin -> instrument failure, allow; a hook that cannot read its payload knows nothing about the commit |
| `verify_guard` (Stop) | absent or repo-less -> the guard's own INCONCLUSIVE, reported as inconclusive | exceeds the Stop timeout -> reported INCONCLUSIVE with the timeout named, stop proceeds | dirty tree / merge commit -> INCONCLUSIVE, the verifier's honest tri-state, never a pass |
| the harness itself | `stop_hook_active` true -> exit 0 immediately, no work, no continuation loop | n/a | the 8-continuation cap is the harness's, not ours; we never reach it because DECORATION blocks at most once per HEAD |

The two rows that earn the table are the hook's own code and `git`. A crash
in our argument handling must not be able to file a bug against the user's
commit, and a `git` we could not run must not be able to imply a tree we
did not read.

## Illegal states <!-- 1.2 -->

- **There is no code path from a guard subprocess to a `deny` that does not
  pass through the exit-code partition.** A single function converts
  (exit code, stdout, stderr) into one of `GREEN` / `RED` / `SKIPPED` /
  `INSTRUMENT`, and only `RED` can deny. An unknown code cannot fall
  through to `GREEN`, because the partition is a lookup with an explicit
  `INSTRUMENT` default rather than an `if red: ... else: green`.
- **The allow-with-message path cannot be reached by a JSON parse of the
  hook's own output.** The hook writes exactly one JSON object to stdout
  and nothing else, because the docs are explicit that anything else on
  stdout (a stray print, a shell profile banner) makes the whole output
  parse as plain text and the decision silently vanish.
- **Every command is an `argv` list.** No `shell=True`, anywhere, on either
  hook. A repo path containing a semicolon is a path.
- `--update-baseline` is never passed to `swallow_lint`, for the reason
  [mcp-server.md](mcp-server.md) gives: a gate that can raise its own floor
  is a rubber stamp.
- The hook never writes to the repo, the index, or any settings file. It
  reads and reports. A gate with side effects is a merge conflict waiting
  for a bad afternoon.

## What the plugin bundles, and how

`plugin/` is **additive**: nothing in it changes a guard, a CLI, an exit
code, or the copy-in contract.

| Component | Copied or referenced | Why |
|---|---|---|
| the two hooks | **copied** (they are new files, and they live here) | `plugin/scripts/*.py`, stdlib only, no imports from the package — a hook that fails to import is a hook that failed, and `sys.path` inside a session is not ours to assume |
| the eight guard programs the plugin runs, `mcp_server.py` among them | **copied** — `plugin/guards/`, refreshed by `plugin/sync_guards.py` from one explicit list | R16-1. Round 15 referenced them through `${CLAUDE_PLUGIN_ROOT}/../python/sutradhar_guards` to keep one server and one version, and that was a plugin which worked only in the layout it was built in: an installed plugin is copied into `~/.claude/plugins/cache` **without** the files around it. The round-15 argument is answered rather than dropped - `test_plugin_bundle.py` fails on a one-byte divergence, derives the set of scripts the plugin invokes from the hooks' AST and the MCP tool table, and refuses a file in the bundle that no list pins |
| `agent/skills/*.md` | **referenced** — `plugin/skills/<name>/SKILL.md` carries the frontmatter Claude Code requires and a body that reads the canonical file | the canonical files have no frontmatter (they are handed to any agent, verbatim, by any harness) and adding it would be a Claude-Code-shaped change to a harness-neutral asset. A ratchet asserts one wrapper per canonical skill, so a skill added later cannot be silently un-shipped |
| `agent/packs/*` | **neither** — documented, not installed | the packs are paste-in text for `CLAUDE.md` and a Cursor rules file. A plugin cannot append to `CLAUDE.md`, and a plugin that *silently* injected 15 KB of rules into every session would be doing the thing this note is most careful not to do |

**No plugin config may contain `${CLAUDE_PLUGIN_ROOT}/..`**, and a ratchet
over every JSON file under `plugin/` enforces it. That path resolves
perfectly from a checkout and is simply absent after an install, with no
error at install time to say so — which is why R16-1 survived a full round
of testing. The skill wrappers still reach for `agent/skills/*.md` through
`../`, and that is a deliberately different case: a missing skill BODY
degrades to a wrapper that says the canonical file is not here, while a
missing guard program is a hook that cannot measure anything.

`guard_dir()` resolves in one order, and says both paths when it fails:

    SUTRADHAR_GUARD_DIR  ->  <plugin root>/guards  ->  instrument failure

Installed, the second one is always there. From a checkout,
`claude --plugin-dir ./plugin` uses the same bundle, so the layout under
test and the layout in use are the same layout — which is the actual lesson
of R16-1, and a stronger property than any test written inside one of
them.

## What deliberately did NOT change

- **The CI path.** `.github/workflows/selftest.yml` and `ci/guards.yml` are
  untouched. CI remains the gate that cannot be skipped; this is a faster
  copy of a subset of it, and if the two ever disagree CI is right.
- **The copy-in contract.** No guard learned about hooks. No guard imports
  anything new. `framework_only.py` still passes over the whole tree,
  including `plugin/`, and the plugin adds no dependency manifest.
- **Nobody's `settings.json`.** This repo's own `.claude/settings.json` is
  not modified by this change and is not tracked by it. Installing a
  blocking hook into a running session without the maintainer typing the
  command is precisely the failure this design is built to avoid, and doing
  it *while shipping the design* would be a fine joke and a bad commit.
- **The `Guard-cmd:` convention.** Read, not redefined. `ci/guards.yml`
  already greps it; the Stop hook greps the same trailer the same way.

## Ruled out, with reasons <!-- 7.4 -->

- **Blocking on INCONCLUSIVE.** Tempting: 2.9 says a check that could not
  run has not passed. But the common causes — dirty tree, merge commit, no
  git — are conditions the agent cannot fix by working longer, and a `Stop`
  block that cannot be satisfied is a loop the harness has to break. It is
  reported by name, loudly, and it never reads as a pass. Blocking is what
  a *rule* would do; naming it is what an *honest* instrument does.
- **Running the full test suite in the pre-commit hook.** It is the guard
  that would catch the most, and it is 19 s on this repo. See R14-2.
- **A `SessionStart` hook that injects `agent/packs/CLAUDE-snippet.md`.**
  It would make the doctrine genuinely non-optional, and it would spend
  every session's context on it without asking. If it ships it ships as an
  opt-in, with a measured token cost, in its own note.
- ~~**A marketplace (`.claude-plugin/marketplace.json`) for a one-command
  persistent install.**~~ **Reversed in round 16.** The reason given was
  that distribution is a separate decision with its own surface, and
  `--plugin-dir` is documented and deliberately per-session. What that
  reasoning missed is that the two are not independent: not shipping a
  marketplace also meant never exercising an *installed* layout, and
  `${CLAUDE_PLUGIN_ROOT}/../python` was broken the whole time (R16-1). The
  manifest is now at the repository root, the install is
  `/plugin marketplace add sutradharhq/sutradhar` then
  `/plugin install sutradhar@sutradhar`, and `--plugin-dir ./plugin` still
  works from a checkout against the same bundle. Nothing here writes to
  anyone's `settings.json`.
- **Stashing or checking out the index to gate the exact committed tree.**
  Correct, and destructive in a hook that must never lose someone's work.
  The gate names the tree it read instead (B-15).

## Guards shipping with this

All in `python/tests/test_agent_loop_hooks.py`, all driving the hooks as
real subprocesses over real repositories (2.3), all mutation-verified in
[round 15](../rounds/round-015.md).

- [x] `test_precommit_gate_holds_its_declared_envelope` (enforces n, p95_ms, memory_mb)
- [x] `test_fast_path_costs_about_what_the_interpreter_costs`
- [x] `test_fast_path_factor_matches_the_design_note` (pins this note to the constant)
- [x] `test_red_guard_denies_with_the_guards_own_output`
- [x] `test_green_guards_allow_and_name_what_ran`
- [x] `test_inapplicable_guard_allows_and_says_which_one`
- [x] `test_measuring_nothing_is_not_reported_as_green`
- [x] `test_a_crashing_hook_allows_with_an_instrument_message` (both hooks)
- [x] `test_a_missing_guard_directory_is_an_instrument_failure` (both hooks)
- [x] `test_an_unknown_exit_code_never_becomes_a_pass`
- [x] `test_a_red_guard_still_denies_when_another_guard_broke`
- [x] `test_gate_names_the_tree_it_measured` (B-15)
- [x] `test_a_quoted_git_commit_is_not_a_commit`, `test_a_commit_inside_a_chain_is_still_a_commit`
- [x] `test_stop_hook_blocks_on_decoration`
- [x] `test_stop_hook_reports_inconclusive_as_inconclusive`
- [x] `test_stop_hook_respects_stop_hook_active`
- [x] `test_stop_hook_reports_a_head_once_per_session`
- [x] `test_stop_hook_reminds_when_prod_and_test_move_without_a_trailer`
- [x] `test_every_canonical_skill_has_a_plugin_wrapper` (class ratchet)
- [x] `test_hooks_json_matches_the_documented_schema` (class ratchet: every event name against the documented set)
- [x] `test_no_hook_script_can_shell_out_or_exit_2` (class ratchet over the AST of every hook script)
- [x] `test_stop_hook_will_not_run_someone_elses_trailer` (R16-2; the planted trailer writes a sentinel file, and the assertion is that the file does not exist)
- [x] `test_stop_hook_will_not_run_a_trailer_when_the_repo_has_no_identity`, `test_stop_hook_runs_the_trailer_when_the_commit_is_yours` (the pair: a check that refused everything would pass the first and switch the hook off)
- [x] `test_the_hooks_find_their_guards_when_the_checkout_is_not_there` (R16-1 for the hooks: `plugin/` copied somewhere with nothing around it, the gate driven there, and the assertion is the DENY - a gate that cannot find its guards allows, so "nothing crashed" is what the broken version looks like too)
- [x] `test_plugin_bundle.py` (R16-1: byte-identity per bundled guard, coverage derived from the hooks' AST and the MCP tool table, no unpinned file in the bundle, no `${CLAUDE_PLUGIN_ROOT}/..` in any plugin config, the marketplace `source` resolving to a real plugin, and the bundled MCP server driven over stdio from a temp cwd with `python/` off `sys.path`)
- [x] `test_each_hook_has_a_selfcheck_that_could_fail` (6.7, in pairs)
- [x] `--selfcheck` on both hooks: the commit classifier, the `-a` widening,
      the exit-code partitions, the trailer reader, the production/test
      split, and the marker key
