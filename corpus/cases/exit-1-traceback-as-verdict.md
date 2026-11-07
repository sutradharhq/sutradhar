---
case: exit-1-traceback-as-verdict
guard: swallow_lint
rule: 6.11
scar: R21-18
expected: open
---

A guard that crashes exits 1 like a guard that found something, and a
caller mapping exit codes to verdicts reads the traceback as a report
(R21-18: through the adapter, a crash came back a red verdict with the
traceback attached, `isError: false`). No registry guard measures the
caller mapping - the defect lives in the adapter layer, not in any CLI
shape this scorer runs. These twins are placeholders on purpose: clean
code, silent under every guard, scoring MISSED so the case stays open
and measured instead of greenwashing a gap. The day a crash-aware check
exists, THESE twins get replaced by twins that crash it; until then the
gap is named here rather than silently absent.

## defective

```python path=app/units.py
def latest_total(store):
    return store.fetch()
```

## clean

```python path=app/units.py
def latest_count(store):
    return len(store.fetch())
```
