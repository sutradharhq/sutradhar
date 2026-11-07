---
case: import-from-subpackage-init
guard: detectors
rule: 2.3
scar: R18-1
expected: caught
---

A relative import from a subpackage `__init__` naming a member the
subpackage never defines: the importing route fails while a
helper-level check beside it passes (2.3). R18-1 records the key
discipline this detector keeps. Neither twin sorts anything unbounded,
so the union contract holds.

## defective

```python path=app/__init__.py
"""Device units package."""
```

```python path=app/pkg/__init__.py
def present_name():
    return "here"
```

```python path=app/units.py
from .pkg import missing_name


def latest_total(store):
    return store.fetch()
```

## clean

```python path=app/__init__.py
"""Device units package."""
```

```python path=app/pkg/__init__.py
def present_name():
    return "here"
```

```python path=app/units.py
from .pkg import present_name


def latest_total(store):
    return store.fetch()
```
