# Multi-agent playbook

Running many agent sessions (or agents plus humans) on one codebase without
them destroying each other's work. Every rule here was earned by an actual
collision.

## Git isolation

**One worktree per agent.** This is not advice, it is a hard rule, and
explicit staging is NOT a sufficient substitute: on a shared worktree, one
session's perfectly explicit `git add CLAUDE.md` captured a second
session's UNSTAGED mid-edits to the same file into its own commit, and a
branch switch moved HEAD out from under the other session's running work.
`git worktree add ../proj-agent2 <base>` costs seconds.

**Stage only named files. Never `git add -A`.** Twice, a `-A` swept another
workstream's untracked WIP (marketing collateral, build output, scratch
scripts) into an unrelated commit. Also beware toolchains that write into
bind-mounted paths: a `docker cp` into a container whose directory is a
bind mount writes into the working tree. `git status --porcelain` after
staging, before committing, every time.

## Orientation protocol

Before starting any workstream:

1. Read the owning plan or tracker.
2. **Spot-check its claims against the tree** (the named files, tests, and
   seams exist or do not). Two minutes of grep.
3. Check recent commits touching the area.

Two workstreams on our record were started fresh after parallel sessions
had already completed them. The doc said pending; the tree said done; the
sessions that skipped step 2 paid full price.

The reciprocal duty: when YOU finish something, update the owning doc the
same day. "Trust the tree, not the doc" is a survival rule, not an excuse
to let the doc rot further.

## Shared-backend serialization

Worktrees isolate git, not the database. Two test runs against one slow
shared service produce phantom failures and incomparable counts in both.
Serialize test runs that share a backend, or give each agent its own
compose project. The parallelism you lose is worth less than the
invalidated verdicts you avoid.

## Knowledge transfer between sessions

- **Record what you ruled out**, with the reason, where the next session
  will look (the plan doc, a residual register, a memory file). Un-recorded
  dead ends get re-explored at full price.
- **Keep a residual register**: the round-over-round backlog of known
  deferrals, each with a reason. It only shrinks or gets more honest; it
  never silently grows.
- **Harness knowledge is transferable capital.** Env vars that gate side
  effects, mounts that ratchet tests need, suites that must run in their
  own process: write them down the first time. Re-learning a harness fact
  costs an hour every time it is not recorded.

## Waits and polling

Bounded waits only. Prefer a synchronous command with a generous timeout
over an until-loop. If you must background work, one completion check, not
a poll ladder: when a wait loop's producer dies, the loop spins forever.
