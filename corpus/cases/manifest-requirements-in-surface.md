---
case: manifest-requirements-in-surface
guard: framework_only
rule: "-"
scar: distribution
scar_argument: the framework/product line is a repo-specific promise with no numbered incident behind this exact manifest check; the case pins the manifest gate on a planted requirements file beside a stdlib-only guard.
expected: caught
---

A dependency manifest in the framework surface means an install step,
which is the moment the toolkit stops being copy-in. The defective
twin pairs a stdlib-only guard with a requirements file naming a
third-party package; the clean twin carries the same guard and no
manifest.

## defective

```python path=guards/check.py
import json


def load(text):
    return json.loads(text)
```

``` path=requirements.txt
requests==2.30.0
```

## clean

```python path=guards/check.py
import json


def load(text):
    return json.loads(text)
```
