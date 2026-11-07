---
case: sql-fstring-interpolation
guard: interpolation_lint
rule: 2.8
scar: R16-5
expected: caught
---

A value interpolated into a quoted query position. Safe today only if
the caller never passes anything with a quote in it - the pattern
becomes the hole the moment someone parameterises it, which is why the
guard flags the shape rather than the value. R16-5 records the same
hole in its older spellings; this case pins the f-string half the
register item says was caught from the first day.

## defective

```python path=app/units.py
def by_device(device_id):
    return f'SELECT * FROM units WHERE device = "{device_id}"'
```

## clean

```python path=app/units.py
def by_device(device_id):
    return f'SELECT * FROM units WHERE device = "{escape_literal(device_id)}"'
```
