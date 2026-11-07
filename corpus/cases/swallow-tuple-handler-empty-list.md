---
case: swallow-tuple-handler-empty-list
guard: swallow_lint
rule: 2.7
scar: R18-2
expected: caught
---

A tuple handler naming two failure modes, one of them broad, degrading
silently to an empty row set. The caller asked for rows and got none,
with no signal that the read failed rather than found nothing. The
loud half of 2.7, which R18-2 records `swallow_lint` as catching; the
clean twin returns a value the empty result never takes, so the two
stay distinguishable.

## defective

```python path=app/units.py
def latest_rows(store, device_id):
    try:
        return store.fetch(device_id)
    except (ValueError, Exception):
        return []
```

## clean

```python path=app/units.py
def latest_rows(store, device_id):
    try:
        return store.fetch(device_id)
    except (ValueError, Exception):
        return {"ok": False}
```
