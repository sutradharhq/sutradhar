---
case: budget-rps-unenforced
guard: budget
rule: 1.1
scar: R1-8
expected: caught
---

A design note declaring a scale and rate envelope no test holds. A number
written down and never enforced is decoration (R1-8): the note declares
the flow-budget id with a row count and a rate, and the defective twin
ships a test file that never quotes the id, so the build fails. The clean
twin quotes the id in a comment, visibly, so the gate passes. The note's
own frontmatter id stays unquoted, so it cannot self-enforce.

## defective

```markdown path=design/note.md
---
sutradhar_budget: flow-budget
n: 200000
n_unit: devices
rps: 500
---

# Flow budget note
```

```python path=tests/test_flow.py
def test_flow_runs():
    assert fetch([]) == []
```

## clean

```markdown path=design/note.md
---
sutradhar_budget: flow-budget
n: 200000
n_unit: devices
rps: 500
---

# Flow budget note
```

```python path=tests/test_flow.py
def test_flow_runs():
    # enforces "flow-budget" at the declared rate
    assert fetch([]) == []
```
