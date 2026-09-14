---
description: Run an operations drill - cold-start install, backup/restore reconciliation, unattended soak, or upgrade-in-place - to find the defects code review structurally cannot see. Use when asked to drill, rehearse a restore, verify a runbook, or check operational readiness.
---

# Ops drill

The procedure is kept in one canonical file so that every harness reads the
same text. Read it now, in full, and follow it:

    ${CLAUDE_PLUGIN_ROOT}/skills/ops-drill/ops-drill.md

That file is a byte-identical copy of `agent/skills/ops-drill.md` in
<https://github.com/sutradharhq/sutradhar>, kept in step by
`plugin/sync_guards.py`. If it is not there, this copy of the plugin is
incomplete. Say so rather than improvising - a drill without its command-
verifiable gates is a demo, and a demo is what the drill exists to replace.

A drill's findings belong in a round record (`docs/rounds/`), validated by
`rounds.py`, like any other finding.
