---
case: swallow-bare-except-pass
guard: swallow_lint
rule: 2.7
scar: R18-2
expected: caught
---

A bare `except:` with nothing but `pass` in the body: the handler names
no failure mode, logs nothing, degrades to nothing explicitly, and
re-raises nothing. A failed fetch becomes silence, and the caller reads
the silence as success. The loud half of 2.7, which R18-2 records
`swallow_lint` as catching.

## defective

```python path=app/units.py
def latest_total(store):
    try:
        return store.fetch()
    except:
        pass
```

## clean

```python path=app/units.py
def latest_total(store):
    return store.fetch()
```
