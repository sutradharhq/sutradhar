---
case: design-note-citing-no-scar
guard: rounds
rule: 8.1
scar: R14-8
options: designs
expected: caught
---

Every design note names the incident that paid for it, or the gate
refuses it (R14-8: one note cited nothing, and nothing would have
refused a note that cited nothing). The defective twin cites R99-9,
which no round record contains; the clean twin cites the R9-9 the twin
round record carries.

## defective

```markdown path=rounds/round-009.md
# Round 9 - 2026-01-01

Lenses: synthetic

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R9-9 | low | 2.7 | synthetic | fixed | placeholder row |
```

```markdown path=design/note.md
---
sutradhar_scar: R99-9
---

# Design note: synthetic
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

```markdown path=design/note.md
---
sutradhar_scar: R9-9
---

# Design note: synthetic
```
