---
case: claim-units-mismatch
guard: claim_check
rule: 4.1
scar: distribution
scar_argument: no numbered finding records the right-value-wrong-unit invention shape; this case pins the same-unit grounding behavior the guard mechanises, authored from the rule prose rather than from guard output.
expected: caught
---

A generated summary that phrases a witnessed value under a unit that was
never witnessed. The model phrases witnessed values and never invents
(4.1): the value 980 was witnessed in units, so phrasing it as 980
devices is ungrounded even though the digits match. The clean twin keeps
the witnessed value with its witnessed unit. The witnessed set is
manifest data in the helper fence below - the adapter reads it, no guard
output authored it.

```json path=witnessed.json
[{"value": 980, "unit": "units"}]
```

## defective

```text path=summary.md
Throughput holds at 980 devices.
```

## clean

```text path=summary.md
Throughput holds at 980 units.
```
