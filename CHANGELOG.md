# Changelog

Versioning: semver on the toolkit's file contracts (CLI flags, library
APIs, baseline file formats, probe HTTP endpoints). Docs and doctrine
evolve freely within a minor version. Tags mark releases; copy-in users
upgrade by diffing against the tag they took.

## Unreleased

**Two doors closed, and a plugin that survives being installed** (round 16;
record: [docs/rounds/round-016.md](docs/rounds/round-016.md)).

- **BREAKING: a `--guard-cmd` is no longer a shell command.** `verify_guard`
  spawns it as one program with arguments - optionally prefixed by
  `cd <dir> &&`, whose directory must resolve inside the worktree - and
  refuses a pipe, a redirection, `;`, a stray `&&`, a backtick, `$(` or a
  bare `$`. A refusal exits **2 (INCONCLUSIVE)**, never 0, because no guard
  ran. `--setup-cmd` follows the same rule. The `cd python && python -m
  pytest tests/x.py -q` form every `Guard-cmd:` trailer uses still works;
  anything more complex belongs in a script you name. A program that cannot
  be started is now INCONCLUSIVE rather than the shell's exit 127 read as a
  guard going red.
- **The `Stop` hook will not run a `Guard-cmd:` trailer somebody else
  wrote.** It compares HEAD's author email with `git config user.email` and,
  when they differ or the repository has no identity, names the author, says
  why it did not run the trailer, and prints the command to run by hand.
  Checking out a pull request used to be enough to let its author choose a
  command that ran on your machine when your turn ended.
- **The MCP `verify_guard` tool's description opens with the warning** that
  it runs your command as the current user, that it is a test runner and not
  a linter, and that it should not be allowlisted. Every tool's `repo`
  argument is now confined to the git toplevel of the server's own working
  directory (the directory itself when that is not a repository); out of
  bounds is a caller error, and `SUTRADHAR_MCP_ANY_REPO=1` lifts it.
- **The plugin is self-contained, and installs in two commands.**
  `/plugin marketplace add sutradharhq/sutradhar` then
  `/plugin install sutradhar@sutradhar`. It ships the eight guard programs
  it runs under `plugin/guards/`, because an installed plugin is copied
  without the files around it - the old
  `${CLAUDE_PLUGIN_ROOT}/../python/sutradhar_guards` worked only from a
  checkout. The copies are pinned byte-for-byte to `python/sutradhar_guards/`
  by a test, and `python3 plugin/sync_guards.py` refreshes them.
  `claude --plugin-dir ./plugin` still works from a checkout.
- **`SUTRADHAR_GUARD_DIR` -> `<plugin root>/guards` -> instrument failure**
  is the hooks' guard-directory order, and the failure names both paths.
- **MCP output cap 65,536 -> 8,192 bytes per stream**, and truncation stops
  being a dead end: the full output of a truncated call is written to
  `<tempdir>/sutradhar-mcp/<tool>-<timestamp>.txt`, the notice names it, and
  `structuredContent.output_spill_path` carries it.
- **The `tools/list` payload is 20,718 -> 7,270 bytes** (~5,200 tokens saved
  per session, spent whether or not a tool is called), under a declared
  ceiling of 8,192 enforced over the real transport. The cut is repetition:
  the shared `repo`/`timeout_s` argument descriptions and the result-object
  field list now appear once in the server's `instructions` instead of nine
  times. `structuredContent` is unchanged apart from the new
  `output_spill_path`; its declared `outputSchema` now names only the three
  fields that are always present.
- **The plugin is exercised in an installed layout**, not only in a
  checkout: `plugin/` is copied somewhere with nothing around it and the
  pre-commit gate is driven there, asserting the deny. That is the layout
  the R16-1 bug lived in, and the one nothing had ever tested.
- **Known red:** `rounds.py docs/rounds/ --backflow docs/backflow.md` exits
  1. Thirteen register items came due at round 16 and round 16 decided none
  of them; the gate says so rather than being quieted. See
  [docs/backflow.md](docs/backflow.md).

**The harness inside the agent's loop** (round 15; design note:
[docs/design/agent-loop-hooks.md](docs/design/agent-loop-hooks.md)).

- **`plugin/`** (new): a Claude Code plugin that makes the guards
  non-optional for a session instead of merely available. It bundles two new
  hooks, and **references** rather than copies the existing MCP server and
  the two skills in `agent/skills/` - one server, one version, and a copy
  would be a second answer that wins silently the first time the two
  disagree. Load it with `claude --plugin-dir ./plugin` from a checkout; it
  is per-session on purpose and writes to nobody's `settings.json`.
- **Pre-commit gate** (`PreToolUse`): on a Bash `git commit`, runs the fast
  guards - `interpolation_lint` over the staged Python, `swallow_lint`
  against a baseline when one exists, `rounds --check` when `docs/rounds/`
  exists - and denies the commit with the guard's own output when one is
  red. A guard that is inapplicable is **named as skipped**, never folded
  into a green verdict, and the gate **says which tree it read**: the guards
  see the working tree, `git commit` takes the index, and the message lists
  the staged paths where the two differ (backflow B-15).
- **Verify-before-done** (`Stop`): if HEAD carries a `Guard-cmd:` trailer -
  the convention `ci/guards.yml` already reads - it asks `verify_guard`
  whether that guard is real. DECORATION blocks the turn from ending;
  INCONCLUSIVE is reported **as inconclusive and never as a pass**; a commit
  moving production and test files with no trailer gets a reminder, not a
  block. Silent otherwise, and it reports a given HEAD at most once per
  session.
- **A hook that crashes never blocks.** Any failure of the hook itself - a
  missing guard, a spawn error, a timeout, an exit code outside the guard's
  documented partition, a bug in the hook - is reported as an *instrument*
  failure naming the hook, and the action proceeds. Hook usage errors exit
  1, not 2, because 2 is the harness's block signal and a typo in our own
  configuration must not deny your tool call. A source ratchet over the AST
  of every hook script refuses `SystemExit(2)` and `shell=True`.
- **Budget** `precommit-gate` (new): 10 gated commits within 2,500 ms and
  16 MB, enforced by
  `test_precommit_gate_holds_its_declared_envelope`. Measured baseline
  155-172 ms per gated commit; the fast path costs 1.93-2.09x a bare
  interpreter start against a declared ceiling of 3.0x. R14-2 is a correct
  guard that was switched off the same afternoon because its signal cost
  more than it paid, and a gate on every commit has that failure with a
  shorter fuse.
- 35 new tests, all driving the hooks as real subprocesses over real
  repositories (370 -> 405).

**Two defects reported by the threads that use this, and the mechanism that
should have carried them here sooner** (round 14; register:
[docs/backflow.md](docs/backflow.md)).

- **`expectEffect` was blind to form state.** It compared the URL,
  `body.innerText`, and configured storage keys - and `innerText` reports
  neither an input's value nor a button's `disabled` attribute. Typing into a
  field and watching a submit button enable moved nothing it could see: a
  false red on a working control, and the expensive inverse, a silent pass
  over a form that did nothing. New exported `readFormState` covers value,
  checked, disabled, the `aria-*` equivalents, multi-select selections, and
  contenteditable text. Snapshot and comparison are driven off one
  `EFFECT_DIMENSIONS` list, so a dimension captured but never compared is no
  longer representable. **Breaking for anyone who monkey-patched the internal
  snapshot shape**; the public signature is unchanged.
- **`js/cypress/uiGuards.selftest.mjs`** (new): compiles the real shipped
  source with esbuild and runs it against a DOM stub. The load-bearing case is
  two documents with identical body text and different form state. It exits 2,
  not 0, when it cannot run.
- **`swallow_lint.py` no longer walks vendor trees.** The only exclusion was
  `__pycache__`, so a project-root scan descended into `.venv` and buried the
  real finding under third-party ones. The walk now skips vendor directories,
  **reports how many files it skipped** and how to override
  (`--include-vendor`), and still scans an explicitly named path regardless.
  `build`, `dist` and `env` are deliberately not excluded - they are real
  package names, and a too-greedy exclusion is the same defect inverted.
  **Adopters should re-run `--update-baseline`**: a baseline recorded over a
  vendor tree will now show those files as improved.
- **Doctrine 2.9** (new): *a check that could not run has not passed.* The only
  rule here that four independent build threads each invented separately
  before it reached this file.
- **`rounds.py --backflow <register>`** (new): gates a backflow register.
  An item past its `by-round` and still `owed` or `deferred` fails until
  somebody adopts it, rejects it with a reason, or re-defers it with a reason.
  `practice` evidence (a documented intention) may strengthen an existing
  scarred rule's mechanism but may not found a new rule - 8.1, enforced.
  Closes R7-1, high and deferred since round 7.
- **`rounds.py --designs <notes>`** (new): 8.1 for *mechanisms*, not just
  rules. Every note under `docs/design/` must carry a `sutradhar_scar:` in its
  frontmatter naming the finding id(s) that paid for it - each one resolved
  against the round records, any status - or the literal `distribution` plus a
  `sutradhar_scar_argument:` sentence admitting it entered on reach rather than
  an incident. A missing key, an id no record contains, a bare `distribution`,
  and a note the parser cannot read all fail; a notes directory that is absent
  or empty exits 2, because nothing was checked. Every note here already cited
  a scar in its prose *by habit* and one cited nothing at all - which is the
  difference this closes. `TEMPLATE.md` is skipped by name, as the budget gate
  skips it. **Adopters must add the field**: the gate refuses a note without
  it rather than passing over it.

**The guards become tools an agent calls MID-task** (round 13; design note:
[docs/design/mcp-server.md](docs/design/mcp-server.md)). Every guard here
runs in CI, which is to say after the agent has stopped. `mcp_server.py` is
a second placement, not a replacement: a stdlib-only MCP stdio server
exposing nine guards as tools, so an agent can ask `verify_guard` whether
the guard it just wrote actually goes red *while it is still writing it*.

    claude mcp add sutradhar -- python3 /path/to/sutradhar_guards/mcp_server.py

- **Nine tools**, each shelling out to the **real guard CLI** via
  `subprocess` rather than importing it (doctrine 2.3 - an in-process
  adapter can pass while the command a human types fails):
  `verify_guard`, `budget_check`, `obsgate_check`, `obsgate_snapshot`,
  `obsgate_effects`, `rounds_check`, `swallow_lint`, `interpolation_lint`,
  `framework_only`. Each carries a JSON input and output schema and a
  description written for an agent to route on.
- **A red guard is a RESULT, not an error.** The distinction the whole
  design turns on. A guard that RAN returns `isError: false` with its
  verdict in `structuredContent`, green or red, because a red guard is the
  tool working; per the spec `isError: true` means "retry with adjusted
  parameters", and `DECORATION` is not fixed by adjusting parameters. Only
  a guard that could **not run** - missing file, spawn failure, timeout,
  unreadable exit code, bad arguments - is a JSON-RPC error, attributed to
  the `instrument` so it can never be mistaken for a finding about your
  code. Exit codes are partitioned **per tool**, because `verify_guard`'s
  exit 2 is the verdict INCONCLUSIVE while every other guard's exit 2 is a
  usage error.
- **Bounded output.** A tool result goes straight into a model's context
  window, so an uncapped one is the 2.6 unbounded-read class with a more
  expensive consumer. Capped at 65,536 bytes per stream, and truncation is
  **stated** in both the text and the structured content - a partial
  finding list read as a complete one is worse than no list.
- **Dual-era, verified against the specification rather than recalled.**
  The current protocol revision (`2026-07-28`) has **no handshake**:
  version and capabilities ride in every request's `_meta`, and
  `server/discover` replaces `initialize`. The `initialize` handshake is
  legacy (`2025-11-25` and earlier). This server serves both, which the
  spec permits explicitly, and refuses an unknown version with the
  spec-defined `-32022` naming what it does support.
- **`--selfcheck` spawns itself** over real stdio, handshakes in both eras,
  lists every tool, and calls a real guard twice - green and red - to
  confirm the red one comes back as a result. `SUTRADHAR_MCP_GUARD_DIR`
  (for adopters who copied the guards elsewhere) doubles as its falsifier:
  pointed at an empty directory, the selfcheck must go red.

Nine mutations were run against the result. One **survived the first run**:
the test guarding the per-tool exit-code partition read the declaration in
the tool table and never exercised the code that consults it, so collapsing
the partition - which turns every usage error into a pass - left the suite
green. Fixed with two tests that drive the runtime seam, after which no
mutant survived. 44 tests added; the CI path, every guard CLI, every flag
and every exit code are unchanged, and copy-in remains the primary
contract.

**obsgate answers the other half of 6.6** (round 12; design note:
[docs/design/obsgate-depth.md](docs/design/obsgate-depth.md)). The gate could
say whether a surface EXISTS. It could not say whether a change was
witnessed there, which is the half of doctrine 6.6 that decides when a task
is done. Three additions, all depth on the one tool - the existing
invocation (`obsgate --metrics X --floor Y`) and its exit codes are
unchanged, and subcommands extend rather than replace it:

- **`obsgate snapshot --metrics X --out snap.json`** - a deterministic
  digest of a metrics surface: per family, its `# TYPE`, series count,
  sorted label keys, order-independent value sum, and a sha256 over the
  sorted series, plus a whole-surface digest. Two snapshots of an unchanged
  surface are identical apart from `captured_at`. Label values are retained
  only up to a cap, past which the snapshot records that it **stopped
  looking** - a snapshot storing every distinct value would rebuild, inside
  its own file, the cardinality bomb the floor check exists to catch.
- **`obsgate effects --before a.json --after b.json --floor f.json`** -
  doctrine 6.6 as an exit code. The floor manifest gains an optional
  `effects` section with four kinds: `increased` (with counter-RESET
  detection, because a counter that fell restarted rather than declined),
  `appeared` (a family, or a specific label value), `no_vanished_series` (a
  vanished metric is how a deleted instrument reads as zero traffic), and
  `stable_labels` (cardinality-shape drift). Each miss names its
  **direction**; each unanswerable question says so rather than passing. A
  manifest with no `effects` section **refuses and exits 2** - a vacuous 0
  would be a tool certifying an unstated change.
- **`--samples N --interval-ms M`** - byte-identical payloads across every
  scrape, on a surface declaring counters that must move, is **FROZEN**
  (exit 4), a verdict distinct from UNWITNESSED because every metric is
  present and the fix is not "add metrics". A surface with no must-move
  counter is never accused.

Every failure message now names **which of three parties failed**:
`instrument:` (obsgate itself - bad flag, parser raised, its own cap hit),
`endpoint:` (unreachable, empty, non-metrics, frozen, vanished), or `floor:`
(the declaration is not met). A parser crash is caught narrowly, printed
with its exception type, and explicitly disclaimed as evidence about the
endpoint. An HTML error page is now diagnosed as a non-metrics payload
rather than lumped in with an empty 200. Twelve mutations were run against
the new detectors - blinding frozen detection, counter-reset naming,
vanished-family detection, `appeared`'s before-state, label-key drift, the
no-effects refusal, the digest's sort, two party attributions, the label cap,
the non-metrics diagnosis, and the declared latency envelope - and every one
turned the selfcheck or the suite red. 49 tests added.

**Probe bridge hardening - BREAKING for anyone scripting the endpoints**
(round 10; design note: [docs/design/probe-auth.md](docs/design/probe-auth.md)).
An external adversarial review demonstrated that any webpage open in the
developer's browser could fully compromise the loopback bridge:
`access-control-allow-origin: *` made every response readable, preflight-less
POSTs reached handlers, `/probe/poll` let a hostile page impersonate the
probe outright, and `/probe/result` let it answer agent queries with
arbitrary payload shapes - a fabrication hole in exactly the channel whose
contract is "never a fabricated value". Four independent layers now hold it:

- **Shared token required on every endpoint** (`x-sutradhar-probe-token`),
  timing-safe compared, generated at startup and printed if not supplied
  (`--token` / `SUTRADHAR_PROBE_TOKEN` also work). Every curl example,
  the MCP adapter, and the installer carry it. *This changes every probe
  HTTP contract* - hence the breaking marker per the versioning policy.
- **No CORS headers are sent at all** - no legitimate client is a browser;
  cross-origin reads die, and the custom header kills the simple-request
  bypass. A class ratchet (`test_probe_source_guards.py`) fails the build
  if any CORS permission ever reappears in `js/`.
- **Host check**: non-loopback Host headers (DNS rebinding) are a 403.
- **Payload validation**: malformed polls/results are 400s; result
  waiters receive only validated fields, so nothing else can shape what
  the agent reads. Request bodies are capped (413 above 5 MB).
- Installer parses bridge URLs with `new URL()` - the old regex accepted
  `http://127.0.0.1@evil.example`, shipping page state off-machine - and
  refuses to install without the token.

Also fixed en passant, found by writing the failure-path tests: a query
that timed out stayed in the delivery queue forever, to be answered into
the void by the next page that polled. All refusal paths are first-class
selftest cases (25 total), and all three guards were mutation-verified:
disabling the token gate, reintroducing the CORS header, and reverting
the URL parsing each turn a suite red.

**First adoption report, and its fixes** ([#1](https://github.com/sutradharhq/sutradhar/issues/1)).
A repository that is not this one ran the full bootstrap and the gates, and
the kit itself produced the first red:

- `budget.py` no longer reports the shipped `docs/design/TEMPLATE.md` as a
  declared-but-unenforced budget, so a fresh bootstrap's first gate run is
  green instead of a false red. A placeholder id in any *other* note is now
  **refused** rather than skipped - a half-filled copy has numbers no test can
  find, which is the decoration the gate exists to catch. Both directions
  mutation-verified.
- `bootstrap.sh --layers python,frontend,probe,ci,agent,docs` (default: all).
  A backend-only repo no longer receives a cypress suite it will never run and
  a CI job that fails on a missing JS lockfile. An unknown layer is refused,
  never ignored. This is the deferred v0.3 roadmap item, unblocked by field
  evidence rather than guessed demand.
- The python layer now creates `docs/rounds/`, so the CI template's
  `rounds --check` has a directory to read on an adopter's first push.

## v0.4.0 - 2026-08-18

**Public release.** Sutradhar is now open source. Added the community surface a
copy-in framework needs: `CONTRIBUTING.md`, `SECURITY.md` (the zero-dependency,
nothing-to-install supply-chain posture stated as a feature), issue templates -
including an *adoption report*, because field evidence from a codebase that is
not ours is the framework's binding constraint (doctrine 8.4) - a PR template
that is the doctrine's own checklist, and
[docs/design/scope-framework-only.md](docs/design/scope-framework-only.md)
stating the framework/product line the gate already enforces. Rounds 6-8 (the
outside-evidence cross-read, the multi-thread survey, and the deletion pass)
land in this release; contributing repositories are referred to anonymously.

**Framework, not a product - and now a gate says so.** The DOCTRINE preamble
and README state the commitment plainly: Sutradhar is a copy-in framework with
no runtime and nothing to install, not a product-harness. Because a promise in
prose is one this framework tells you not to trust, it is enforced.

- New tool `framework_only.py`: fails the build if any shipped guard in
  `sutradhar_guards/` imports outside the standard library, or if a dependency
  manifest (`requirements.txt`, `pyproject.toml`, `package.json`, a lockfile)
  appears anywhere in the framework surface but `examples/`. Top-level imports
  only - a lazy `import` inside a function is the deferred-integration escape
  hatch (envgate carries pytest exactly this way), and the gate found that
  distinction by flagging envgate on its first run against the real tree.
- Wired into the repo's own `selftest.yml` (its selfcheck, the real check
  against this tree, and the 3.9 lane) - the framework holds itself to the
  line it draws. Selfcheck mutation-verified three ways; stdlib-only, so the
  gate passes its own check.

**Doctrine 6.6: observability is a provenance gate.** The "Observability
floor" prose in docs/operations.md is now a numbered rule, and it is
mechanised. The line it draws, in the maintainer's words: every task
becomes verifiable - a change to a running system is done when its effect
is witnessable at a runtime surface, and a claim no surface witnessed does
not leave the building. Promoted on two recorded incidents (rounds 3 and
4), which is the 8.1 bar; see docs/rounds/round-005.md.

- New tool `obsgate.py`: takes a declared floor (JSON manifest) and a
  metrics payload (Prometheus text, file or endpoint) and answers
  WITNESSED / UNWITNESSED / INCONCLUSIVE. An empty payload FAILS - "no
  data" and "all zero" must never read the same (2.4) - and an unreachable
  endpoint is INCONCLUSIVE, never a pass. Cardinality caps mechanise the
  route-template-never-raw-path line. Stdlib-only, copy-in, exit codes
  0/1/2/3.
- Selfcheck mutation-verified five ways; the first run survived a blinded
  empty-payload branch by refusing for the wrong reason, so the selfcheck
  now asserts the diagnosis, not just the verdict.
- Wired into CI (both Python versions), bootstrap.sh, and the reachability
  ratchet covered it automatically on the day it landed - which was the
  point of building that ratchet as a class invariant.


**Every tool's `--selfcheck` is now reachable, and its exit code means
something.** Five of ten modules (`ratchet`, `envgate`, `claim_check`,
`golden`, `detectors`) had no `__main__` block at all: `python -m
sutradhar_guards.envgate --selfcheck` ignored the flag, imported the module
and exited 0. A weekly review read those zeros as passing checks. Found by
the review routine's first run; see docs/rounds/round-004.md.

- Those five modules gain a CLI and a real `selfcheck()`, each exercising the
  behaviour the module would be worthless without - `golden` refuses an
  unreasoned re-baseline, `ratchet` refuses an unbanked improvement,
  `envgate` refuses an audit over an empty corpus, `detectors` demands its
  planted known-bad inputs are found.
- **Unknown flags now exit 2** in `budget`, `rounds`, `swallow_lint` and
  `interpolation_lint`. They previously skipped anything starting with `--`,
  so a typo such as `--selfchek` ran the default scan and exited 0. The first
  thing this caught was a malformed command in the reviewer's own health
  script.
- **Every selfcheck reports on success.** Seven of eight passed silently; a
  check that prints nothing cannot be distinguished from one that never ran.
- `__init__` resolves exports lazily (PEP 562). Eager submodule imports made
  `python -m` emit a `RuntimeWarning` on every CLI run of six tools. The
  public API is unchanged and `budget` still resolves to the submodule.
- New class ratchet `python/tests/test_selfcheck_reachability.py` walks every
  module in the package and asserts, for each: `--selfcheck` exits 0 and
  names itself, an unknown flag exits non-zero, and no `RuntimeWarning` is
  emitted. Shown red before the fixes (25 failed), green after (31 passed),
  and mutation-verified by deleting `golden`'s `__main__`.

## v0.3.0 - 2026-08-08

The theme: move rules out of memory and into mechanism. v0.2 made the
guards guard themselves; v0.3 makes the doctrine guard itself. Every rule
that lives only in prose is a rule that gets dropped under deadline
pressure.

Four of seven planned items shipped. The release closes there deliberately,
on doctrine 8.3: the marginal value of another tool fell below the value of
one outside reader, and everything here has been validated against a single
codebase by a single reviewer. See docs/rounds/round-002.md for the stop
decision, including where the flight recorder disagrees and why that is not
a contradiction.

Added:
- **`verify_guard.py`**: doctrine 2.2 as a command. Checks the fix commit
  out into a throwaway worktree, confirms the guard is green there, reverts
  only the production half (tests and prose kept), and requires the guard
  to go red. Tri-state exit code - 0 `VERIFIED`, 1 `DECORATION`, 2
  `INCONCLUSIVE` - so "I could not tell" is never reported as a pass.
  Stack-agnostic: the guard command is yours (`pytest`, `go test`, `npm
  test`). Grades a red as weak when the guard failed to LOAD rather than
  to assert; warns when `--guard-cmd` contains a pipe that would swallow
  `$?` (doctrine 6.3); refuses merge commits and commits with no
  executable change. Wired into `bootstrap.sh`, `ci/guards.yml`, and this
  repo's own CI.

- **`budget.py`**: doctrine 1.1 as a gate. Cardinalities and envelopes live
  in the design note's frontmatter; the test reads its N from there
  (`with budget("fleet-sweep") as b: ... b.n ...`) so nobody hand-picks a
  comfortable size, and the CLI fails the build on any declared number no
  test enforces. The gate is deliberately NOT "did you write a note" -
  that measures paperwork - but "is every number you wrote down binding".
  Stdlib-only strict frontmatter parser that refuses what it would have to
  guess at; `tracemalloc` for the memory envelope with its limits stated
  (Python heap, not RSS); `ci_slack` declared in the file so widening a
  ceiling stays visible in the diff. The repo now carries its own budget
  (`docs/design/lint-scan.md`) enforced in its own CI.

- **`rounds.py`** (the flight recorder): makes doctrine 8.1 and 8.3
  computable instead of felt. Reads the round records the robustness-loop
  skill already asks for - prose plus one machine-readable findings table -
  and answers three questions nothing could answer before: the stop rule
  (CONTINUE / REST / INSUFFICIENT, using the loop's own exit criterion of
  two consecutive zero-HIGH rounds), the residual register (derived from
  open deferrals rather than maintained by hand), and rule attribution
  (which doctrine rules can cite a save). It **refuses** to name deletion
  candidates on fewer than five rounds - 8.1 asks for months of silence,
  not a quiet week - and labels findings RECORDED versus floors MEASURED so
  a logbook is never presented as telemetry (doctrine 5.1). `--check` is
  the gate half: a mistyped rule id silently loses an attribution, so CI
  fails on one. The skill now ships the format it had always asked for.

- **`examples/`**: a worked repo with seven planted defects and a green
  test suite, plus `run-the-guards.sh` - ten seconds, no install, and the
  guards surface every one of them. The pedagogy is the passing suite: the
  defects live in a codebase whose own tests are green, which is the state
  most codebases are in. The example is itself under guard (the runner
  exits nonzero on any missed defect, and CI runs it), because a
  walkthrough that has quietly stopped demonstrating fails in front of
  exactly the person you least want it to. Frontend guards and drills are
  deliberately excluded and the README says why, rather than turning a
  ten-second demo into a five-minute install.

Fixed (found by this release's own tests - recorded per doctrine 8.1):
- the flight recorder's round-heading regex lacked `re.MULTILINE`, so
  `.search()` over a whole document never matched and NO round record was
  ever parsed. Its own selfcheck caught it on the first run.
- the budget gate's parser strictness had no selfcheck behind it: mutation
  testing showed that blinding the parser's refusal branch passed every
  other planted case, so a malformed design note would have been read as
  "no budget declared" - an unenforced number reporting as compliant. The
  selfcheck grew four malformed-note cases.
- `__init__` re-exported the `budget` context manager from the `budget`
  module, so `sutradhar_guards.budget` meant the function or the submodule
  depending on import order. test_budget.py passed alone and five of its
  tests failed in the full suite. Fixed by not re-exporting it, and guarded
  by a CLASS ratchet that walks every submodule
  (`test_no_export_shadows_a_submodule`) rather than pinning the instance.
- the budget selfcheck CRASHED rather than returning False when blinded,
  so the CLI answered with a traceback instead of a verdict. A selfcheck
  that dies is a selfcheck that failed, and now says so (doctrine 2.4).
- verify-guard's first selfcheck run reported `DECORATION` for a docs-only
  commit: prose was classified as production code, so reverting a README
  and finding the guard still green read as a dead guard. A false
  accusation is the worst failure mode for this tool - a net that cries
  wolf gets muted. Fixed with a third file class (inert prose/media, with
  `requirements*.txt` explicitly carved out as real code), and a commit
  whose whole non-test half is inert now returns `INCONCLUSIVE`.
- the guard-collision warning fired on bare substrings, so `golden.py`
  was reported as possibly-the-guard for a command naming
  `test_claim_check_golden.py`. Now matched on a token boundary.

## v0.2.0 - 2026-08-03

The runtime probe, the numeric-truth toolkit, and the repo held to its own
doctrine (this release closes an external review's four findings:
versioning, provenance, CI, selfcheck wiring).

Added:
- **Runtime probe** (`js/probe/`): inner-loop verification for running
  apps - browser probe (plain ESM, zero deps) + local bridge
  (`node:http`, binds 127.0.0.1, curl-able by any agent) + MCP stdio
  adapter + `selftest.mjs` driving the real `ProbeCore` against the real
  bridge, failure paths as first-class cases. The selftest caught a
  contract bug (`connected: null` vs `false`) on its first run.
- **`claim_check.py`**: ground every number in generated text against
  witnessed values; unit-gated matching, empty-witness-set flags
  everything, currency/lakh/crore shorthand.
- **`golden.py`**: golden-dataset gate with in-file declared tolerance and
  a re-baseline that REQUIRES a reason (`GOLDEN_REASON`), recorded in the
  file so the diff carries the why.
- **`detectors.py`**: ready-made ratchet detectors - relative-import
  integrity (module and name level) and unbounded ORDER BY.
- **Selfcheck wiring tests** (`test_detectors_and_wiring.py`): blind each
  lint's detector and assert the CLI exits nonzero - the path from
  "detector went vacuous" to "CI goes red" is itself under test.
- **CI on this repo** (`.github/workflows/selftest.yml`): pytest, lint
  selfchecks, probe selftest, TS syntax. The guards guard themselves.
- `docs/ai-llm.md` playbook; `docs/templates/design-note.md` (the
  prevention discipline as a fillable template).
- Provenance statement in the README for the repo's own claims.

- **`rounds.py`** (the flight recorder): makes doctrine 8.1 and 8.3
  computable instead of felt. Reads the round records the robustness-loop
  skill already asks for - prose plus one machine-readable findings table -
  and answers three questions nothing could answer before: the stop rule
  (CONTINUE / REST / INSUFFICIENT, using the loop's own exit criterion of
  two consecutive zero-HIGH rounds), the residual register (derived from
  open deferrals rather than maintained by hand), and rule attribution
  (which doctrine rules can cite a save). It **refuses** to name deletion
  candidates on fewer than five rounds - 8.1 asks for months of silence,
  not a quiet week - and labels findings RECORDED versus floors MEASURED so
  a logbook is never presented as telemetry (doctrine 5.1). `--check` is
  the gate half: a mistyped rule id silently loses an attribution, so CI
  fails on one. The skill now ships the format it had always asked for.

- **`examples/`**: a worked repo with seven planted defects and a green
  test suite, plus `run-the-guards.sh` - ten seconds, no install, and the
  guards surface every one of them. The pedagogy is the passing suite: the
  defects live in a codebase whose own tests are green, which is the state
  most codebases are in. The example is itself under guard (the runner
  exits nonzero on any missed defect, and CI runs it), because a
  walkthrough that has quietly stopped demonstrating fails in front of
  exactly the person you least want it to. Frontend guards and drills are
  deliberately excluded and the README says why, rather than turning a
  ten-second demo into a five-minute install.

Fixed (found by this release's own tests - recorded per doctrine 8.1):
- the flight recorder's round-heading regex lacked `re.MULTILINE`, so
  `.search()` over a whole document never matched and NO round record was
  ever parsed. Its own selfcheck caught it on the first run.
- probe bridge reported `connected: null` instead of `false` before any
  probe ever connected;
- claim-check number regex split "2026" into "202" + "6" (grouping
  alternative too greedy) and let a stopword defeat the bare-year filter;
- ORDER BY detector double-counted f-strings (JoinedStr and its child
  constants both visited).

## v0.1.0 - 2026-08-03

Initial release: DOCTRINE.md (8 sections, every rule with its scar), five
playbooks, Python guard toolkit (swallow lint, interpolation lint, Ratchet
library, envgate), Cypress behavioral guards (`expectEffect`,
`overprintsIn`, route sweep), CI template, agent operating rules, the
robustness-loop and ops-drill skills, `bootstrap.sh`.
