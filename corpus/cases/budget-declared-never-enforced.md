---
case: budget-declared-never-enforced
guard: budget
rule: 1.1
scar: R1-8
expected: caught
---

A design note promising 200,000 devices inside 800 ms, with no test
holding it to that. A budget written down and never enforced reads as a
commitment and behaves like a wish (R22-4 re-states R1-8 from the corpus
side; R1-8 is the incident). The defective twin's test file never quotes
the id; the clean twin quotes it, visibly. The note's own frontmatter id
is unquoted, so it cannot self-enforce.

## defective

```markdown path=design/note.md
---
sutradhar_budget: fleet-sweep
n: 200000
n_unit: devices
p95_ms: 800
memory_mb: 512
---

# Design note: the fleet sweep
```

```python path=tests/test_fleet.py
def test_sweep_runs():
    assert sweep([]) == []
```

## clean

```markdown path=design/note.md
---
sutradhar_budget: fleet-sweep
n: 200000
n_unit: devices
p95_ms: 800
memory_mb: 512
---

# Design note: the fleet sweep
```

```python path=tests/test_fleet.py
def test_sweep_runs():
    # enforces "fleet-sweep" at the declared scale
    assert sweep([]) == []
```
