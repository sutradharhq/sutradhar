---
case: skip-gate-nothing-sets
guard: envgate
rule: 3.7
scar: R2-2
expected: caught
---

A test tier gated on an environment variable no automation file sets, so
the tests behind it run in no environment while the suite counts them.
The audit R2-2 almost fooled is textual on purpose; this case is the
shape it exists to catch, from the other side - a gate the tree sets
nowhere. The clean twin sets the variable in the workflow, visibly.
The gate list is manifest data in the helper fence below.

```json path=gates.json
[{"marker": "full_stack", "env_var": "FULL_STACK", "reason": "runs the slow tier"}]
```

## defective

```yaml path=.github/workflows/ci.yml
name: ci
on: [push]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: python -m pytest tests/ -q
```

## clean

```yaml path=.github/workflows/ci.yml
name: ci
on: [push]
env:
  FULL_STACK: "1"
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: python -m pytest tests/ -q
```
