---
case: helper-with-test-and-no-caller
guard: detectors
rule: 8.2
scar: distribution
scar_argument: no numbered finding records a helper-with-a-test incident in this repository; the sentence entered 8.2 from the standing doctrine, and this case pins the alibi shape - a private helper whose only caller is its own test - authored from the rule prose, never from guard output.
expected: caught
---

Doctrine 8.2: a test is not a caller, and dead code with a test has an
alibi. The helper's arithmetic was inlined into the one production
caller during a refactor; the helper stayed behind because its test
kept passing, and every later reader assumes something still needs it.
The clean twin is the same pair of files with the production caller
still calling the helper. Both twins stay clean of the sibling
detectors: absolute imports only, no query strings.

## defective

```python path=app/units.py
def rollup(samples):
    return sum(s.value for s in samples) / max(len(samples), 1)


def _interval_mean(samples):
    return sum(s.value for s in samples) / max(len(samples), 1)
```

```python path=tests/test_units.py
from app import units


def test_interval_mean_of_empty_is_zero():
    assert units._interval_mean([]) == 0
```

## clean

```python path=app/units.py
def rollup(samples):
    return _interval_mean(samples)


def _interval_mean(samples):
    return sum(s.value for s in samples) / max(len(samples), 1)
```

```python path=tests/test_units.py
from app import units


def test_interval_mean_of_empty_is_zero():
    assert units._interval_mean([]) == 0
```
