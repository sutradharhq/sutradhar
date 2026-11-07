---
case: ci-pipe-case-pattern-and-regex
guard: ci_step_lint
rule: 6.3
scar: R24-7
expected: caught
---

A pipe check that reads every `|` as a pipeline flags ordinary CI shell
that holds none: the alternation bar of a `case` pattern list
(`push|pull_request) ...;;`) and the bar inside a `[[ ... =~ ... ]]` regex
(`^(main|release/.*)$`). The outside review of v0.6.0 found both flagged
with "pipes a command's exit code away" (R24-7), the kind of false positive
that gets a guard muted inside a week. The clean twin is the point of this
case: it carries both shapes, on one line and across lines, and a sweep
over it pins the false positive shut. The defective twin is the same step
with one real pipe in a case clause's command, which still swallows the
build's exit code.

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
      - run: |
          case "$GITHUB_EVENT_NAME" in a|b) echo ab;; esac
          case "$GITHUB_EVENT_NAME" in
            push|pull_request) python scripts/ok.py src/ | tail -5 ;;
            *) exit 1 ;;
          esac
          if [[ "$GITHUB_REF" =~ ^refs/heads/(main|release/.*)$ ]]; then python scripts/ok.py src/; fi
```

## clean

```yaml path=workflows/ci.yml
name: ci
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: |
          case "$GITHUB_EVENT_NAME" in a|b) echo ab;; esac
          case "$GITHUB_EVENT_NAME" in
            push|pull_request) python scripts/ok.py src/ ;;
            *) exit 1 ;;
          esac
          if [[ "$GITHUB_REF" =~ ^refs/heads/(main|release/.*)$ ]]; then python scripts/ok.py src/; fi
```
