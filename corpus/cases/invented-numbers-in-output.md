---
case: invented-numbers-in-output
guard: claim_check
rule: 4.1
scar: distribution
scar_argument: no numbered finding records the grounding rule for generated text; this case pins the grounding behavior the guard mechanises, authored from the rule prose rather than from guard output.
expected: caught
---

A generated summary whose numbers cannot be traced to witnessed values.
The model phrases; it never invents (4.1). Throughput at 980 units and
errors at 12 percent are witnessed; the peak at 1,240 units and the
headroom at 47 percent appear from nowhere. The clean twin phrases only
what was witnessed. The witnessed set is manifest data in the helper
fence below - the adapter reads it, no guard output authored it.

```json path=witnessed.json
[{"value": 980, "unit": "units"}, {"value": 12, "unit": "percent"}]
```

## defective

```text path=summary.md
Throughput holds at 980 units with errors down to 12 percent. Peak load
hit 1,240 units with headroom at 47 percent.
```

## clean

```text path=summary.md
Throughput holds at 980 units with errors down to 12 percent.
```
