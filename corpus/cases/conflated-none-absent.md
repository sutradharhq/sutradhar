---
case: conflated-none-absent
guard: conflated_degrade_lint
rule: 2.7
scar: R18-2
expected: caught
---

The handler DOES log, and still returns the same `None` the legitimate
"nothing cached" path returns. The log line exists, the caller still
cannot tell an outage from an empty result, and every total computed
downstream is computed over an unknown fraction of reality under a
green status. The quiet half of 2.7, which R18-2 records `swallow_lint`
as structurally blind to. The clean twin carries a status beside the
value, so failure and absence no longer share a spelling.

## defective

```python path=app/units.py
def latest_total(store, device_id):
    cached = store.cached(device_id)
    if cached is None:
        return None
    try:
        return store.fetch(device_id)
    except Exception as exc:
        store.log(exc)
        return None
```

## clean

```python path=app/units.py
def latest_total(store, device_id):
    cached = store.cached(device_id)
    if cached is None:
        return None, True
    try:
        return store.fetch(device_id), True
    except Exception as exc:
        store.log(exc)
        return None, False
```
