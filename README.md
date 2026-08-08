# Sutradhar

**An engineering harness for AI coding agents.**

Sutradhar (सूत्रधार) is the stage director in Sanskrit theatre, the one who
holds the threads. That is what this framework does: it holds the threads of
an agent-built codebase so the play stays coherent while many hands, human
and machine, work on it at once.

It is a complete harness: backend, frontend, operations, and the agent
workflow itself. Every rule in it was paid for by a real defect on a real
production-bound codebase. None of it is aspiration.

## Why this exists

We built a data-heavy platform with AI agents over hundreds of sessions:
25+ adversarial robustness rounds, operational drills, scale passes to 200k
entities, and a parallel multi-session workflow. The record taught us three
things:

1. **Almost every serious defect was found by operating the system or
   asserting on its runtime state, not by reading code.** The backup that
   restored zero rows, the tenant fix that was half dead for a week while its
   tests passed, the query that walked an entire table when a tenant had no
   data. All invisible to review.
2. **Class invariants beat point tests by an order of magnitude.** ~37
   ratchet tests (2.5% of our suite) produced two thirds of all test-driven
   discoveries. ~1,400 per-defect point tests produced three.
3. **Most expensive defects could have been prevented by one design-time
   sentence.** "This must survive 200,000 rows" costs nothing to write and
   everything to skip.

Tools like [Reticle](https://github.com/reticlehq/reticle) proved the value
of the inner loop: let the agent assert on the running app's state instead
of eyeballing screenshots. Sutradhar takes that idea and completes the
picture. The inner loop is one of three loops, and a harness that only has
one of them leaks defects through the other two.

## The three loops

| Loop | Question | Sutradhar gives you |
|---|---|---|
| **Inner** (while building) | Is what I just wrote actually working, right now? | **The runtime probe** ([js/probe/](js/probe/)): a zero-dependency bridge that lets any agent with `curl` assert on the running app's console, network, and live state (MCP adapter included) - plus the discipline docs. [docs/frontend.md](docs/frontend.md), [docs/backend.md](docs/backend.md) |
| **Outer** (regression gate) | Does everything still work after every future change? | Behavioral UI guards (effect assertions, error-boundary and console sweeps, paint-defect detection), Python lint ratchets, class-invariant test helpers, CI templates. [js/](js/), [python/](python/), [ci/](ci/) |
| **Meta** (the process) | Is the way we work producing correct software? | The doctrine, plus the tool that enforces its hardest rule: `verify_guard.py` reverts your fix and requires the guard to go red. [DOCTRINE.md](DOCTRINE.md), [agent/](agent/) |

## What is in the box

```
sutradhar/
├── DOCTRINE.md              The full rule set, each rule with the failure that earned it
├── CHANGELOG.md             Versioned releases (semver on the file contracts)
├── docs/
│   ├── adoption.md          Rolling this onto a new or existing project
│   ├── backend.md           Backend playbook: ratchets, honest degradation, scale discipline
│   ├── frontend.md          The two-loop frontend playbook
│   ├── ai-llm.md            Grounding, claim checking, evals, replay anchors
│   ├── operations.md        Drills, exit-code discipline, verifying the null
│   ├── roadmap-v0.3.md      What is shipping in v0.3, and what was deferred
│   ├── design/
│   │   └── lint-scan.md     This repo's own budget - a filled-in design note
│   ├── multi-agent.md       Running many agents/sessions on one codebase without carnage
│   └── templates/
│       └── design-note.md   The prevention discipline as a fillable template
├── python/
│   ├── sutradhar_guards/
│   │   ├── budget.py              Design-time cardinalities that tests must enforce
│   │   ├── verify_guard.py        Proves a guard can fail: reverts the fix, demands red
│   │   ├── swallow_lint.py        AST-based silent-exception-swallow ratchet
│   │   ├── interpolation_lint.py  Query-string injection guard (SQL, SPARQL, any DSL)
│   │   ├── ratchet.py             Library for writing shrink-only class-invariant tests
│   │   ├── envgate.py             Pytest env-gating that audits its own skip gates
│   │   ├── claim_check.py         Ground every number in LLM-generated text
│   │   ├── golden.py              Golden-dataset gate with reasoned re-baseline
│   │   └── detectors.py           Ready-made ratchet detectors (imports, ORDER BY)
│   └── tests/                     The guards' own tests, red cases and selfcheck wiring included
├── js/
│   ├── cypress/
│   │   ├── uiGuards.ts            Behavioral UI invariants: effect assertions, overprint detection
│   │   └── routeSweep.example.cy.ts
│   └── probe/
│       ├── core.mjs               The probe logic (runs in browser AND in the selftest)
│       ├── browser.mjs            Dev-only installer: console + fetch capture, state getters
│       ├── server.mjs             Local bridge, zero deps, curl-able by any agent
│       ├── mcp.mjs                Optional MCP stdio adapter (also zero deps)
│       └── selftest.mjs           Real core vs real bridge, failure paths first-class
├── ci/
│   └── guards.yml           GitHub Actions template wiring all guards into CI
├── .github/workflows/
│   └── selftest.yml         This repo's own CI - the guards guard themselves
├── agent/
│   ├── AGENTS.md            Drop-in operating rules for any coding agent (CLAUDE.md compatible)
│   └── skills/
│       ├── robustness-loop.md     A repeatable adversarial depth sweep
│       └── ops-drill.md           Operate the system, don't read it
└── bootstrap.sh             Copies the pieces into your repo
```

## Who is this for

Anyone building any application with (or without) coding agents. The
layers have different reach, stated honestly:

- **Stack-agnostic** (any language, any framework): the doctrine, the
  five playbooks, the agent operating rules, the two skills, the design
  templates, the CI shape. This is most of the value.
- **Any Python codebase**: the guard toolkit (stdlib only, Python 3.9+,
  framework-free). The ratchet PATTERN ports to any language in an
  afternoon; the shipped detectors are Python.
- **Any git repository, any language**: `verify_guard.py`. It needs Python
  to *run*, not to verify - the guard command is yours (`go test ./...`,
  `npm test`, `cargo test`), so it works on any stack with commits and a
  test command.
- **Any browser app**: the runtime probe (plain ESM, bundler-agnostic,
  zero deps; the agent side is just curl).
- **Cypress projects**: `uiGuards.ts` as shipped. The guards are small
  and DOM-level, so porting to Playwright is mostly mechanical; the
  route-sweep and effect-assertion patterns carry over unchanged.

Nothing assumes our domain, our stack, or any particular agent product.

## Quickstart

```bash
git clone https://github.com/sutradharhq/sutradhar.git
cd your-project
bash ../sutradhar/bootstrap.sh .
```

Then:

1. **Give your agent the rules.** Append `agent/AGENTS.md` to your project's
   `CLAUDE.md` / `AGENTS.md` / rules file, or keep it as its own file and
   reference it.
2. **Turn on the Python guards** (any Python backend):
   ```bash
   python scripts/swallow_lint.py src/ --update-baseline   # record today's floor
   python scripts/swallow_lint.py src/                     # gate: only shrinks from here
   python scripts/interpolation_lint.py src/ --keywords sql
   ```
3. **Turn on the UI guards** (any Cypress project): import
   `cypress/support/uiGuards.ts`, add the route sweep, and give every new
   interactive control an `expectEffect` assertion.
4. **Wire CI** from `ci/guards.yml`.
5. **Schedule the loops.** The robustness loop and the ops drill in
   `agent/skills/` are designed to be handed to an agent verbatim as
   recurring work.

Everything is copy-in, dependency-free, and yours to edit. There is no
package to install and no version to chase. The guards are plain Python
stdlib and plain TypeScript.

## The ideas that carry the weight

**Ratchets, not accumulation.** A fix ships with a guard over the whole
*class* of defect, not a pin on the instance. The guard keeps a frozen
allowlist of current violations that may only shrink; fixing one without
removing its entry fails the build, so the floor drops monotonically and the
codebase cannot quietly regrow the class. `python/sutradhar_guards/ratchet.py`
makes this a five-line test.

**Guards must be shown to fail.** A guard that has never been red is
decoration. Revert the fix: the test must go red. Weaken the seam: the
behavioral cases must go red. Our worst week shipped a tested-and-half-dead
fix precisely because its tests set internal state by hand instead of
exercising the real seam. Every guard in this repo ships with a self-check
that plants a known-bad case and requires the detector to catch it, so the
guard cannot pass vacuously.

That rule used to live on the honour system, which is the same as not
having it. Now it is a command:

```bash
python scripts/verify_guard.py --guard-cmd "pytest tests/test_tenant_scope.py"
```

It reverts the production half of your fix commit in a throwaway worktree,
keeps the tests, and reruns them. Exit 0 `VERIFIED`, exit 1 `DECORATION`,
exit 2 `INCONCLUSIVE` - and inconclusive is never reported as a pass. The
tool is held to its own rule: its selfcheck builds a real guard and a
deliberately decorative one and fails unless it tells them apart.

**Honest degradation.** A failure states itself. No silent fallbacks, no
fabricated values, no `"ok"` wrapping an error, no empty list that reads as
"there is genuinely nothing here" when the truth is "the read failed".
The swallow lint is the mechanical edge of this rule.

**Effects, not existence.** A UI control that renders is not a UI control
that works. `expectEffect` snapshots the observable world (URL, DOM text,
persisted state), runs the interaction, and fails if nothing moved. The
control-that-does-nothing class ships constantly under suites that only
assert rendering.

**Drills outrank review.** Cold-start from the docs alone, restore a backup
and reconcile the counts, soak unattended, upgrade in place. Every one of
these found defects that no amount of code reading did.

**State cardinalities before building.** Every feature names the N it must
survive and its latency/memory envelope as numbers, at design time. This is
the cheapest rule in the framework and the one whose absence cost us the
most, so it is not left to good intentions: the numbers go in the design
note's frontmatter, the test reads its N from there rather than picking a
comfortable one, and the gate fails on any declared number no test enforces.

```python
def test_fleet_sweep_at_design_scale():
    with budget("fleet-sweep") as b:      # n, p95, memory from the design note
        sweep(synth_meters(b.n))          # b.n IS the declared 200,000
```

Raising the design figure automatically makes the test harder. Lowering it
is a visible diff in the note, which is exactly where that argument belongs
- rather than a quietly weakened number in a test file nobody reads.

## Relationship to Reticle

[Reticle](https://github.com/reticlehq/reticle) is a dev-only MCP tool for
runtime-state assertions in the frontend inner loop, and it is good at that.
Sutradhar is not a fork or a competitor at that layer; use any
runtime-observation tool you like inside the inner loop (browser MCP
tooling, CDP, Reticle itself). What Sutradhar adds is everything around it:
the outer regression loop, the backend equivalents, the operational drills,
the multi-agent workflow, and the doctrine that ties it together. The
frontend playbook explains exactly where an inner-loop tool slots in.

## Provenance of this repo's own claims

Practicing what we preach (doctrine 5.1): the statistics quoted here
("~37 ratchet tests produced two thirds of test-driven discoveries",
"~1,400 point tests produced three", "five UI defects found by a human,
zero by the suite") are **measured from one production build record** -
ours: a production platform, 25+ robustness rounds, ~1,500
tests, built largely by agents over hundreds of sessions. They are honest
counts, not a controlled study, and one codebase is a sample size of one.
The *scar stories* in DOCTRINE.md are real incidents, genericized only
enough to remove domain detail. Treat the numbers as strong evidence from
a single deployment, and expect your ratios to differ; the doctrine's own
rule 8.1 says to keep only what your record confirms.

## Versioning

Semver on the file contracts (CLI flags, library APIs, baseline formats,
probe endpoints), tagged releases, history in [CHANGELOG.md](CHANGELOG.md).
Copy-in users upgrade by diffing against the tag they took.

## License

Apache-2.0. Use it, fork it, sell with it. If it saves you from shipping a
silent zero, we are even.
