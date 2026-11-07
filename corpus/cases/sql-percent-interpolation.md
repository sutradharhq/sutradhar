---
case: sql-percent-interpolation
guard: interpolation_lint
rule: 2.8
scar: B-20
expected: caught
---

The same hole in an older spelling: `%`-format into a quoted query
position. A detector that knew only f-strings looked like coverage of
the class and covered one dialect of it (B-20).

## defective

```python path=app/units.py
def by_device(device_id):
    return "SELECT * FROM units WHERE device = '%s'" % device_id
```

## clean

```python path=app/units.py
def by_device(device_id):
    return "SELECT * FROM units WHERE device = '%s'" % escape_literal(device_id)
```
