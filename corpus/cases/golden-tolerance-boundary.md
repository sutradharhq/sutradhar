---
case: golden-tolerance-boundary
guard: golden
rule: 2.5
scar: B-5
expected: caught
---

A computed value drifting past the frozen baseline beyond its declared
tolerance. A golden file is a regression pin with a stated tolerance, not
an oracle that follows the code (B-5): throughput frozen at 980.0 with a
relative tolerance of 0.001 refuses 981.96, which sits about two parts in
a thousand out. The clean twin at 980.5 stays inside tolerance and stays
silent. The frozen baseline is manifest data in the helper fence below.

```json path=golden.json
{"tolerance_rel": 0.001, "reason": "initial baseline", "data": {"throughput": 980.0}}
```

## defective

```json path=data.json
{"throughput": 981.96}
```

## clean

```json path=data.json
{"throughput": 980.5}
```
