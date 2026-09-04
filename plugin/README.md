# The Claude Code plugin

Everything else in this repository is **available** to an agent. This
directory is the half that makes it **non-optional** for one session: two
hooks that Claude Code fires from its own loop, whether or not the agent
remembers the guards exist.

| Component | What it does |
|---|---|
| `hooks/hooks.json` -> `scripts/precommit_gate.py` | On `PreToolUse` for a Bash `git commit`: runs the fast guards and **denies the commit** with the guard's own output when one is red |
| `hooks/hooks.json` -> `scripts/verify_before_done.py` | On `Stop`: if HEAD carries a `Guard-cmd:` trailer, asks `verify_guard` whether that guard is real. DECORATION blocks the turn from ending; INCONCLUSIVE is reported as inconclusive and never as a pass |
| `.mcp.json` | Registers the existing `python/sutradhar_guards/mcp_server.py` so the nine guards are callable as tools mid-task |
| `skills/` | Wrappers for the two canonical skills in `agent/skills/` |

## Install

The plugin is a view onto the checkout it lives in, so run this from the
repository root:

```bash
claude --plugin-dir ./plugin
```

That is the documented way to load a local plugin, and it is deliberately
per-session: a hook that can deny a commit should be something you turn on
on purpose. Nothing here writes to your `settings.json`.

Before you install it, run both hooks' selfchecks - each has a case it is
supposed to fail, so a zero here means something:

```bash
python3 plugin/scripts/precommit_gate.py --selfcheck
python3 plugin/scripts/verify_before_done.py --selfcheck
claude plugin validate ./plugin      # the harness's own schema check
```

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

## Pointing it at guards you copied in

If you copied the guards to `scripts/` rather than running from a checkout:

```bash
export SUTRADHAR_GUARD_DIR=/path/to/your/scripts
```

`SUTRADHAR_SWALLOW_BASELINE` overrides the baseline lookup the same way.

## Design

`docs/design/agent-loop-hooks.md` - the event names, payload shapes and
blocking mechanisms this was built against (with the doc URLs and the date
they were read), the latency budget and what it is a tripwire for, the
failure story, and what deliberately did not change.
