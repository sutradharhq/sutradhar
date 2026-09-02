# Round 13 - 2026-09-02

Lenses: protocol fidelity, instrument self-attribution, declaration-vs-effect

**What this round was.** A build, not a review pass. Every guard in this
repo runs in CI, which is to say *after* the agent has stopped. This round
added a second placement without moving the first: an MCP stdio server
exposing nine guards as tools an agent can call mid-task, so `verify_guard`
can answer "is this guard real" while the guard is still being written.
One design note before the code, nine mutations against the result, and one
end-to-end smoke through the live server.

Two of the findings below were produced by the process rather than the
code: the protocol was verified against the specification instead of
recalled, and the mutation run killed a guard I had already written and
believed.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R13-1 | high | 7.2 | fetching modelcontextprotocol.io before writing any code | fixed | The task, and this session's own prior knowledge, described MCP as an `initialize` / `notifications/initialized` handshake with `protocolVersion` negotiated once per connection. That is the **legacy** protocol. The current revision is **2026-07-28**, which has **no handshake at all**: version, client identity and capabilities ride in every request's `_meta` under `io.modelcontextprotocol/*`, the protocol is explicitly stateless, and `server/discover` - which servers MUST implement - replaces `initialize`. Building from memory would have shipped a legacy-only server, and by the spec's own compatibility matrix a modern client talking to a legacy server **fails**. Fixed by reading eight specification pages (URLs recorded in the design note) and building **dual-era**: modern `_meta` requests served statelessly, `initialize` selecting legacy semantics, both tested. This is 7.2 in its purest form - trust the tree, not the doc, and here not the memory of a doc. Round 12 filed the same rule for the same reason about DOCTRINE.md; two rounds running, the most persuasive kind of wrong was a confidently-remembered address |
| R13-2 | high | 2.2 | mutation M5, run against a guard I had already written | fixed | `test_verify_guards_exit_2_is_a_verdict_and_everyone_elses_is_not` read the `result_codes` **declaration** in the tool table and never exercised the code that consults it. Collapsing the per-tool partition to one shared `{0: OK, 1: FINDINGS, 2: OK}` lookup inside `run_tool` - which turns every guard's usage error into a **pass** and `verify_guard`'s INCONCLUSIVE into a fabricated OK - left the whole suite green and the selfcheck exit 0. The guard was decoration and looked like coverage. Fixed with two tests that drive the runtime seam instead: a non-git directory makes `verify_guard` exit 2 = INCONCLUSIVE and must arrive as a **result**; an empty rounds directory makes `rounds` exit 2 = usage error and must arrive as an **instrument error**. M5 now kills both. This is 3.6 wearing a backend costume - a declaration is not an effect, and asserting on the table measured string presence, not reachability |
| R13-3 | high | 2.4 | writing the failure-story table before the code | fixed | The obvious implementation returns a JSON-RPC error whenever a guard exits non-zero, and it is wrong twice over. Per the specification, `isError: true` means *"actionable feedback that language models can use to self-correct and retry with adjusted parameters"* - and `DECORATION` is not fixed by adjusting parameters, it is fixed by writing a better guard. An agent handed a red verdict as an error reads flakiness and **retries**, which is the exact opposite of the intended action. So: a guard that RAN is a result whatever its verdict (`isError: false`, verdict in `structuredContent`), and only a guard that could not run at all is an error, attributed to the `instrument`. This is the R3-1 scar class reproduced inside the tool built to prevent it - an instrument whose error branch cannot say whose failure it is |
| R13-4 | med | 5.1 | re-measuring the shipped server against the pre-code prototype | fixed | The design note's latency ceiling was chosen against a prototype that ran 200 `tools/list` round trips in 17-20 ms. The **shipping** server runs the same 200 in 100-102 ms: the prototype's stub tool table carried nine short descriptions, while the real one carries nine agent-routable descriptions plus full input and output schemas - **20,896 bytes per response, not ~2,000**. The prototype was wrong by 5x and agreed with itself three times, which is how this class survives. A number read off a proxy is not a measurement of the thing. Both sets of numbers are left in the note with the correction stated, and the declared `p95_ms` is now 300 (~3x the real baseline) rather than 120 (~1.2x, which would have flaked on any shared runner) |
| R13-5 | med | 2.6 | design-time, writing the budget table | fixed | An MCP tool result goes straight into a model's context window, so an uncapped one is the unbounded-read class with a more expensive consumer: it does not OOM a store, it evicts the agent's working memory and bills for the privilege. `swallow_lint` on a large tree prints megabytes. Capped at 65,536 bytes per stream in the one function that can produce captured output, so there is no path around it - and truncation is **stated** in both the text block and `structuredContent`, because a partial finding list read as a complete one is a wrong answer wearing a right one's shape. Found before any code existed, which is the only place this class is cheap |
| R13-6 | med | 2.2 | asking what would falsify the selfcheck | fixed | A selfcheck that handshakes and lists tools proves the transport and nothing about the tools; this repo already carries the scar of five `--selfcheck` flags that exited 0 because the module merely imported. `SUTRADHAR_MCP_GUARD_DIR` - a real feature, for adopters who copied the guards to `scripts/` - doubles as the falsifier: pointed at an empty directory, every tool call becomes an instrument failure and the selfcheck must go red. `test_selfcheck_actually_calls_a_tool` asserts exactly that, and mutation M4 (delete the tool-call section) kills it |
| R13-7 | low | 1.2 | writing the illegal-states section | fixed | `swallow_lint --update-baseline` is deliberately **not exposed** as a tool argument. Every other flag is read-only; that one rewrites the ratchet's floor, and an agent that can raise its own floor mid-task can make any swallow finding disappear - which converts a ratchet into a rubber stamp. Similarly, no tool passes `shell=True`: arguments are built as `argv` lists from typed schema entries, so a repository path containing a semicolon is a path. `verify_guard`'s `guard_cmd` is the one necessary exception (it *is* a command) and is called out in the note rather than left for a reader to notice |
| R13-8 | low | 2.4 | reading the 2026-07-28 error-code table | fixed | The existing adapter in `js/probe/mcp.mjs` returns `-32000` for server errors. That range (`-32000`..`-32019`) is now explicitly **legacy**, new implementations SHOULD NOT use it, and receivers MUST NOT assume any meaning for it. Instrument failures here use the standard `-32603` with `data.party: "instrument"`, and an unsupported protocol version uses the spec-defined `-32022` with its `supported` list. Recorded rather than fixed in the JS adapter: that file speaks the legacy era end to end and changing one code in isolation would make it inconsistent with itself |
| R13-9 | low | 2.3 | choosing how tools reach the guards | closed | Every tool shells out to the real guard CLI via `subprocess`, never by importing the module and calling into it. An in-process adapter would be faster and would also be able to pass while the command a human types fails - the tested-but-half-dead shape `verify_guard` exists to catch. The measured cost of the decision: the protocol round trip is 0.60 ms and the cheapest real guard call is 26 ms, so the seam is under 3% of the cheapest call and under 0.1% of `verify_guard`'s |

## Mutations run (doctrine 2.2)

`selfcheck` is `python3 python/sutradhar_guards/mcp_server.py --selfcheck`;
`pytest red` counts failures in `python/tests/test_mcp_server.py`.

| # | mutation | selfcheck | pytest red |
|---|---|---|---|
| M1 | a red guard raises `InstrumentError` instead of returning a result | exit 1 | 5 |
| M2 | the output cap removed (`cap_output` never truncates) | exit 1 | 3 |
| M3 | the unknown-flag refusal blinded (an unrecognised flag is ignored) | exit 0 | 1 |
| M4 | the selfcheck no longer calls a tool (handshake + `tools/list` only) | exit 0 | 1 |
| M5 | the per-tool exit-code partition collapsed to one shared table | exit 0 | **2** |
| M6 | the `instrument` party attribution dropped from a missing guard | exit 0 | 2 |
| M7 | a malformed line kills the session instead of being answered | exit 1 | 2 |
| M8 | the modern era removed (no `server/discover`, no version refusal) | exit 1 | 4 |
| M9 | the declared `p95_ms` tightened to 1 ms in the design note | exit 0 | 1 |

No mutant survived - **on the second run**. On the first, **M5 survived
with selfcheck exit 0 and zero failures**, which is R13-2 and the most
useful thing this round produced. The guard against that mutation existed,
was written deliberately, read plausibly, and asserted on the tool table
rather than on the behaviour, so blinding the behaviour cost it nothing.
Worth stating plainly: had the mutation run been skipped, this round would
have shipped a tested-looking hole in the one distinction the whole design
turns on.

Two other properties of the table are worth more than the counts. M3, M4,
M6 and M9 exit 0 on the selfcheck **by design**: an unknown-flag refusal, a
declared latency envelope and a party attribution are enforced by pytest,
not by the tool's own selfcheck, and a selfcheck cannot be expected to
notice that it has stopped checking something - which is precisely why M4
needs an external falsifier rather than an internal assertion. And the
pytest counts are inflated by cascade (several tests share a live server),
so the load-bearing kill in each row is the dedicated point test: M1 kills
`test_red_guard_is_a_result_not_an_error`, M5 kills both runtime-partition
tests, M4 kills `test_selfcheck_actually_calls_a_tool`.

Restored to green after every mutation, and the file diffed byte-identical
against its pre-mutation copy: `310 passed`.

## End-to-end smoke (doctrine 6.6)

Not a unit test and not a mock: the real server, spawned as a subprocess,
driven over stdio, asked to verify a real commit in this repository.

    server/discover -> supportedVersions ["2026-07-28", "2025-11-25", "2025-06-18"]
    tools/list      -> 9 tools
    tools/call verify_guard {commit: HEAD (1677d14),
                             guard_cmd: pytest python/tests/test_obsgate_depth.py}

**Verdict actually returned: `VERIFIED`, exit 0, `isError: false`, 3,948 ms**,
843 bytes of stdout, untruncated. The guard's own JSON carries
`"weak_proof": true` with the reason spelled out: *the guard went red by
failing to LOAD (import/collection error), not by asserting* - reverting
`obsgate.py` removes symbols `test_obsgate_depth.py` imports, so the suite
cannot collect. `verify_guard` grades that as VERIFIED (weak) rather than
counting it as a clean pass, which is the honest answer and is exactly the
limit its own docstring declares. Recorded here as the verdict received,
not as a stronger claim than it is (5.1).

## Corrected premises

- **"MCP is the `initialize` handshake."** It has not been since revision
  `2026-07-28` (R13-1). The handshake is legacy. The tell was one page -
  `/specification/versioning` names the current revision in a single
  sentence - and it was only read because the instruction to verify was
  explicit. The prior belief was confident, coherent, and eight months out
  of date.
- **"I wrote a test for that."** M5 (R13-2). The test existed and was
  vacuous against the mutation it was written for. A guard is not verified
  by having been written thoughtfully; it is verified by being shown to
  fail.
- **"The prototype measures the hot path."** It measured a stub whose
  payload was a tenth the size of the real one (R13-4).

## Harness gotchas

- The selfcheck spawns **itself** by `Path(__file__).resolve()`, so the
  guard directory resolves correctly in both the repo layout and a copy-in.
  `SUTRADHAR_MCP_GUARD_DIR` overrides it - useful for adopters, and the
  only reason `test_selfcheck_actually_calls_a_tool` can exist.
- `python -m sutradhar_guards.mcp_server` with **no arguments starts a
  server** and blocks reading stdin. Nothing in the suite does this, but a
  typo'd flag would have, which is why the unknown-flag refusal matters
  more here than in the scanning tools: a process sitting on stdin looks
  exactly like one that passed.
- The test client is written from scratch rather than importing
  `mcp_server._Client`. A shared client breaks identically under a mutation
  and both sides agree, which is how an instrument stops being independent
  of its subject.
- `json.dumps` escapes newlines, which is what keeps a guard's multi-line
  stdout from violating the transport's one-message-per-line rule. A test
  pins it, because the natural refactor (writing the text out directly)
  would break every call at once.

## What was ruled out (doctrine 7.4)

- **Streamable HTTP transport.** It brings origin validation, bearer
  tokens and a listening socket into a framework that installs nothing;
  `framework_only.py` would be right to object. stdio only.
- **In-process dispatch instead of `subprocess`.** Faster, and able to pass
  while the real command fails (R13-9). Rejected on 2.3, with the cost
  measured rather than assumed.
- **Exposing `--update-baseline`** on `swallow_lint` (R13-7). Rejected: an
  agent that can raise its own floor mid-task turns a ratchet into a rubber
  stamp.
- **`resources`, `prompts`, `logging`, `subscriptions`, pagination.** Not
  advertised, so a client is never told a surface exists that would answer
  emptily. Nine tools fit one page; pagination becomes real work the day
  they do not.
- **Changing `js/probe/mcp.mjs` to the modern era** (R13-8). That adapter
  speaks legacy consistently; a one-code fix would make it inconsistent
  with itself. Left as a whole-file decision for whoever needs it.

## Stop decision

STOP for this workstream (doctrine 8.3). The marginal round is now worth
less than the next cheapest activity: the second mutation run produced no
survivors, and the one real hole this round found was found by mutation in
round 1 of the loop rather than round 9, which is the process working.

The honest limit is the same one round 12 ended on, and it is worth
repeating because this tool is more exposed to it: **everything verified
here was verified against clients this session wrote.** The selfcheck's
client, the test client and the smoke client are all mine, so they share my
reading of the specification. Dual-era support in particular is checked
against two client implementations of one person's understanding, not
against a shipped client of either era. That is a 5.2 limit - synthetic
results do not leave as evidence - and the next useful signal on this
server is not another self-directed round. It is a real MCP client, in
someone else's agent loop, calling `verify_guard` on a repository I have
never seen (8.4, 8.5).
