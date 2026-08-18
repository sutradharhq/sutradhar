# Sutradhar and DeepSeek Harness: different layers

People ask how Sutradhar relates to [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)
(dsh), which arrived in August 2026 to a very large reception. Short answer:
**they are different layers, and they compose.** dsh is an agent *runtime*;
Sutradhar is agent-agnostic engineering *discipline*. You can run Sutradhar's
guards over a codebase an agent built with dsh, with Claude Code, with Cursor,
or by hand — it does not care which agent wrote the code.

## What each one is

| | DeepSeek Harness | Sutradhar |
|---|---|---|
| Kind | A product: an agent runtime you install and run (`npx @deepseek-ai/dsh`), plugin-based, with a web UI | A framework: a doctrine plus copy-in, stdlib-only guards. Nothing to install; you copy files into your repo |
| Answers | "How does the agent *do* the work?" | "How do I know the work the agent did is *correct*?" |
| Runs | as a service | in your CI, over your code |
| Dependency posture | a full runtime and its dependencies | zero dependencies, enforced by a gate |

If dsh is the workshop the agent works in, Sutradhar is the inspection regime
the output has to pass. Neither replaces the other.

## Where Sutradhar adds something a runtime doesn't

An agent runtime's job is to *produce* changes; it is not, and does not try to
be, the discipline that keeps a growing codebase honest. Those are the four
things Sutradhar is built around, and they are worth naming because they are
the expensive lessons:

- **Cardinalities and budgets stated at design time** — every feature names the
  N it must survive and its latency/memory envelope, as numbers a test enforces.
- **Operational drills** — restore-reconciliation, cold-start, soak — because
  almost every serious defect is found by *operating* a system, not by reading
  it.
- **Grounding and evals on model-backed features** — a generated number is
  traceable to a computed value or refuses cleanly; every prompt surface gets a
  frozen eval run as a regression gate.
- **A stop rule and rule-attribution** — a flight recorder that says when a
  hardening loop has run dry and which rules ever caught anything, so the
  discipline itself does not just accrete.

A read of the public dsh repository in August 2026 did not find these as
first-class concerns — which is expected, because a runtime is a different kind
of thing. (dsh moves fast; treat that as a snapshot, not a scorecard. If it has
grown these since, this page is out of date and we would rather know.)

## The honest symmetry

dsh's own engineering discipline is, independently, very strong — hundreds of
decision records, exhaustive per-package invariants, coverage and duplication
gates. Reading it was the best outside evidence Sutradhar has had: a team that
had never seen this framework converged on several of its load-bearing rules
(prove a guard can fail; test the published artifact; never swallow an
exception; ground what the model emits). Convergence from an independent, much
larger effort is the strongest signal we have that these rules are not just
ours. The full write-up is in this repo's round records (`docs/rounds/`).

## Which should you use?

Both, if they fit. Pick an agent runtime for how work gets done. Adopt
Sutradhar for whether you can trust it afterward — with any agent, or none.
