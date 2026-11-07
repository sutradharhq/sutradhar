---
case: golden-frozen-from-own-output
guard: golden
rule: 2.5
scar: B-5
expected: caught
---

A golden file is a regression pin, not an oracle: frozen from the
engine's own output it locks every current defect in as truth (B-5).
The guard cannot see provenance - that half is prose - but it sees
drift: the defective twin's computed values moved past the frozen
baseline beyond tolerance, and the gate fails instead of quietly
following. The clean twin stays inside tolerance. Re-baselining is a
deliberate act with a stated reason, never an accident. The frozen
baseline is manifest data in the helper fence below.

```json path=golden.json
{"tolerance_rel": 0.001, "reason": "initial baseline", "data": {"throughput": 980.0, "errors": 12.0}}
```

## defective

```json path=data.json
{"throughput": 1040.0, "errors": 12.0}
```

## clean

```json path=data.json
{"throughput": 980.0, "errors": 12.0}
```
