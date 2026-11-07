---
case: claim-grouped-thousands
guard: claim_check
rule: 4.1
scar: distribution
scar_argument: no numbered finding records the grouped-thousands invention shape; this case pins the grounding behavior the guard mechanises, authored from the rule prose rather than from guard output.
expected: caught
---

A generated summary that phrases a witnessed throughput figure alongside
an invented peak shaped with grouped thousands. The model phrases
witnessed values and never invents (4.1): throughput at 980 units is
witnessed, while the peak at 1,240 units appears from nowhere. The clean
twin phrases only what was witnessed. The witnessed set is manifest data
in the helper fence below - the adapter reads it, no guard output
authored it.

```json path=witnessed.json
[{"value": 980, "unit": "units"}]
```

## defective

```text path=summary.md
Throughput holds at 980 units with a peak at 1,240 units.
```

## clean

```text path=summary.md
Throughput holds at 980 units.
```
