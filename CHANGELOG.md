# Changelog

Versioning: semver on the toolkit's file contracts (CLI flags, library
APIs, baseline file formats, probe HTTP endpoints). Docs and doctrine
evolve freely within a minor version. Tags mark releases; copy-in users
upgrade by diffing against the tag they took.

## Unreleased (v0.3.0)

The theme: move rules out of memory and into mechanism. v0.2 made the
guards guard themselves; v0.3 makes the doctrine guard itself. Every rule
that lives only in prose is a rule that gets dropped under deadline
pressure.

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

Fixed (found by this release's own tests - recorded per doctrine 8.1):
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

Fixed (found by this release's own tests - recorded per doctrine 8.1):
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
