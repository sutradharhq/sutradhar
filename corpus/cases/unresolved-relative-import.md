---
case: unresolved-relative-import
guard: detectors
rule: 2.3
scar: R18-1
expected: caught
---

A relative import the package cannot resolve: the target module exists
on disk but never defines the imported name, so the route that imports
it fails while the helper-level test beside it passes (2.3). R18-1
records the key discipline this detector keeps. Neither twin sorts
anything unbounded, so the union contract holds.

## defective

```python path=app/__init__.py
"""Device units package."""
```

```python path=app/helpers.py
def present_name():
    return "here"
```

```python path=app/units.py
from .helpers import missing_name


def latest_total(store):
    return store.fetch()
```

## clean

```python path=app/__init__.py
"""Device units package."""
```

```python path=app/helpers.py
def present_name():
    return "here"
```

```python path=app/units.py
from .helpers import present_name


def latest_total(store):
    return store.fetch()
```
