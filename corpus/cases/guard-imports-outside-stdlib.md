---
case: guard-imports-outside-stdlib
guard: framework_only
rule: "-"
scar: distribution
scar_argument: the framework/product line is a repo-specific promise with no numbered incident behind this exact check; the case pins the import gate on a planted third-party import.
expected: caught
---

A guard reaching outside the standard library is the moment the
framework starts becoming a product. The defective twin imports a
third-party client; the clean twin parses with stdlib only. The gate
makes the drift a visible diff instead of a quiet one.

## defective

```python path=guards/check.py
import requests


def fetch(url):
    return requests.get(url, timeout=5)
```

## clean

```python path=guards/check.py
import json


def load(text):
    return json.loads(text)
```
