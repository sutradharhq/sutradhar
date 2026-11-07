---
case: round-duplicate-id
guard: rounds
rule: 8.1
scar: R14-4
expected: caught
---

R14-4 records the row-strictness finding: a register parser that skipped
what it could not read stayed green over a lost item. The rounds side of
the same family refuses instead of skipping. Two rows carrying one
finding id in a single round record are rejected, since a repeated id
makes the trend a lie. The defective twin repeats `R9-1`; the clean twin
gives each row its own id.

## defective

```markdown path=rounds/round-009.md
# Round 9 - 2026-01-01

Lenses: synthetic

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R9-1 | low | 8.1 | synthetic | fixed | first record |
| R9-1 | low | 8.1 | synthetic | fixed | repeated record |
```

## clean

```markdown path=rounds/round-009.md
# Round 9 - 2026-01-01

Lenses: synthetic

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R9-1 | low | 8.1 | synthetic | fixed | first record |
| R9-2 | low | 8.1 | synthetic | fixed | second record |
```
