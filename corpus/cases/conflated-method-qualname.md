---
case: conflated-method-qualname
guard: conflated_degrade_lint
rule: 2.7
scar: R18-2
expected: caught
---

The same conflation inside a class method, so the finding keys on the
qualified name (`Reader.latest_totals`) rather than a line number. The
handler logs and still returns the same `[]` the "nothing cached" path
returns; the clean twin returns a status-carrying value on failure, so
the two no longer share a spelling.

## defective

```python path=app/units.py
class Reader:
    def latest_totals(self, store, device_id):
        cached = store.cached(device_id)
        if cached is None:
            return []
        try:
            return store.fetch(device_id)
        except Exception as exc:
            store.log(exc)
            return []
```

## clean

```python path=app/units.py
class Reader:
    def latest_totals(self, store, device_id):
        cached = store.cached(device_id)
        if cached is None:
            return []
        try:
            return store.fetch(device_id)
        except Exception as exc:
            store.log(exc)
            return {"ok": False}
```
