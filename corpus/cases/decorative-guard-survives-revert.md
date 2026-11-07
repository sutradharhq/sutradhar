---
case: decorative-guard-survives-revert
guard: verify_guard
rule: 2.2
scar: R4-1
fixture: two_commit
expected: caught
---

A guard that sets up the arithmetic by hand and asserts on its own
local math: it re-implements the fix instead of calling the seam, so it
passes whether the fix is present or not. Revert the production half
and it stays green - tested and half dead, the founding shape of 2.2
(the tenant-isolation fix that shipped that way for a week predates the
round records; R4-1 is the recorded member of the family, a check that
proved only the interpreter started). The registry owns the bug, the
fix, the git history, and the guard command; the manifest authors only
the guard under test.

## defective

```python path=tests/check.py
import sys
subtotal = 100 * 10
subtotal *= 0.9
sys.exit(0 if abs(subtotal - 900.0) < 1e-9 else 1)
```

## clean

```python path=tests/check.py
import os
import sys
sys.path.insert(0, os.getcwd())
import calc
sys.exit(0 if abs(calc.total(100, 10) - 900.0) < 1e-9 else 1)
```
