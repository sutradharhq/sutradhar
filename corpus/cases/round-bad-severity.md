---
case: round-bad-severity
guard: rounds
rule: 8.1
scar: R14-4
expected: caught
---

Same strictness family as R14-4 (see the duplicate-id twin in this
corpus): the parser refuses a row it cannot read exactly instead of
skipping it. Here the unreadable cell is severity `critical`, which is
not one of high, med, or low, so the defective twin is refused. The clean
twin carries `low` and passes.

## defective

```markdown path=rounds/round-009.md
# Round 9 - 2026-01-01

Lenses: synthetic

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R9-1 | critical | 8.1 | synthetic | fixed | severity outside the allowed set |
```

## clean

```markdown path=rounds/round-009.md
# Round 9 - 2026-01-01

Lenses: synthetic

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R9-1 | low | 8.1 | synthetic | fixed | placeholder row |
```
