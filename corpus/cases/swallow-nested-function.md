---
case: swallow-nested-function
guard: swallow_lint
rule: 2.7
scar: R18-2
expected: caught
---

A silent swallow one def deep: the inner handler catches broadly and
degrades to an empty value with no log line, so only a walk that reads
nested defs can see it. The loud half of 2.7, which R18-2 records
`swallow_lint` as catching; the clean twin keeps the same nesting and
degrades explicitly.

## defective

```python path=app/units.py
def collector(store):
    def latest_total():
        try:
            return store.fetch()
        except Exception:
            return {}
    return latest_total
```

## clean

```python path=app/units.py
def collector(store):
    def latest_total():
        try:
            return store.fetch()
        except Exception as exc:
            store.log(exc)
            return {}
    return latest_total
```
