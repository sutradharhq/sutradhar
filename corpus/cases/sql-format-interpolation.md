---
case: sql-format-interpolation
guard: interpolation_lint
rule: 2.8
scar: B-20
expected: caught
---

The same hole in the third spelling: `.format()` into a quoted query
position (B-20). The clean twin interpolates into an unquoted LIMIT
position with a numeric-typed name - not injectable, and not flagged.

## defective

```python path=app/units.py
def by_device(device_id):
    return "SELECT * FROM units WHERE device = '{}'".format(device_id)
```

## clean

```python path=app/units.py
def one_page(page_limit):
    return "SELECT * FROM units LIMIT {}".format(page_limit)
```
