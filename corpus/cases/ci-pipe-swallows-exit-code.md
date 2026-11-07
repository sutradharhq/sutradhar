---
case: ci-pipe-swallows-exit-code
guard: ci_step_lint
rule: 6.3
scar: R22-3
expected: caught
---

A build piped through `tail` reports tail's exit code, and a failed
build reads as success. This case was seeded open in round 22 while 6.3
was convention-only (R22-3), and scored MISSED until round 23 gave the
guard a pipe check. The twins are unchanged since they were authored:
the defective step pipes its build through `tail` with no pipefail, the
clean step runs the same build unpiped. Both twins name only reachable
scripts, so the reachability half of the guard stays silent on both and
the verdict is the pipe check's alone. The reachable script is manifest
data in the helper fence below.

```python path=scripts/ok.py
print("reachable")
```

## defective

```yaml path=workflows/ci.yml
name: ci
on: [push]
jobs:
  guards:
    runs-on: ubuntu-latest
    steps:
      - run: python scripts/ok.py src/ | tail -5
```

## clean

```yaml path=workflows/ci.yml
name: ci
on: [push]
jobs:
  guards:
    runs-on: ubuntu-latest
    steps:
      - run: python scripts/ok.py src/
```
