---
case: ci-step-job-defaults
guard: ci_step_lint
rule: 6.7
scar: R18-3
expected: caught
---

The job-level variant of the working-directory defect: `defaults.run`
sets the directory for every step in the job that does not opt out
(R18-3). The defective twin runs `python scripts/ok.py` under the job
default `sub`, where no such file sits, so the interpreter would halt on
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
    defaults:
      run:
        working-directory: sub
    steps:
      - name: run the guard
        run: python scripts/ok.py
```

## clean

```yaml path=workflows/ci.yml
name: ci
on: [push]
jobs:
  guards:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: sub
    steps:
      - name: run the guard
        run: python scripts/ok.py
```

```python path=sub/scripts/ok.py
print("reachable")
```
