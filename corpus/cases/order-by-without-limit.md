---
case: order-by-without-limit
guard: detectors
rule: 2.6
scar: distribution
scar_argument: no numbered finding records the ORDER BY incident; the detector exists for the doctrine 2.6 memory-bomb class and this case pins its behavior, authored from the rule prose.
expected: caught
---

ORDER BY on an unbounded result set sorts the whole set in the store.
The defective twin sorts with no bound; the clean twin carries LIMIT in
the same fragment. Neither twin uses a relative import, so the union
contract holds: each twin exercises exactly one finder.

## defective

```python path=app/units.py
def history():
    return "SELECT device, ms FROM units ORDER BY ms"
```

## clean

```python path=app/units.py
def history():
    return "SELECT device, ms FROM units ORDER BY ms LIMIT 100"
```
