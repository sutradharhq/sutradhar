---
case: golden-rebaseline-without-reason
guard: golden
rule: 2.5
scar: B-5
expected: caught
options: rebaseline
---

A re-baseline with the update mode on and no stated reason. Re-baselining
is deliberate: it carries the reason the numbers legitimately changed, in
the same act, or the golden file stops meaning anything (B-5). With
options rebaseline the adapter sets the update mode and reads reason.txt
when present. The defective twin drifts to new values with no reason file
anywhere, so the gate refuses. The clean twin carries the same drifted
values plus a reason.txt twin body holding one legitimate-change
sentence, so the reasoned re-baseline proceeds silently. The frozen
baseline is manifest data in the helper fence below; the reason differs
per twin, so it lives in the twin body, not in helpers.

```json path=golden.json
{"tolerance_rel": 0.001, "reason": "initial baseline", "data": {"throughput": 980.0}}
```

## defective

```json path=data.json
{"throughput": 1040.0}
```

## clean

```json path=data.json
{"throughput": 1040.0}
```

```text path=reason.txt
Throughput model re-tuned per review; the expected value moved.
```
