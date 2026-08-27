# Operations playbook

What code reading cannot find, and how to find it on purpose. The record
this distills: the un-restorable backup, the root-owned data directory, the
architecture-dependent build, and the half-dead-in-production fix were ALL
invisible to review and each fell out of the first drill or runtime check
that touched it.

## Drills, on a schedule

The four drills and their full protocol live in
[agent/skills/ops-drill.md](../agent/skills/ops-drill.md). The short form:

| Drill | Cadence | Non-negotiable |
|---|---|---|
| Cold-start install from docs alone | Before first deploy, then per release | Every stumble is a doc-fix commit the same day |
| Backup restore + reconciliation | Monthly, and before any real data | Counts diffed against source; "backup exists" proves nothing |
| Unattended soak | Before first unattended operation | Gaps in observation reported as gaps, never assumed continuous |
| Upgrade in place | Per upgrade path you claim to support | On a stack carrying data, gates green after |

## Exit-code discipline

The cheapest rule with the highest save rate:

- Never pipe a build or test through anything that swallows `$?`.
  `make build | tail -20` reports the tail of a FAILED build with tail's
  exit code. Capture `EXIT=$?` explicitly, print it, act on it.
- A truncated run reports as truncated. Exit 137 is a killed process; a
  killed test run shows its last green line and looks like a short pass.
  Compare counts against the expected total every time.
- Watch for flag interactions that eat your signal: a config-level `-q`
  plus a command-line `-q` can suppress the very summary line you are
  parsing.
- Measure, never eyeball: row counts, exit codes, RSS, computed layout. If
  the verification is "it looks fine", it is not verification.

## Verify the null

Before filing any finding, prove the test itself is valid:

- `docker kill` suppresses `restart: always` by design; a "container did
  not restart" finding from it is a bug in the drill, not the stack. Crash
  PID 1 inside the container instead.
- A test that fails for an environmental reason (missing mount, wrong env
  var) produces findings about your harness, not the system. Prove
  pre-existing vs regression by running the same check at the baseline
  commit.
- A false finding costs more trust than no finding, because the next real
  one gets discounted.

## Observability floor (doctrine 6.6)

Before anything runs unattended, four surfaces have metrics: requests
(count + latency by route template, not raw path - cardinality), jobs
(fired, succeeded, failed), ingest/throughput chokepoints, and dependency
up/down gauges. The gauge probes must not block the serving path.
A metrics endpoint that cannot load its client library degrades to an
honest comment block, never an empty 200 a scraper reads as "all zero".

This floor is a **provenance gate**, and it is mechanised: `obsgate.py`
takes the floor as a JSON manifest and a metrics payload (file or endpoint)
and answers WITNESSED / UNWITNESSED / FROZEN / INCONCLUSIVE. Wire it into CI
against a staging endpoint, or into a deploy gate against production:

    python obsgate.py --metrics https://svc/metrics --floor obs_floor.json

The line it draws: a task that changes a running system is done when its
effect is witnessable at one of these surfaces, and a claim about a running
system that no surface witnessed does not leave the building (5.1). An
empty payload FAILS - "no data" and "all zero" must never read the same -
and an unreachable endpoint is INCONCLUSIVE, never a pass, because a dead
endpoint witnesses nothing.

A 200 is not evidence either. An exporter that caches, or whose collection
loop has wedged, serves stale truth behind a healthy status line, and that
reads exactly like a live surface. Scrape it more than once:

    python obsgate.py check --metrics https://svc/metrics --floor f.json \
                            --samples 3 --interval-ms 500

Byte-identical payloads across every sample, on a surface whose floor
declares counters that ought to move, is **FROZEN** (exit 4) - its own word,
not UNWITNESSED, because the metrics are all present and the fix is not "add
metrics". A surface with no must-move counter is never accused: a false
finding costs more trust than no finding (6.4).

Every refusal names **which of three parties failed** - `instrument:`
(obsgate itself: bad flag, parser raised), `endpoint:` (unreachable, empty,
frozen), or `floor:` (the surface is fine, the declaration is not met).
*The scar: a polling loop printed ten "no response" lines about an API that
was serving 200s in 0.27s, because a bug in the poller raised and a shell
fallback spoke on the server's behalf.* An instrument that cannot say whose
failure it is always blames the system.

## Witnessing effects, not just surfaces (doctrine 6.6)

The floor answers "does the surface exist". It does not answer the harder
half of 6.6 - *a change to a running system is done only when its effect can
be witnessed at a runtime surface* - and until you can compute that, it is a
sentence people nod at. Snapshot the surface before and after, and declare
what the change should have done:

    python obsgate.py snapshot --metrics https://svc/metrics --out before.json
    # ...deploy, run the job, hit the new route...
    python obsgate.py snapshot --metrics https://svc/metrics --out after.json
    python obsgate.py effects --before before.json --after after.json \
                              --floor obs_floor.json

A snapshot is a deterministic digest - per family: type, series count,
sorted label keys, value sum, and a sha256 over the sorted series - so two
snapshots of an unchanged surface are identical apart from `captured_at`.
The `effects` section of the floor manifest declares what to look for, and
`obs_floor.json` in `docs/templates/` ships a documented example of all four
kinds: `increased`, `appeared`, `no_vanished_series`, `stable_labels`.

Exit 0 when every effect is witnessed, 1 when any is not, 2 when the command
cannot answer. Three properties are worth knowing before you wire it in:

- **A miss states its direction.** `expected-increase-but-fell`,
  `expected-appear-but-absent`, `expected-increase-but-family-VANISHED`. A
  verdict's word is part of its correctness (2.4 + 5.1); nobody re-derives a
  figure that arrived with a confident label.
- **A counter that fell is `COUNTER_RESET`, not a generic failure.** Same
  arithmetic, opposite diagnosis: the process restarted, and the effect you
  asked about may well have happened where this surface can no longer see
  it. Sending someone to debug a feature over a restart wastes the day.
- **Nothing passes vacuously.** No `effects` section, an empty before
  snapshot, or a question about a label whose value set exceeded the
  snapshot's cardinality cap each REFUSE - `UNANSWERABLE`, never a pass.
  A gate that certifies an unstated change is worse than no gate.

Design note, with the budgets and the deliberate non-goals:
[docs/design/obsgate-depth.md](design/obsgate-depth.md).

## Shared-host hygiene

- Scrub selectively; never global-prune volumes on a machine that runs
  anything else. Verify the neighbors survived.
- Services with restart policies come back after a `stop` issued hours
  ago. Re-check what is actually running before attributing resource
  pressure.
- Two test runs sharing one backend poison each other's verdicts. If a
  failure looks impossible, check for a concurrent run before debugging.
