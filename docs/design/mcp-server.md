---
sutradhar_budget: mcp-roundtrip
n: 200
n_unit: round trips
p95_ms: 300
memory_mb: 8
ci_slack: 2.0
---

# Design note: the guards as agent-callable tools

<!-- Written before the code, which is the only order in which 1.1 is worth
     anything. The numbers below were measured first and chosen second. -->

## What and why

Every guard in this repo runs in CI, which is to say: **after** the agent has
finished. That placement is not wrong, but it is the slowest possible
feedback loop. The agent writes a fix, opens a PR, and learns twenty minutes
later that the guard it never ran says the fix is decoration.

This adds a second placement without moving the first. `mcp_server.py` is a
stdio MCP server that exposes nine guards as tools an agent can call **mid
-task**, in the same loop where it is writing the code. The agent asks
`verify_guard` whether the guard it just wrote actually goes red, gets the
answer in one round trip, and fixes it before the commit exists.

The reference shape is a platform shipping an MCP server so that agents call
it as tools rather than as a shell. We are doing the same thing to a
copy-in toolkit, and `js/probe/mcp.mjs` already established the precedent in
this repo: MCP's stdio transport is newline-delimited JSON-RPC 2.0, small
enough to implement directly, so the adapter costs zero dependencies and
`framework_only.py` stays green.

## Protocol, verified rather than remembered

The protocol was read from the specification on **2026-09-02**, not written
from memory. That mattered more than expected:

| Page | URL |
|---|---|
| Versioning (which revision is current) | <https://modelcontextprotocol.io/specification/versioning> |
| Base protocol, `_meta`, error codes, `resultType` | <https://modelcontextprotocol.io/specification/2026-07-28/basic/index> |
| Versioning and compatibility, era model | <https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning> |
| stdio transport (framing) | <https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio> |
| `server/discover` | <https://modelcontextprotocol.io/specification/2026-07-28/server/discover> |
| Tools (`tools/list`, `tools/call`, `isError`) | <https://modelcontextprotocol.io/specification/2026-07-28/server/tools> |
| Legacy lifecycle (`initialize` handshake) | <https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle> |
| Legacy stdio transport | <https://modelcontextprotocol.io/specification/2025-06-18/basic/transports> |

**The current protocol version is `2026-07-28`, and it has no handshake.**
Version, client identity and client capabilities travel in every request's
`_meta` field under `io.modelcontextprotocol/*`; the protocol is explicitly
stateless, and `server/discover` (which servers **MUST** implement) replaces
`initialize` as the way a client learns what a server speaks. The
`initialize` / `notifications/initialized` handshake is **legacy** —
`2025-11-25` and earlier.

Building this server from memory would have produced a server that only
speaks the legacy era, and by the spec's own compatibility matrix a modern
client talking to a legacy server **fails**. So this server is **dual-era**,
which the spec permits explicitly: *"A dual-era server selects its behavior
from how the client opens: a request carrying modern per-request `_meta` is
served statelessly according to this revision; an `initialize` request
selects legacy semantics."*

Supported versions, newest first: `2026-07-28`, `2025-11-25`, `2025-06-18`.

Two consequences worth stating, because both are places a plausible guess
would have been wrong:

- Every result carries `resultType: "complete"`. Modern clients require it;
  legacy clients are required to ignore fields they do not know, and the
  spec tells modern clients to read an absent `resultType` as `"complete"`,
  so one shape serves both eras.
- A modern request naming a version we do not support gets
  `UnsupportedProtocolVersionError` (`-32022`) with `data.supported`, not a
  generic failure. That code is spec-defined; the `-32000`..`-32019` range
  the older adapter used is now explicitly discouraged for new code.

## The tools

Nine, one per guard surface, each shelling out to the **real guard CLI** via
`subprocess` (doctrine 2.3 — through the seam the humans and CI use, never
import-and-monkeypatch, so the tool cannot pass while the command a person
types fails).

| Tool | Guard | Answers |
|---|---|---|
| `verify_guard` | `verify_guard.py` | Is this guard real? `VERIFIED` / `DECORATION` / `INCONCLUSIVE` |
| `budget_check` | `budget.py` | Is every declared budget enforced by a test? |
| `obsgate_check` | `obsgate.py check` | Does the observability floor exist? (`FROZEN` reachable with `samples`) |
| `obsgate_snapshot` | `obsgate.py snapshot` | Digest this metrics surface now |
| `obsgate_effects` | `obsgate.py effects` | Was the change witnessed? |
| `rounds_check` | `rounds.py --check` | Are the round records valid, rule ids real? |
| `swallow_lint` | `swallow_lint.py` | New silent exception swallows against the baseline |
| `interpolation_lint` | `interpolation_lint.py` | Query-language interpolation risks |
| `framework_only` | `framework_only.py` | Still stdlib-only, still no dependency manifest |

Descriptions are written for an agent to **route on** — each says what
question the tool answers and what its verdicts mean, because a tool an
agent cannot pick correctly is a tool it will not call.

## The distinction the whole design turns on <!-- doctrine 2.4 -->

MCP gives a server two ways to say something went wrong, and choosing
between them wrongly is this server's version of the R3-1 scar: an
instrument that cannot tell *"the subject failed"* from *"I failed"* reports
the wrong outage with total confidence, and it always reports it about the
subject.

| What happened | How it is reported | Why |
|---|---|---|
| Guard ran, verdict green | result, `isError: false` | a measurement |
| **Guard ran, verdict RED** | **result, `isError: false`**, verdict in `structuredContent` | **also a measurement.** A red guard is the tool working |
| Instrument failed | **JSON-RPC error**, `data.party: "instrument"` | no measurement was taken |

The middle row is the load-bearing one. The tempting implementation returns
a JSON-RPC error when a guard exits non-zero, and it is wrong twice over.
It tells the agent *"your call failed, retry it"* about a call that
succeeded perfectly and returned bad news — and per the spec, `isError:
true` is for *"actionable feedback that language models can use to
self-correct and retry with adjusted parameters"*. A `DECORATION` verdict is
not something the agent fixes by adjusting parameters. It is something the
agent fixes by writing a better guard. Reported as an error it reads as
flakiness, and flakiness is retried, not acted on.

So exit codes are partitioned per tool into **result codes** and everything
else:

| Tool | Result exit codes | Instrument |
|---|---|---|
| `verify_guard` | `0` VERIFIED, `1` DECORATION, **`2` INCONCLUSIVE** | anything else |
| `obsgate_*` | `0` OK, `1` UNWITNESSED, `3` INCONCLUSIVE, `4` FROZEN | **`2`** and anything else |
| the other six | `0` OK, `1` FINDINGS | **`2`** (unknown flag / bad path) and anything else |

`verify_guard` is the exception that proves the rule: its exit 2 is
`INCONCLUSIVE`, a deliberate tri-state verdict meaning *"I could not tell"*,
and "I could not tell" is a finding, not a crash. Every other guard uses
exit 2 for a usage error, which is the caller's or the server's fault and
therefore an instrument failure. A single shared table would have
misclassified one of these two, silently, in whichever direction the author
happened to guess.

## Cardinalities and budgets <!-- doctrine 1.1 -->

| Dimension | Design N | Enforced by |
|---|---|---|
| protocol round trips in one server process | 200 | `test_mcp_roundtrip_holds_its_declared_envelope` |
| wall clock for those 200 round trips | 300 ms (x2 CI slack) | same |
| peak Python heap across them | 8 MB (x2 CI slack) | same |
| captured bytes per stream per tool call | 65,536 (`MAX_OUTPUT_BYTES`) | `test_output_cap_truncates_and_says_so`, `test_output_cap_matches_the_design_note` |

**Provenance of these numbers** (doctrine 5.1). The ceilings are *chosen*;
the baseline behind them is *measured*, and the measurement had to be taken
twice.

A pre-code prototype of the hot path — spawn the server, then 200
`tools/list` round trips over the pipe — ran in **17, 20 and 20 ms across
three runs** (per-call p95 **0.11 ms**, client peak heap 0.02–0.04 MB), and
a ceiling was chosen against it. That prototype was **wrong by 5x**,
because its stub tool table carried nine short descriptions while the
shipped one carries nine long agent-routable descriptions plus full input
and output schemas: **20,896 bytes per response**, not ~2,000. Re-measured
against the **shipping server**, the same 200 round trips run in **100, 100
and 102 ms** (per-call p95 **0.60 ms**) with a client-side peak Python heap
of **0.12–0.13 MB**. Process spawn plus the first round trip costs
**19–21 ms**.

The declared numbers are the second set. The first set is left in this note
on purpose: a prototype is a *proxy* for the surface, and a number read off
a proxy is not a measurement of the thing (doctrine 5.1, and the reason 6.6
insists a claim is worth what the surface behind it is worth). The proxy
agreed with itself three times, which is exactly how this class survives.

The wall-clock ceiling is ~3x the real baseline and `ci_slack` doubles it
again, matching the convention in [obsgate-depth.md](obsgate-depth.md) and
[lint-scan.md](lint-scan.md); the extra slack is spent here rather than
elsewhere because this baseline measures **pipe I/O and process
scheduling**, which are noisier on a shared runner than the pure-CPU paths
those notes measure. The looseness costs nothing, because the regression
this ceiling exists to catch is not a few milliseconds of drift — it is
**per-call work that should be per-session**. A `tools/list` that re-read
the guard directory from disk, or (the patch someone will actually reach
for) re-spawned a subprocess per call, lands at 26–780 ms *each* by the
measurements below: 200 of those is 5–150 seconds, one to two orders of
magnitude above the ceiling. A tripwire that far from the wire does not
need to be tight.

The memory ceiling is the same kind of tripwire, aimed at the accumulation
bug: a server that retained each call's captured output, or a client that
grew its buffer without bound, breaks 8 MB long before it breaks anything
else.

**What a real tool call costs, for honest expectations.** The protocol layer
is not the cost; the guard is. Measured on the same machine, three runs
each, `--selfcheck` end to end: `interpolation_lint` 26–28 ms,
`swallow_lint` 28–31 ms, `framework_only` 49–58 ms, `rounds` 50–66 ms,
`budget` 56–60 ms, `obsgate` 76–102 ms, `verify_guard` **688–778 ms** (it
builds a git worktree and runs a test suite twice, by design). So the
0.11 ms round trip is well under 1% of even the cheapest real call, and
`verify_guard` is a tool an agent should expect to wait on. Its description
says so, because an agent that does not know a tool is slow will call it in
a loop.

`MAX_OUTPUT_BYTES` is the fourth number and the one with teeth. A guard
pointed at a large tree can print megabytes — `swallow_lint` on a codebase
with thousands of baselined swallows, `interpolation_lint` on a monorepo.
An MCP tool result goes straight into a model's context window, so an
uncapped result is the doctrine 2.6 unbounded-read class with a new and
more expensive consumer: it does not OOM a store, it evicts the agent's
working memory and costs real money doing it. Each stream is capped at
64 KiB, and **truncation is stated, never silent**: the text block carries a
`[truncated: N of M bytes]` marker and `structuredContent` carries
`stdout_truncated` / `stdout_total_bytes`. A silently truncated guard
report is worse than no report, because the agent reads a partial finding
list as a complete one.

## Failure story <!-- doctrine 1.4 -->

| Dependency | Down | Slow | Partial |
|---|---|---|---|
| the guard CLI file | missing / not executable -> JSON-RPC `-32603`, `party: instrument`, naming the path it looked for; **never** a verdict | n/a | file present but exits on an unparseable code -> `-32603`, the exit code quoted, explicitly not attributed to the code under test |
| the guard subprocess | raises `OSError` on spawn -> `-32603`, `party: instrument`, exception **type** printed | exceeds `timeout_s` -> `-32603`, `party: instrument`, the timeout named; the agent is told the guard was killed, not that the code passed | killed by a signal (negative exit code) -> `-32603`; a signal is not a verdict |
| the guard's own findings | guard exits red -> **result**, `isError: false`, verdict named | a long run is the caller's wait, capped by `timeout_s` | output over the cap -> result **with the truncation stated** in both text and structured content |
| `git` (for `verify_guard`) | absent or the path is not a repo -> the guard itself answers `INCONCLUSIVE` (exit 2), returned as a **result** | worktree build is the bulk of the 688–778 ms | dirty tree / merge commit -> `INCONCLUSIVE`, which is the guard's honest tri-state, not an error |
| the metrics endpoint (`obsgate_*`) | unreachable -> guard exits 3 -> result `INCONCLUSIVE`, party `endpoint` in the guard's own text | `--timeout` elapses -> same | floor unmet -> result `UNWITNESSED`; frozen -> result `FROZEN` |
| the client | sends a line that is not JSON -> `-32700` parse error, `id: null`, **server keeps running** | n/a | sends a request with no `id` that is not a notification -> `-32600`; unknown method -> `-32601`; unknown tool or bad argument type -> `-32602` |
| the client's protocol version | modern `_meta` naming a version we do not speak -> `-32022` with `data.supported` | n/a | modern `_meta` missing the required `clientCapabilities` -> `-32602`, as the spec requires; a legacy `initialize` naming an unknown version gets our newest legacy version back, per the negotiation rule |
| the server's own dispatch | any unexpected exception is caught per request, its **type** printed to stderr and returned as `-32603` with `party: instrument`; the loop does not die | n/a | a single bad request never takes down the session — the next line is served normally, which a test pins |

The rows that earn the note are the last two. A crash in this server's own
argument handling must not be able to file a bug against the user's guard,
their repo, or their metrics endpoint; and a malformed request must not be
able to end a session the agent is mid-task in.

## Illegal states <!-- doctrine 1.2 -->

- A tool cannot be dispatched without an entry in `TOOLS`, and a `TOOLS`
  entry cannot exist without both an `inputSchema` and a `result_codes` set.
  A class ratchet walks the table and fails on any tool missing either, so
  a tool added later cannot inherit a default exit-code partition by
  omission — the partition is the thing most likely to be wrong.
- Captured output is capped by the **only** function that can produce it;
  there is no path from `subprocess` output to a content block that skips
  the cap.
- Arguments are built from typed schema entries, never by splicing a
  caller's string into a shell. **No tool passes `shell=True`** — `argv`
  lists throughout, so a repo path containing a semicolon is a path, not a
  command. `verify_guard`'s `guard_cmd` is the single exception by
  necessity: it is a command, the guard's own CLI takes it as one, and it is
  forwarded as a single opaque `argv` element for the guard to interpret.
  Called out here rather than left for a reader to notice.
- `--update-baseline` is deliberately **not exposed** by `swallow_lint`.
  Every other flag is read-only; that one rewrites the ratchet's floor. An
  agent that can raise its own floor mid-task can make any swallow finding
  disappear, which converts a ratchet into a rubber stamp. Copy-in users who
  want it run the CLI.

## What deliberately did NOT change

- **The CI path is untouched.** `ci/guards.yml`, every guard CLI, every flag
  and every exit code are exactly as they were. This server is a second
  placement of the same guards, not a replacement: CI remains the gate that
  cannot be skipped, and an agent calling a tool mid-task is an accelerator
  in front of it. If the two ever disagree, CI is right, because CI runs the
  command a human types.
- **Copy-in remains the primary contract.** The guards are still files you
  copy into your repo and run with `python guard.py`. This server is
  optional sugar over that surface, exactly as `js/probe/mcp.mjs` is
  optional sugar over a bridge that was already `curl`-able. Nothing in the
  toolkit requires an MCP client, and `SUTRADHAR_MCP_GUARD_DIR` exists so an
  adopter who copied the guards to `scripts/` can point the server at them.
- **No new guard logic.** Not one detector, verdict or exit code is defined
  here. Every answer this server returns was computed by a guard that
  already existed; the server's entire job is transport plus an honest
  exit-code partition. That is why there is no new golden data.
- **stdio only.** No Streamable HTTP, no auth, no session store. HTTP would
  bring origin validation, bearer tokens and a listening socket into a
  framework that installs nothing, and `framework_only.py` would be right to
  object.
- **No `resources`, `prompts`, `logging`, `subscriptions` or pagination.**
  The capability block advertises `tools` and nothing else, so a client is
  never told a surface exists that would answer emptily. Nine tools fit in
  one `tools/list` page; when they do not, pagination is a real feature and
  gets a real design.
- **The legacy era is supported, not preferred.** `initialize` works because
  most shipped clients today still send it. It is not the path the tests
  treat as canonical, and if the ecosystem finishes moving, dropping it is a
  deletion (doctrine 8.2), not a rewrite.

## Guards shipping with this

- [x] `test_mcp_roundtrip_holds_its_declared_envelope` (enforces n, p95_ms, memory_mb)
- [x] `test_output_cap_truncates_and_says_so` (end to end, through the real seam)
- [x] `test_output_cap_matches_the_design_note` (pins this note to the constant)
- [x] `test_red_guard_is_a_result_not_an_error` (the middle row above)
- [x] `test_instrument_failure_is_an_error_naming_the_instrument`
- [x] `test_every_tool_has_a_schema_and_a_result_code_partition` (class ratchet)
- [x] `test_malformed_request_does_not_kill_the_session`
- [x] `test_unknown_flag_exits_2`
- [x] `selfcheck` spawns itself, handshakes in both eras, lists tools, and
      calls a real tool green **and** red — mutation-verified in
      [round 13](../rounds/round-013.md)
