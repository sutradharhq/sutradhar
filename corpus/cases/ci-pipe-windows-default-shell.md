---
case: ci-pipe-windows-default-shell
guard: ci_step_lint
rule: 6.3
scar: R23-10
expected: caught
---

The same pipe means two different things depending on the runner. A step
with no `shell:` key runs under `bash -e` on a linux runner, where a pipe
reports its last command's status and a failed build reads as success.
On a windows runner the default shell is pwsh, whose exit-code model is
different, and the remedy a bash-minded check prints (`set -o pipefail`)
breaks the step outright (R23-10). The twins differ only in `runs-on`:
the defective twin is the linux job, the clean twin is the windows job.
The clean twin is the point of this case - a sweep over it pins the false
positive shut. Both twins name a reachable script, so only the pipe check
decides the verdict.

```python path=scripts/ok.py
print("reachable")
```

## defective

```yaml path=workflows/ci.yml
name: ci
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: python scripts/ok.py src/ | tee build.log
```

## clean

```yaml path=workflows/ci.yml
name: ci
on: [push]
jobs:
  build:
    runs-on: windows-latest
    steps:
      - run: python scripts/ok.py src/ | tee build.log
```
