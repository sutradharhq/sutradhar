---
case: verify-guard-collision-warning
guard: verify_guard
rule: 3.7
scar: R21-15
fixture: two_commit
expected: open
---

The guard command `python tests/test_calc.py` contains `calc.py`, the
production file under test, as a bare substring - and the collision
warning fires on every such command while the verdict stays VERIFIED.
A warning, never a verdict (R21-15). Both twins call the seam and both
verify, so this case scores MISSED twice: open, measured, waiting on
the day the warning graduates into something a gate can hold. The
defect lives in the file NAME, so the twins differ only by path, and
the registry owns everything else about the fixture.

## defective

```python path=tests/test_calc.py
import os
import sys
sys.path.insert(0, os.getcwd())
import calc
sys.exit(0 if abs(calc.total(100, 10) - 900.0) < 1e-9 else 1)
```

## clean

```python path=tests/check.py
import os
import sys
sys.path.insert(0, os.getcwd())
import calc
sys.exit(0 if abs(calc.total(100, 10) - 900.0) < 1e-9 else 1)
```
