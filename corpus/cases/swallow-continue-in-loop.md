---
case: swallow-continue-in-loop
guard: swallow_lint
rule: 2.7
scar: R18-2
expected: caught
---

Per-device reads in a loop, each guarded by `except Exception:
continue`. One failed fetch skips one device with no log line, and the
returned row set silently covers fewer devices than asked for. The loud
half of 2.7, which R18-2 records `swallow_lint` as catching; the clean
twin logs and re-raises, which the guard reads as handled.

## defective

```python path=app/units.py
def collect_totals(store, devices):
    totals = []
    for device in devices:
        try:
            totals.append(store.fetch(device))
        except Exception:
            continue
    return totals
```

## clean

```python path=app/units.py
def collect_totals(store, devices):
    totals = []
    for device in devices:
        try:
            totals.append(store.fetch(device))
        except Exception as exc:
            store.log(exc)
            raise
    return totals
```
