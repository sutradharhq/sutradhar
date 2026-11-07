---
case: budget-missing-tests-dir
guard: budget
rule: 1.1
scar: R1-8
expected: caught
---

A design note declaring a scale and rate envelope with no test root at
all. A missing test root leaves every declared number unenforced, which
is the same decoration R1-8 names: the defective twin carries only the
design note, so the build fails. The clean twin adds a test file quoting
the store-sweep id, visibly, so the gate passes. The note's
frontmatter id stays unquoted, so it cannot self-enforce.

## defective

```markdown path=design/note.md
---
sutradhar_budget: store-sweep
n: 200000
n_unit: rows
rps: 500
---

# Store sweep note
```

## clean

```markdown path=design/note.md
---
sutradhar_budget: store-sweep
n: 200000
n_unit: rows
rps: 500
---

# Store sweep note
```

```python path=tests/test_flow.py
def test_flow_runs():
    # enforces "store-sweep" at the declared rate
    assert fetch([]) == []
```
