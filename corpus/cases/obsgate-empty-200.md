---
case: obsgate-empty-200
guard: obsgate
rule: 6.6
scar: R3-1
expected: caught
---

An endpoint answering with nothing behind a success status. An empty 200
reads as nothing, never zero (R3-1): the defective metrics carry no
series at all while the floor requires request and job series, so the
gate reports UNWITNESSED instead of letting every consumer read the
payload as all zero. The clean twin exports both series, so every
declared surface has live series behind it and the gate stays silent.

## defective

```text path=metrics.txt
# the exporter answered with no series
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
