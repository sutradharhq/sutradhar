---
case: backflow-item-past-its-round
guard: rounds
rule: 8.1
scar: R21-8
options: backflow
expected: caught
---

Recording an owed item costs nothing, so it sits. The register makes an
unmoved item cost something: past its by-round it fails the gate, and
the only ways out are decisions (R21-8 decided nineteen items in one
round). The defective twin owes B-27 since round 5 with round 9
recorded; the clean twin adopted it with a rule attached.

## defective

```markdown path=rounds/round-009.md
# Round 9 - 2026-01-01

Lenses: synthetic

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R9-9 | low | 2.7 | synthetic | fixed | placeholder row |
```

```markdown path=backflow.md
## The register

| id | source | what | evidence | rule | status | by-round | note |
|---|---|---|---|---|---|---|---|
| B-27 | synthetic | an item nobody decided | scar | 8.1 | owed | 5 | still owed past round 9 |
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

```markdown path=backflow.md
## The register

| id | source | what | evidence | rule | status | by-round | note |
|---|---|---|---|---|---|---|---|
| B-27 | synthetic | an item nobody decided | scar | 8.1 | adopted | 5 | decided in round 9 |
```
