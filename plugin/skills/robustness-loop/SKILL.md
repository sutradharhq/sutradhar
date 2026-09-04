---
description: Run one adversarial robustness round over a codebase - find defects by operating and asserting, fix each with a guard in the same commit, mutation-verify every guard, and write the round record. Use when asked to harden, audit, stress, or run a robustness round on a repo.
---

# Robustness loop

The procedure is kept in one canonical file so that every harness reads the
same text. Read it now, in full, and follow it:

    ${CLAUDE_PLUGIN_ROOT}/../agent/skills/robustness-loop.md

If that file is not there, this plugin was loaded from outside a Sutradhar
checkout. Say so rather than improvising the procedure from memory - the
value of the loop is in its specifics, and a half-remembered version of it
is a code review with a longer name. The file lives at
`agent/skills/robustness-loop.md` in <https://github.com/sutradharhq/sutradhar>.

The guards the loop calls for are available as MCP tools from the
`sutradhar-guards` server this plugin registers, and as CLIs under
`python/sutradhar_guards/`.
