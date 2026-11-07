---
case: swallow-outage-as-data
guard: swallow_lint
rule: 2.7
scar: R18-2
expected: caught
---

An outage becomes "this device reported nothing", and the caller cannot
tell the difference from a device that truly reported nothing. The
handler logs nothing, degrades to nothing explicitly, and re-raises
nothing: the loud half of 2.7, which R18-2 records `swallow_lint` as
catching.

## defective

```python path=app/units.py
def latest_total(store):
    try:
        return store.fetch()
    except Exception:
        return {}
```

## clean

```python path=app/units.py
def latest_total(store):
    return store.fetch()
```
