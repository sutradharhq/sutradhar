---
case: ci-step-working-directory
guard: ci_step_lint
rule: 6.7
scar: R18-3
expected: caught
---

A step that names its own working directory resolves every script path
under it (R18-3). The defective twin runs `python scripts/ok.py` from
`sub`, where no such file sits, so the interpreter would halt on
file-not-found: a claim about a process, and none at all about the code
under test. The clean twin ships `sub/scripts/ok.py`, so the same step
resolves. Reachability, not correctness: a script that exists can still
be wrong, but one that cannot be found cannot be either.

## defective

```yaml path=workflows/ci.yml
name: ci
on: [push]
jobs:
  guards:
    runs-on: ubuntu-latest
    steps:
      - name: run the guard
        working-directory: sub
        run: python scripts/ok.py
```

## clean

```yaml path=workflows/ci.yml
name: ci
on: [push]
jobs:
  guards:
    runs-on: ubuntu-latest
    steps:
      - name: run the guard
        working-directory: sub
        run: python scripts/ok.py
```

```python path=sub/scripts/ok.py
print("reachable")
```
