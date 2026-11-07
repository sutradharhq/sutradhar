---
case: round-record-malformed-row
guard: rounds
rule: 8.1
scar: R14-4
expected: caught
---

A findings row with five cells where six are required. R14-4 records
the twin in the backflow parser: a row the parser could not read
vanished while the gate printed OK. The rounds parser refuses the row
instead of skipping it. The clean twin is the same record well-formed.

## defective

```markdown path=rounds/round-009.md
# Round 9 - 2026-01-01

Lenses: synthetic

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R9-9 | low | 2.7 | synthetic |
```

## clean

```markdown path=rounds/round-009.md
# Round 9 - 2026-01-01

Lenses: synthetic

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R9-9 | low | 2.7 | synthetic | fixed | placeholder row |
```
