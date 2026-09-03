# Backflow register

Innovations your other repos, teams or forks invented, and what happened to
them here. Gated:

```bash
python scripts/rounds.py docs/rounds/ --backflow docs/backflow.md
```

An item past its **by-round** and still `owed` or `deferred` fails the gate.
Three ways out, all of them decisions: adopt it, reject it with a reason,
re-defer it to a later round with a reason. Nothing here can quietly wait —
which is the only reason a register like this is different from a wish list.

`evidence` is `scar` (an incident with a recorded cost) or `practice` (a
documented intention — a charter, an ADR, a protocol). A `practice` item may
strengthen the mechanism of a rule that already has a scar; it may not found a
new rule. That is doctrine 8.1, and the gate enforces it.

Notes cannot contain the `|` character — it splits the row.

## The register

| id | source | what | evidence | rule | status | by-round | note |
|---|---|---|---|---|---|---|---|
| B-1 | (which repo or team) | (the innovation, one line) | scar | 2.1 | owed | 3 | |
