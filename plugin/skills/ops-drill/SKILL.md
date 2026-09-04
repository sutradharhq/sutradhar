---
description: Run an operations drill - cold-start install, backup/restore reconciliation, unattended soak, or upgrade-in-place - to find the defects code review structurally cannot see. Use when asked to drill, rehearse a restore, verify a runbook, or check operational readiness.
---

# Ops drill

The procedure is kept in one canonical file so that every harness reads the
same text. Read it now, in full, and follow it:

    ${CLAUDE_PLUGIN_ROOT}/../agent/skills/ops-drill.md

If that file is not there, this plugin was loaded from outside a Sutradhar
checkout. Say so rather than improvising - a drill without its command-
verifiable gates is a demo, and a demo is what the drill exists to replace.
The file lives at `agent/skills/ops-drill.md` in
<https://github.com/sutradharhq/sutradhar>.

A drill's findings belong in a round record (`docs/rounds/`), validated by
`rounds.py`, like any other finding.
