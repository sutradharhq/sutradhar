# Adoption guide

How to roll Sutradhar onto a project. The framework is copy-in by design:
no package to install, no version to chase, every file yours to edit. Run
`bootstrap.sh <target-repo>` or copy pieces by hand.

## New project (greenfield)

Adopt everything on day one; it is nearly free when there is nothing to
baseline.

1. Append [agent/AGENTS.md](../agent/AGENTS.md) to your agent rules file
   (`CLAUDE.md`, `AGENTS.md`, editor rules).
2. Copy the Python guards into `scripts/`, run each with
   `--update-baseline` (the baselines will be empty), and wire
   [ci/guards.yml](../ci/guards.yml).
3. Copy `uiGuards.ts` into `cypress/support/`, configure it, and commit the
   route sweep with your first route.
4. Start the habits that cannot be retrofitted cheaply:
   - testids on every component at build time;
   - cardinalities and budgets in every design note;
   - a guard in the same commit as every fix.

## Existing project (brownfield)

Do NOT attempt a big-bang cleanup. The ratchet mechanic exists precisely so
you can adopt on a codebase with hundreds of existing violations and still
never regress from today.

**Week 1: freeze the floor.**

```bash
python scripts/swallow_lint.py src/ --update-baseline
python scripts/interpolation_lint.py src/ --keywords sql
```

The swallow baseline records today's count per file; CI now fails only on
NEW swallows. The interpolation lint usually starts clean or near-clean;
fix the handful it finds rather than baselining them (they are injection
shapes).

**Week 2: the route sweep.** One spec, immediate breadth over every route.
Expect it to find something on the first run; ours did.

**Week 3: audit your skip gates.** Wire
`sutradhar_guards.envgate.audit_skip_gates` over your CI configs. If you
have env-gated test tiers, there is a real chance some of them run
nowhere. Ours had ~86 tests, including the billing arithmetic, running in
no environment while the suite reported green.

**Ongoing: ratchet as you touch.**

- Every fix gets a guard in the same commit; prefer extending a ratchet.
- Every control you touch gets an `expectEffect`.
- Every improvement banks its baseline (`RATCHET_UPDATE=1`, or
  `--update-baseline`); the floors only drop.
- Schedule the [robustness loop](../agent/skills/robustness-loop.md)
  (weekly at first) and the [ops drills](../agent/skills/ops-drill.md)
  (before first deploy, then per release).

## What to customize

Everything, but especially:

- `AGENTS.md` rule 11 (staging) if you use a different VCS workflow.
- The `ignoredConsole` list and error-boundary copy in `uiGuards.ts`.
- The keyword preset and safe-call names in `interpolation_lint.py` for
  your query dialect and escaping helpers.
- The lens list in the robustness loop for your domain's defect classes
  (billing arithmetic, authz, ingestion seams - whatever carries your
  money and your trust).

## What NOT to do

- Do not baseline the interpolation lint's findings to get to green; fix
  them. The pattern is the hole.
- Do not let the console ignore list grow without per-entry reasons.
- Do not measure adoption by test count. Measure by: floors shrinking,
  route sweep green, effect assertions on new controls, drills run.
- Do not skip mutation-verification because the guard "obviously works".
  The tested-but-half-dead fix on our record was obvious too.
