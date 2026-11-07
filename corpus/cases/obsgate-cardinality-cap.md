---
case: obsgate-cardinality-cap
guard: obsgate
rule: 6.6
scar: R3-1
expected: caught
---

A route label carrying more distinct values than the floor allows. Labels
must stay templates, never raw paths, and the cap is what keeps a metric
store from becoming a memory bomb (R3-1): the floor caps the route label
at 2 distinct values, the defective metrics carry 3, so the gate reports
UNWITNESSED. The clean twin stays within the cap, so the surface is
witnessed and the gate stays silent.

## defective

```text path=metrics.txt
# HELP http_requests_total requests by route template
# TYPE http_requests_total counter
http_requests_total{route="/api/users/:id",method="GET"} 9042
http_requests_total{route="/api/orders",method="POST"} 112
http_requests_total{route="/api/exports",method="GET"} 7
```

```json path=floor.json
{"surfaces": [{"name": "requests", "pattern": "^http_requests_total$", "min_series": 1, "max_label_cardinality": {"route": 2}}]}
```

## clean

```text path=metrics.txt
# HELP http_requests_total requests by route template
# TYPE http_requests_total counter
http_requests_total{route="/api/users/:id",method="GET"} 9042
http_requests_total{route="/api/orders",method="POST"} 112
```

```json path=floor.json
{"surfaces": [{"name": "requests", "pattern": "^http_requests_total$", "min_series": 1, "max_label_cardinality": {"route": 2}}]}
```
