---
case: obsgate-zero-rows
guard: obsgate
rule: 6.6
scar: R3-1
expected: caught
---

A jobs surface the floor requires with no series behind it. A claim about
a running system is verified against the surface that carries the
consequence (R3-1): the floor demands request and job series, the
defective metrics carry requests but no job series at all, so the gate
reports UNWITNESSED instead of letting a silent zero read as healthy. The
clean twin exports the job series, so every declared surface has live
series behind it and the gate stays silent.

## defective

```text path=metrics.txt
# HELP http_requests_total requests by route template
# TYPE http_requests_total counter
http_requests_total{route="/api/users/:id",method="GET"} 9042
http_requests_total{route="/api/orders",method="POST"} 112
```

```json path=floor.json
{"surfaces": [{"name": "requests", "pattern": "^http_requests_total$", "min_series": 1}, {"name": "jobs", "pattern": "^jobs_(fired|succeeded|failed)_total$", "min_series": 3}]}
```

## clean

```text path=metrics.txt
# HELP http_requests_total requests by route template
# TYPE http_requests_total counter
http_requests_total{route="/api/users/:id",method="GET"} 9042
http_requests_total{route="/api/orders",method="POST"} 112
# TYPE jobs_fired_total counter
jobs_fired_total 40
jobs_succeeded_total 38
jobs_failed_total 2
```

```json path=floor.json
{"surfaces": [{"name": "requests", "pattern": "^http_requests_total$", "min_series": 1}, {"name": "jobs", "pattern": "^jobs_(fired|succeeded|failed)_total$", "min_series": 3}]}
```
