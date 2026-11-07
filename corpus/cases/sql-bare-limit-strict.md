---
case: sql-bare-limit-strict
guard: interpolation_lint
rule: 2.8
scar: R16-5
expected: caught
options: strict
---

A value interpolated into a bare LIMIT position. Outside strict mode
the guard leaves unquoted positions alone, so this shape is flaggable
only under `strict` - and the manifest says so. The clean twin wraps
the value in an escaping call at the site, which is silent in either
mode.

## defective

```python path=app/units.py
def one_page(n):
    return "SELECT * FROM units LIMIT {}".format(n)
```

## clean

```python path=app/units.py
def by_device(device_id):
    return "SELECT * FROM units WHERE device = '{}'".format(escape_literal(device_id))
```
