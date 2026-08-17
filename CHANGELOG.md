# Changelog

Versioning: semver on the toolkit's file contracts (CLI flags, library
APIs, baseline file formats, probe HTTP endpoints). Docs and doctrine
evolve freely within a minor version. Tags mark releases; copy-in users
upgrade by diffing against the tag they took.

## Unreleased

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
