---
case: envgate-second-gate-unset
guard: envgate
rule: 3.7
scar: R2-2
expected: caught
---

A second test tier gated on a variable no automation file sets, while the
first tier is set. A skip gate nothing sets leaves its tests running in
no environment under a green suite (R2-2): the defective twin CI sets
only FULL_STACK, so the audit flags the missing PERF_TIER gate. The clean
twin sets both variables in the workflow, visibly, so the audit stays
silent. The gate list is manifest data in the helper fence below.

```json path=gates.json
[{"marker": "full_stack", "env_var": "FULL_STACK", "reason": "runs the full stack tier"}, {"marker": "perf_tier", "env_var": "PERF_TIER", "reason": "runs the load tier"}]
```

## defective

```yaml path=.github/workflows/ci.yml
name: ci
on: [push]
jobs:
  check:
    runs-on: ubuntu-latest
    env:
      FULL_STACK: "1"
    steps:
      - run: python -m pytest tests/ -q
```

## clean

```yaml path=.github/workflows/ci.yml
name: ci
on: [push]
jobs:
  check:
    runs-on: ubuntu-latest
    env:
      FULL_STACK: "1"
      PERF_TIER: "1"
    steps:
      - run: python -m pytest tests/ -q
```
