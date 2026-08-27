# Sutradhar operating rules (condensed)

Append to your `CLAUDE.md` / `AGENTS.md` / rules file. Every rule was earned
by a real defect; the number in brackets points at that rule in DOCTRINE.md,
where the scar that paid for it is written down. This is the short form -
the full operating rules are in `agent/AGENTS.md`.

## Before writing code

- **Name N and the envelope.** [1.1] State the rows, users, or requests per
  second the feature must survive and its latency/memory budget, as numbers,
  before implementing. Put them where a test can read them, not in the PR
  description where nothing can. A design that cannot name N is not designed.
- **Write the failure story.** [1.4] For every dependency touched: what does
  the user see when it is down, slow, or partial? If the answer is "the same
  as success", the design is not done.
- **Prefer the seam to the guard.** [1.2] If a type or constructor can make
  the bug unrepresentable, do that instead of adding a test that catches it.
- **Orient before starting.** [7.1, 7.2] Read the owning plan, then check its
  claims against the tree. Trust the tree, not the doc.

## While building

- **Exceptions are never silently swallowed.** [2.7] Every `except` logs,
  degrades explicitly, or re-raises. A bare handler returning an empty value
  converts an outage into a lie that downstream code reads as real data.
- **Honest degradation: a failure states itself.** [2.4] No silent fallbacks,
  no fabricated values, no `"ok"` wrapping an error list. A partial result
  carries a flag the caller must see. Confirm a delete, erasure, or send only
  when every layer verifiably succeeded.
- **Unbounded reads are bugs.** [2.6] Any query or sweep over a collection
  that grows with usage carries a cap and an honest too-large refusal.
- **Never interpolate into a query language.** [2.8] The pattern is the hole
  even when today's value is safe.
- **Test through the real seam.** [2.3] The route, the transport, the public
  function - never internals the production path does not use.
- **Assert on runtime state, not appearance.** [3.3] Read the actual response,
  the actual row, the actual console. Pixels and green-looking output lie in
  both directions.

## Frontend

- **Effects, not existence.** [3.1] Every interactive control must change URL,
  DOM, or persisted state, and a test must assert that it did. A control that
  renders is not a control that works.
- **Baseline every route.** [3.2] Per route and role: it lands (not bounced to
  login), no error boundary, no meaningful console errors, non-empty body.
- **Counting selectors measures nothing.** [3.6] A testid can exist and be
  unreachable; a spec can pass vacuously. Measure reachability and effect.

## Before committing

- **Every fix ships with a guard in the same commit.** [2.1] Prefer a class
  ratchet - an invariant that walks the code by AST, route table, or schema
  and fails on every current and future sibling - over a point test.
- **Show the guard fail.** [2.2] Revert the fix: the test must go red. A guard
  never shown to fail is decoration. Run that experiment; do not claim it.
- **Freeze numeric truth.** [2.5] Re-baseline a golden set only deliberately,
  in the same commit as the intentional change, with the reason in the message.
- **Stage named files only.** [7.3] Never `git add -A` on a shared tree.

## When reporting

- **An exit code is evidence only in pairs.** [6.3, 6.6] It is a claim about a
  process, not about a check: a known-good input must exit 0 AND a known-bad
  input must exit non-zero before a check counts as green. `--selfcheck` on a
  tool with no argument parser exits 0 because the import succeeded, and reads
  exactly like a pass. Never pipe a build or test through anything that
  swallows `$?`; a truncated run reports as truncated.
- **A change is done when its effect is witnessed at a runtime surface** [6.6]
  - a metric, a log line, a queryable row - not when the deploy exited 0. A
  surface that cannot report must say so: an endpoint degrading to an empty
  200 turns "no data" into "all zero", and every number read from it
  afterward is fabricated with extra steps.
- **Refute the null before filing a finding.** [6.4] Prove the test itself is
  valid first. A false finding costs more trust than no finding.
- **Every number carries its provenance.** [5.1] Measured, estimated with
  stated assumptions, or illustrative - in the artifact, not in your head.

## If the feature is model-backed

- **The model phrases; it never invents.** [4.1] Every generated number traces
  to a computed value or is flagged unverifiable - mechanically, not by prompt.
- **Schema-validate every structured output** [4.3] with bounded corrective
  retries. A model response is untrusted input.

## Stop rule

- **Stop when the marginal round yields less than the next cheapest
  activity.** [8.3] Hardening, polishing, and testing are all budgets.

---

Condensed from the Sutradhar doctrine. Full operating rules: `agent/AGENTS.md`.
The scar behind each number: `DOCTRINE.md`.
Source: https://github.com/sutradharhq/sutradhar
