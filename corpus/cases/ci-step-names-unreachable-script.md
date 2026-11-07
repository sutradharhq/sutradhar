---
case: ci-step-names-unreachable-script
guard: ci_step_lint
rule: 6.7
scar: R18-3
expected: caught
---

A step whose interpreter exits 2 on file-not-found has made a claim
about a process and none at all about the code under test (R18-3). The
defective twin names a script the tree does not hold; the clean twin
names one it does. Reachability, not correctness: a script that exists
can still be wrong, but one that cannot be found cannot be either.

## defective

```yaml path=workflows/ci.yml
name: ci
on: [push]
jobs:
  guards:
    runs-on: ubuntu-latest
    steps:
      - run: python scripts/nosuch.py src/
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

```python path=scripts/ok.py
print("reachable")
```
