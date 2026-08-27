---
sutradhar_budget: obsgate-snapshot
n: 10000
n_unit: series
p95_ms: 900
memory_mb: 24
ci_slack: 2.0
---

# Design note: obsgate goes deep

<!-- Written before the code, which is the only order in which 1.1 is worth
     anything. The numbers below were measured first and chosen second. -->

## What and why

`obsgate` checks a declared floor against **one** metrics payload. That
answers "does a surface exist", which is half of doctrine 6.6. The other
half - *"a change to a running system is done only when its effect can be
witnessed at a runtime surface"* - was still prose. Prose is what 6.6's own
scars are made of: a verification read a queryable proxy three times while
the surface a person actually saw disagreed throughout, and a review read
exit 0 from five selfchecks that did not exist.

Three moves, all depth on the same tool, no new tools:

1. **Snapshot** - a deterministic digest of the metrics surface at a moment.
   Without a before, "witnessed" cannot be computed, only asserted.
2. **Effects** - `before + after + declared effect` -> a verdict per effect.
   This is 6.6's sentence made into an exit code.
3. **Live-surface honesty** - a 200 is not evidence. An endpoint that serves
   byte-identical bytes across N scrapes is stale truth wearing a 200, and
   until now it read exactly like a healthy one.

## Cardinalities and budgets <!-- doctrine 1.1 -->

| Dimension | Design N | Enforced by |
|---|---|---|
| series in one snapshotted surface | 10,000 | `test_snapshot_holds_its_declared_envelope` |
| wall clock, snapshot x2 + effects diff | 900 ms (x2 CI slack) | same |
| peak Python heap for that pass | 24 MB (x2 CI slack) | same |
| distinct values retained per label key | 64 (`LABEL_VALUE_CAP`) | `test_label_values_are_capped_and_say_so` |

**Provenance of these numbers** (doctrine 5.1). The ceilings are *chosen*;
the baseline behind them is *measured*. On a 2026 laptop, a prototype of the
shipping hot path - parse a 10,000-series payload (100 families x 100
series, 0.57 MB of text), build both snapshots, diff them - ran in **296 ms
(296, 294, 296 across three runs) with a peak Python heap of 8.2 MB**, and
the resulting snapshot serialised to 0.05 MB of JSON. The wall-clock ceiling
is ~3x that baseline so a shared runner does not flake, matching the
convention in [lint-scan.md](lint-scan.md). The memory ceiling is ~3x and
deliberately loose, because its job is not a tight fit but a **tripwire for
unbounded accumulation**: the shape that breaks it is a change that retains
per-series state across families - keeping raw payload text per sample, or
lifting `LABEL_VALUE_CAP` - which is precisely the 2.6 regression a snapshot
tool invites, since "just record everything" is always the easiest patch.

10,000 is the design N because it is a large-but-real single-process
exporter. It is **not** a claim about a federated Prometheus; a 10-million
series query is a different tool's problem and this one will refuse to be
it (see non-goals).

`LABEL_VALUE_CAP` is the second number and the more interesting one: a
snapshot that stored every distinct label value would reintroduce, in the
snapshot file, exactly the unbounded-cardinality bomb the existing
`max_label_cardinality` check exists to catch. So values are retained only
up to the cap, and past it the snapshot records **that it stopped looking**.
An `appeared` effect aimed at a truncated key must then answer
`UNANSWERABLE`, never `NOT_WITNESSED` and never a pass - the snapshot does
not know, and a tool that guessed here would be fabricating with extra steps
(6.6).

## The three parties <!-- doctrine 2.4 + 6.4, and the R3-1 scar class -->

Every failure this tool emits names **whose** failure it is. This is not
cosmetic: the scar is a polling loop that printed ten "no response" lines
about a production API that was serving 200s in 0.27s, because a bug in the
poller's own formatting raised and the shell's `||` fallback spoke on the
server's behalf. An instrument whose error branch cannot tell "the system is
down" from "my parser crashed" reports the wrong outage with total
confidence, and it always reports it about the system.

| Party | Means | Example message |
|---|---|---|
| `instrument` | obsgate itself is broken or misused | `instrument: parser raised ValueError on line 41 - this is obsgate's failure, NOT evidence about the endpoint` |
| `endpoint` | the metrics surface failed | `endpoint: unreachable`, `endpoint: served 0 parseable series`, `endpoint: FROZEN` |
| `floor` | the surface is fine, the declaration is not met | `floor: surface 'jobs' has 0 series, floor requires 3` |

A bad flag is `instrument`. An unreachable URL is `endpoint`. A missing
metric is `floor`. Nothing is allowed to be unattributed.

## Verdict vocabulary, and why FROZEN is its own word <!-- doctrine 2.4 + 5.1 -->

`UNWITNESSED` already means "the payload was read and the floor is not met".
A frozen exporter is a different fact with a different fix: the floor *is*
met, every series is present, and the numbers are stale. Filing it as
`UNWITNESSED` would send the reader to add metrics that already exist.
2.4 and 5.1 together make a verdict's *word* is part of its correctness - a
number can be right while the name attached to it sends the reader the
opposite way - so frozen gets `FROZEN` and its own exit code (4).

Likewise, on the effects side: `expected-increase-but-fell` and
`COUNTER_RESET` are the same arithmetic and opposite diagnoses. A counter
that fell did not decline; the process restarted. The direction is in the
word.

## Failure story <!-- doctrine 1.4 -->

| Dependency | Down | Slow | Partial |
|---|---|---|---|
| metrics endpoint | `INCONCLUSIVE` (exit 3), party `endpoint`; never a pass | `--timeout` elapses -> same `INCONCLUSIVE`, timeout named in the message | payload parses but floor unmet -> `UNWITNESSED` (1), party `floor` |
| metrics endpoint, alive but stale | `FROZEN` (exit 4), party `endpoint`, only reachable with `--samples N` | N scrapes at `--interval-ms` each carry the full timeout | one differing byte across N samples -> not frozen; the check is deliberately conservative |
| snapshot files | unreadable/not JSON -> exit 2, party `instrument` (a caller passed a path that is not a snapshot) | n/a | snapshot written by a newer schema -> refused by version, exit 2, not silently half-read |
| the floor manifest | unreadable -> exit 2, party `instrument`; no `effects` section -> exit 2 with "there is nothing to check", **never a vacuous 0** | n/a | an effect naming a family absent from both snapshots -> `NOT_WITNESSED`, named as the deleted-instrument case |
| obsgate's own parser | any unexpected exception is caught, its **type printed**, and attributed to `instrument`; the run exits 2 | n/a | a line the parser cannot read is skipped (lenient by design), but a payload where **no** line parses is an `endpoint` failure, not silence |

The row that earns the note is the last one. A parser that dies must not be
able to file a bug against someone else's server.

## Illegal states <!-- doctrine 1.2 -->

- A snapshot carries `obsgate_snapshot: 1`. Anything else is refused at load
  rather than duck-typed - the field exists so that a future format change
  cannot be read as a wrong answer.
- `captured_at` is excluded from every digest by construction, not by a
  comparison that remembers to skip it. Two snapshots of an identical
  surface therefore differ in exactly one field, and a test pins that.
- An effect with an unknown `kind` is refused at floor load, not skipped at
  check time. A skipped effect is a silent pass, which is the whole disease.
- `effects: []` is refused for the same reason `surfaces: []` already is.

## What deliberately did NOT change

- **The existing CLI is untouched.** `obsgate --metrics X --floor Y` parses,
  gates, and exits 0/1/2/3 exactly as before; subcommands are added, so an
  adopter's pipeline does not move. The exit-code table only *grows* (4 =
  FROZEN), and 4 is unreachable without the new `--samples` flag.
- **No new verdict for the single-payload path.** Empty-200 and cardinality
  keep their existing words and messages; they gained a party prefix and
  nothing else.
- **Counter-reset detection is family-SUM based, not per-series.** A reset on
  one series masked by growth on a sibling in the same family is **not**
  detected. Storing every series' value would give the exact answer and
  would also reintroduce the unbounded-read shape this note just spent a
  paragraph capping. Recorded as a known limit rather than fixed, and it is
  in the round record as deferred with that reason - not discovered later by
  someone who assumed the stronger claim.
- **No histogram-quantile or rate() arithmetic.** `increased` compares sums
  of raw values. This tool checks whether a surface can witness a claim; it
  is not a query engine and will not grow into one.
- **No storage, no daemon, no retention.** Snapshots are files the caller
  keeps. The moment this tool owns a time series database it has stopped
  being copy-in, and `framework_only.py` would be right to say so.

## Guards shipping with this

- [x] `test_snapshot_holds_its_declared_envelope` (enforces n, p95_ms, memory_mb)
- [x] `test_two_snapshots_of_one_surface_differ_only_in_captured_at`
- [x] `test_label_values_are_capped_and_say_so`
- [x] `test_missing_effects_section_refuses_rather_than_passing`
- [x] `test_counter_reset_is_named_not_generically_failed`
- [x] `test_frozen_exporter_is_frozen_not_witnessed`
- [x] `selfcheck` planted-bad cases for every detector above, all
      mutation-verified in [round 12](../rounds/round-012.md)
