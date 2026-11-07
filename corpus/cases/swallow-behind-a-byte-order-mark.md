---
case: swallow-behind-a-byte-order-mark
guard: swallow_lint
rule: 2.9
scar: R24-27
expected: caught
---

Three bytes at the top of a file - the UTF-8 byte-order mark, EF BB BF,
which Windows editors add on their own - made every source lint read the
file as clean. Python imports such a file without complaint, so the code
ran, and the lint, reading it as `utf-8`, handed the mark to the parser as
a character, got a SyntaxError, and returned the empty list a clean file
returns (R24-27). The swallow below was live and unjudged under a pass.

Both twins carry the mark: the first line of each fence begins with
U+FEFF, which renders as nothing. `test_corpus.py` asserts that the
materialized files really start with those three bytes, so the case
cannot lose its point to an editor that strips them. The clean twin is the
same file without the swallow, which pins the other half: a BOM-prefixed
file with nothing in it is judged clean, not refused.

## defective

```python path=app/reader.py
﻿def latest(store):
    try:
        return store.fetch()
    except Exception:
        pass
```

## clean

```python path=app/reader.py
﻿def latest(store):
    return store.fetch()
```
