---
case: swallow-conflated-degrade
guard: conflated_degrade_lint
rule: 2.7
scar: R18-2
expected: caught
---

The handler DOES log, and still returns the same falsy value the
legitimate "nothing cached" path returns. The log line exists, the
caller still cannot tell an outage from an empty result, and every total
computed downstream is computed over an unknown fraction of reality
under a green status. The quiet half of 2.7, which R18-2 records
`swallow_lint` as structurally blind to - and which this guard exists to
see. The fix is not "raise instead": the fail-safe value is usually
right, and the silence is the defect. Make the two distinguishable.

## defective

```python path=app/units.py
def latest_total(store, device_id):
    cached = store.cached(device_id)
    if cached is None:
        return {}
    try:
        return store.fetch(device_id)
    except Exception:
        store.log("fetch failed")
        return {}
```

## clean

```python path=app/units.py
def latest_total(store, device_id):
    cached = store.cached(device_id)
    if cached is None:
        return {}
    try:
        return store.fetch(device_id)
    except Exception:
        store.log("fetch failed")
        return {"ok": False}
```
