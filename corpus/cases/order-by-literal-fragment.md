---
case: order-by-literal-fragment
guard: detectors
rule: 2.6
scar: distribution
scar_argument: no numbered finding records the ORDER BY incident; the detector exists for the doctrine 2.6 unbounded-sort class and this case pins its f-string fragment half, authored from the rule prose.
expected: caught
---

ORDER BY inside a query fragment sorts the whole result set in the
store. The defective twin carries no bound; the clean twin carries
LIMIT in the same fragment. Both twins use a literal device value, so
no interpolation shape is present for any other guard to trip on -
a clean twin must be clean under every guard, not just its own.
Neither twin uses a relative import, so the detectors union contract
holds: each twin exercises exactly one finder.

## defective

```python path=app/units.py
def history():
    return "SELECT device, ms FROM units WHERE device = 'abc' ORDER BY ms"
```

## clean

```python path=app/units.py
def history():
    return "SELECT device, ms FROM units WHERE device = 'abc' ORDER BY ms LIMIT 100"
```
