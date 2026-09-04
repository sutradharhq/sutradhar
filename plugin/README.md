# The Claude Code plugin

Everything else in this repository is **available** to an agent. This
directory is the half that makes it **non-optional** for one session: two
hooks that Claude Code fires from its own loop, whether or not the agent
remembers the guards exist.

| Component | What it does |
|---|---|
| `hooks/hooks.json` -> `scripts/precommit_gate.py` | On `PreToolUse` for a Bash `git commit`: runs the fast guards and **denies the commit** with the guard's own output when one is red |
| `hooks/hooks.json` -> `scripts/verify_before_done.py` | On `Stop`: if HEAD carries a `Guard-cmd:` trailer, asks `verify_guard` whether that guard is real. DECORATION blocks the turn from ending; INCONCLUSIVE is reported as inconclusive and never as a pass |
| `.mcp.json` | Registers `guards/mcp_server.py` so the nine guards are callable as tools mid-task |
| `guards/` | The guard programs the hooks and the MCP server run |
| `skills/` | Wrappers for the two canonical skills in `agent/skills/` |

## Install

You need `python3` on your PATH. That is the whole list.

Two commands, typed into Claude Code:

```
/plugin marketplace add sutradharhq/sutradhar
/plugin install sutradhar@sutradhar
```

The first one tells Claude Code where to look; the second installs the
plugin from there. The same two from your terminal, if you prefer:

```bash
claude plugin marketplace add sutradharhq/sutradhar
claude plugin install sutradhar@sutradhar
```

You do not have to edit a settings file, and nothing here writes to one.

**To try it for one session instead**, from a checkout of this repository:

```bash
claude --plugin-dir ./plugin
```

That loads the plugin for that session only and leaves nothing behind -
a reasonable way to meet a tool that can deny a commit.

**Before you install it**, run the two hooks' selfchecks. Each one has a
case it is supposed to fail, so a zero here means something:

```bash
python3 plugin/scripts/precommit_gate.py --selfcheck
python3 plugin/scripts/verify_before_done.py --selfcheck
claude plugin validate .              # the harness's own schema check
```

Run `claude plugin validate .` from the repository root: it reads the
marketplace manifest at `.claude-plugin/marketplace.json` and the plugin
it points at.

**If `python3` is missing**, the hooks report an *instrument failure* and
allow. They say so by name, and they do not block anything - a guard
harness that can wedge a session is not a harness. You get the message,
your commit goes through, and nothing claims your code was checked.

**The guards under `plugin/guards/` are copies.** An installed plugin is
copied without the files around it, so the plugin carries the programs it
runs rather than reaching back into a checkout for them. The copies are
pinned to `python/sutradhar_guards/` by a test that fails on a one-byte
difference, and `python3 plugin/sync_guards.py` is what refreshes them.

## What it will and will not do

- **It never blocks because it broke.** A missing guard, a spawn failure, a
  timeout, an exit code outside the guard's documented partition, or a bug
  in the hook itself is reported as an *instrument* failure - naming the
  hook as the failing party - and the tool call proceeds. A guard harness
  that can wedge a session is not a harness.
- **It never reports a guard that did not run as green.** No
  `swallow_baseline.json`, no `docs/rounds/`, no staged Python: each is
  named as skipped. A commit where nothing was applicable says so out loud.
- **It says which tree it read.** The guards read the working tree; `git
  commit` commits the index. When they differ, the message names the paths
  where they disagree. The gate never stashes, checks out, or writes
  anything in your repository.
- **It is quiet.** The `Stop` hook says nothing on a turn with nothing to
  report, and reports a given HEAD at most once per session.

- **It will not run a `Guard-cmd:` trailer somebody else wrote.** The
  `Stop` hook runs a trailer only when HEAD's author email matches your
  `git config user.email`. Checking out a pull request is otherwise enough
  to let its author choose a command that runs on your machine. When the
  author is somebody else, the hook says whose commit it is and prints the
  one-line command to run it yourself.

## Pointing it at guards you copied in

The plugin uses its own `guards/` directory. To point it somewhere else -
you keep the guards in `scripts/`, or you are testing a change to them:

```bash
export SUTRADHAR_GUARD_DIR=/path/to/your/scripts
```

`SUTRADHAR_SWALLOW_BASELINE` overrides the baseline lookup the same way.

## Design

`docs/design/agent-loop-hooks.md` - the event names, payload shapes and
blocking mechanisms this was built against (with the doc URLs and the date
they were read), the latency budget and what it is a tripwire for, the
failure story, and what deliberately did not change.
