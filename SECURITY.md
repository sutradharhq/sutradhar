# Security

## The short version

Sutradhar is **copy-in and dependency-free**. There is no package to install,
no runtime, and no service. The Python guards import the standard library only;
the browser probe and Cypress guards are zero-dependency too. This is enforced,
not just claimed — `python/sutradhar_guards/framework_only.py` fails the build
if any shipped guard reaches outside the standard library or if a dependency
manifest appears in the framework surface.

The practical consequence for your supply chain: **there is nothing here to
compromise on your behalf.** No transitive dependencies, no post-install
scripts, no network calls, no telemetry. You can read every line that will run
in your CI in a single sitting, and you should — the whole point of copy-in is
that the code lives in your tree, under your review, pinned to the tag you took.

One exception, stated in full below: the Claude Code plugin can run *your*
commands, and you should read that section before installing it.

## Reporting a vulnerability

If you find a security issue in a guard, the probe, or the example app, please
report it privately rather than opening a public issue:

- Preferred: open a **GitHub private security advisory** on this repository
  (Security → Report a vulnerability).
- Include: the file and version (tag or commit) you took, what the guard does
  versus what it should do, and a minimal reproduction if you have one.

Because the toolkit runs inside your own CI over your own code, the realistic
threat is a guard that **passes when it should fail** — a check that is
decoration. That is the exact defect class this framework exists to catch, so
we treat "this guard cannot actually fail" as a security-grade report, not a
cosmetic one, and every guard ships with a `--selfcheck` and mutation-verified
tests precisely to keep that from happening. If you can show a guard passing a
known-bad input, that is a finding we want.

## What the Claude Code plugin can do to your machine

The paragraph above is true of the guards. The plugin under `plugin/` adds
two things that *execute*, and you should know exactly what they are before
you install it. We found both doors open in our own audit (round 16,
findings R16-2 and R16-3) and closed them in the same commit that added this
section.

**1. `verify_guard` runs the command you give it, as you.** Its job is to run
*your* test command twice — once with the fix, once with the fix reverted —
and check that the test actually goes red. That means it is a test runner,
not a linter. Through the MCP server, the command string comes from the
agent. Treat the tool accordingly:

- It is **not run through a shell.** The command is split into one program
  and its arguments. The only compound form accepted is a leading
  `cd <dir> &&`, and `<dir>` must resolve inside the throwaway worktree.
  Pipes, `;`, `&&` elsewhere, redirects, backticks and any `$` are refused
  with a message that says so (a `$` is refused outright rather than passed
  through as a literal, which would silently run a different check). Anything more complex belongs in a script
  that you name.
- It runs in a **throwaway git worktree**, so it cannot dirty your checkout.
  A worktree is not a sandbox: it is your user, your `$HOME`, your
  environment variables and your network.
- **Do not allowlist it** in Claude Code's permissions. Let it prompt. A
  developer who allowlists `verify_guard` thinking "it runs my tests" has
  allowlisted arbitrary execution by the agent.
- The `repo` argument is confined to the git repository the server was
  started in. `SUTRADHAR_MCP_ANY_REPO=1` lifts that, deliberately, by you.

**2. The `Stop` hook runs the `Guard-cmd:` trailer on HEAD.** When your
agent's turn ends, the hook reads HEAD's commit message and, if it carries a
`Guard-cmd:` trailer, runs that command through `verify_guard` to check the
guard is real. Before this section existed, whoever authored HEAD chose a
command that ran on your laptop: check out a pull request, pull upstream,
merge a contributor, end the session. Now:

- The hook runs a trailer **only when HEAD's author email is your git
  `user.email`.** A trailer on someone else's commit is reported, not run,
  with the one-line command to run it yourself if you choose to.
- The same no-shell parser applies, so the trailer is a program and its
  arguments, never a pipeline.

**What neither one can do.** The hooks never touch your working tree or
your index: no stash, no checkout, no reset. The one write is
`git worktree add`, which registers a throwaway worktree under
`.git/worktrees/` for the duration of a `verify_guard` run and removes it
after. The "already reported" marker lives in your system temp directory,
never in the repository. They never block because they broke;
a crash in the hook is reported as *our* failure and the tool call proceeds.
Nothing is written to any settings file — the plugin is enabled per session,
by you, and disabled by not enabling it. There is still no network code
anywhere in the plugin or the guards.

If you want the enforcement without the execution surface at all: the
pre-commit gate needs only the three fast lints, none of which run your
commands. Delete `verify_guard` from the bundle and the `Stop` hook from
`hooks/hooks.json`, and what remains is read-only.

## Scope

In scope: the guards under `python/sutradhar_guards/`, the Claude Code
plugin under `plugin/` (hooks, bundled guards, MCP server), the probe under
`js/probe/`, the Cypress guards under `js/cypress/`, the bootstrap script, and
the worked example. Out of scope: your own code, your CI configuration, and any
dependency you add on top of the copy-in files (which is now your supply chain,
not ours).

## Response

This is a small, maintainer-run project. We aim to acknowledge a report within
a few days and to fix a confirmed decoration-class or code-execution issue in
the next tagged release, with the fix shipping — per our own doctrine — beside
a guard that proves the defect fails loudly from then on.
