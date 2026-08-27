# Round 12 - 2026-08-27

Lenses: observability depth, instrument self-attribution, vacuous-pass hunting

**What this round was.** Not a review pass - a build. `obsgate` could answer
"does this surface exist" and could not answer "was my change witnessed
there", which is the half of 6.6 that decides when a task is done. Three
additions (snapshot digests, effect checking, frozen-exporter detection),
one design note written before the code, and twelve mutations run against
the result. The findings below are what the building turned up, including
one about this session's own citations.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R12-1 | high | 2.4 | writing the failure-story table before the code | fixed | Every message obsgate emitted was unattributed, and the parse path had no crash containment at all: if `parse_metrics` had raised, the traceback or a caller's fallback would have spoken about the ENDPOINT, when the failure was obsgate's. This is the R3-1 scar class exactly - an instrument whose error branch cannot say whose failure it is reports the wrong outage with total confidence, and it always reports it about the system. Fixed by a three-party vocabulary (`instrument:` / `endpoint:` / `floor:`) on every violation and every effect verdict, a narrow catch that prints the exception TYPE and explicitly disclaims itself as evidence about the endpoint, and two class ratchets asserting no failure this tool can emit is unattributed |
| R12-2 | med | 7.2 | grepping DOCTRINE.md while writing this table | fixed | The first draft of the code, tests, design note and operations doc cited doctrine rules **6.8, 6.9 and 6.11**. Those rules do not exist in this repository's DOCTRINE.md, which defines 6.1-6.6; they come from a standing doctrine outside this tree that this session was carrying in its head. Eighteen citations in four files pointed a public reader at authorities they cannot look up. Rewritten to the rules that do exist (2.4 for honest degradation and verdict wording, 5.1 for labelling, 6.4 for the cost of a false finding, 2.2 for guard-crash discipline). The rule is 7.2 and the correction is its exact shape: trust the tree, not the doc - or in this case, not the memory of a doc |
| R12-3 | med | 2.4 | writing the failure-story table | fixed | An HTML error page and an empty 200 both parse to zero samples, and the pre-existing gate gave them the same diagnosis ("payload contains no series at all"). They need different fixes - one is a broken exporter, the other is a broken route or proxy - and a reader given the wrong one loses the afternoon. A payload carrying non-comment lines that none parse is now diagnosed separately, as the endpoint answering with something that is not metrics |
| R12-4 | low | 2.6 | design-time, writing docs/design/obsgate-depth.md | fixed | The obvious snapshot format stores every distinct value of every label so that `appeared` can answer questions about specific label values. That rebuilds, inside the snapshot file, precisely the unbounded-cardinality bomb the floor check exists to catch: a `route` label carrying raw paths would put every URL the service ever served into a JSON file on disk. Capped at 64 distinct values per key, past which the snapshot records that it STOPPED LOOKING and questions about that key answer UNANSWERABLE, attributed to the instrument. Found before any code existed, which is the only place this class is cheap |
| R12-5 | med | 2.6 | building `_check_increased` | deferred | Counter-reset detection compares the family's value SUM. A reset on one series masked by growth on a sibling series in the same family is not detected, so `increased` can report WITNESSED across a restart. The exact fix - storing every series' value in the snapshot - is the unbounded read R12-4 just capped, and would make snapshot size scale with cardinality rather than with family count. Deferred deliberately, with the limit stated in the design note's non-goals and in this row, rather than left for someone to discover by trusting the stronger claim |
| R12-6 | low | 2.4 | writing `_counters_that_should_move` | fixed | The frozen check keys off counters that ought to move. Reading only `# TYPE` lines would have switched the whole detector silently off against the many exporters that ship no TYPE metadata - a detector that quietly stops detecting is worse than one that was never added. The `_total` naming convention is honoured as a fallback, and a surface with no must-move counter is told so in a note rather than accused (6.4: a false finding costs more trust than no finding) |

## Mutations run (doctrine 2.2)

Every new detector was blinded in turn; the run is red or the guard is
decoration. `selfcheck` is `python3 python/sutradhar_guards/obsgate.py
--selfcheck`; `pytest red` counts failures in
`python/tests/test_obsgate.py python/tests/test_obsgate_depth.py`.

| # | mutation | selfcheck | pytest red |
|---|---|---|---|
| M1 | `frozen_check` always returns "not frozen" | exit 1 | 7 |
| M2 | counter-reset branch disabled (a reset reports as a generic fall) | exit 1 | 5 |
| M3 | `_check_no_vanished` never sees a vanished family | exit 1 | 5 |
| M4 | `appeared` stops reading the before snapshot (already-present passes) | exit 1 | 4 |
| M5 | `stable_labels` ignores gained and lost label keys | exit 1 | 5 |
| M6 | the no-effects-section refusal returns an empty pass instead of raising | exit 1 | 5 |
| M7 | the snapshot digest stops sorting its series | exit 1 | 4 |
| M8 | the empty-200 violation loses its `endpoint:` party prefix | exit 1 | 4 |
| M9 | a parser crash is attributed to the endpoint instead of the instrument | exit 1 | 4 |
| M10 | `LABEL_VALUE_CAP` removed (the snapshot records every label value) | exit 1 | 5 |
| M11 | the declared `p95_ms` in the design note tightened to 1 ns | exit 0 | 1 |
| M12 | the non-metrics-payload diagnosis blinded | exit 1 | 4 |

No mutant survived. Two properties of this table are worth more than the
counts: M11 exits 0 on the selfcheck by design - a declared envelope is
enforced by pytest, not by the tool's own selfcheck, and that separation is
what the row demonstrates. And the pytest counts are inflated by cascade
(the CLI tests run the selfcheck, so a broken detector fails them too); the
load-bearing kill in each row is the dedicated point test plus, where it
applies, the class ratchet. Spot-checked for M2, M5 and M6 by name:
each killed its own point test AND `test_no_effect_failure_is_ever_unattributed`
or its sibling.

Restored to green after every mutation: `266 passed`.

## Corrected premises

- **"The doctrine I am working from is the doctrine in the repo."** It was
  not (R12-2). This session carried a superset numbering - 6.7 through 6.11 -
  that reads as authoritative and is not present in DOCTRINE.md, and it
  wrote eighteen citations against it before anything checked. The tell was
  cheap and was skipped: `grep -E '^\*\*[0-9]+\.[0-9]+' DOCTRINE.md` takes a
  second and would have caught it before the first line of code. Worth
  noting for the next session, because the ideas behind those phantom rules
  were all correct - it was only their addresses that were fabricated, which
  is the most persuasive kind of wrong.
- **"A frozen exporter is just an UNWITNESSED surface."** No: every metric
  is present and within bounds. Filing it as UNWITNESSED sends the reader to
  add metrics that already exist. It got its own verdict word and its own
  exit code for that reason, and the same argument produced COUNTER_RESET as
  a name separate from "the effect did not happen".

## Harness gotchas

- `--samples N` against a FILE source re-reads the same bytes and therefore
  always reports FROZEN. That is correct behaviour and it is also how the
  selfcheck and tests exercise the detector without a network, so do not
  "fix" it - but do not wire a file source into a frozen check in CI and
  read the exit 4 as a finding about a service.
- `math.fsum(sorted(values))` rather than `sum()` for the per-family value
  sum: scrapers do not promise series order, and a digest that changed with
  line order would report drift nobody caused.

## What was ruled out (doctrine 7.4)

- **Per-series values in the snapshot** - see R12-5. Rejected for the
  cardinality reason, not forgotten.
- **`rate()` / histogram-quantile arithmetic on the effects side.** This
  tool checks whether a surface can witness a claim; a query engine is a
  different tool and would end the copy-in, stdlib-only promise
  `framework_only.py` enforces.
- **Making `check` run `effects` automatically when the manifest declares
  them.** Tempting, and wrong: `check` reads one payload and has no before
  snapshot, so it would have to either invent one or silently skip - and a
  silent skip is the vacuous pass this whole round was spent removing.

## Stop decision

STOP for this workstream. The marginal round is now worth less than the next
cheapest activity (doctrine 8.3): the twelve mutations produced no survivors,
and the remaining known gap (R12-5) is documented, deliberate, and blocked on
a trade-off already argued in the design note rather than on effort. The next
useful signal on this tool is not another self-directed round - it is a real
metrics endpoint in someone else's deployment (8.4, 8.5). Everything checked
here was checked against payloads this session wrote, which is exactly the
provenance limit 5.2 names.
