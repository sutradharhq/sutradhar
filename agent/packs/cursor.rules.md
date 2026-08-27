<!-- Put this file at your repo root as `.cursorrules`, or under
     `.cursor/rules/sutradhar.mdc` (add Cursor's `---` frontmatter there,
     e.g. `description:` and `alwaysApply: true`, above the first heading). -->

# Sutradhar engineering rules

Follow these on every change to this repository. Each rule was earned by a
real defect; the number in brackets is that rule in the Sutradhar doctrine,
where the incident that paid for it is recorded.

## Design before implementation

- [1.1] State the N this must survive - rows, users, requests per second -
  and its latency/memory envelope, as numbers, before writing code. Put them
  where a test can read them. If you cannot name N, find out first.
- [1.4] Write the failure story for every dependency touched: what does the
  user see when it is down, slow, or partial? "Same as success" means the
  design is not finished.
- [1.2] When a bug can be prevented by a type or constructor that cannot
  express it, do that instead of adding a test that catches it.
- [7.1, 7.2] Read the owning plan or tracker before starting, then check its
  claims against the tree. Trust the tree, not the doc.

## Writing code

- [2.7] Never swallow an exception. Every `except` logs, degrades explicitly,
  or re-raises. A bare handler returning an empty value converts an outage
  into a lie downstream code reads as real data.
- [2.4] Degrade honestly: no silent fallbacks, no fabricated values, no `"ok"`
  wrapping an error list. A partial result carries a flag the caller must see.
  Confirm a delete, erasure, or send only when every layer verifiably
  succeeded.
- [2.6] Cap every query or sweep over a collection that grows with usage, and
  refuse honestly when the result is too large.
- [2.8] Never interpolate a value into a query language. The pattern is the
  hole even when today's value is safe.
- [2.3] Exercise the real seam - the route, the transport, the public
  function - not internals the production path never uses.
- [3.3] Verify against the running system's actual state: the response body,
  the row, the console. Do not conclude "it works" from a screenshot or from
  output that merely looks green.

## Frontend

- [3.1] Every interactive control must change URL, DOM, or persisted state,
  and a test must assert that it did. Rendering is not working.
- [3.2] Per route and role, assert: it lands (not bounced to login), no error
  boundary, no meaningful console errors, non-empty body.
- [3.6] Do not count selectors. A testid can exist and be unreachable; a spec
  can pass vacuously. Measure reachability and effect.

## Before committing

- [2.1] Ship every fix with a guard in the same commit. Prefer a class ratchet
  - an invariant that walks the code by AST, route table, or schema and fails
  on every current and future sibling - over a point test.
- [2.2] Show the guard fail: revert the fix and the test must go red. A guard
  never shown to fail is decoration. Run the experiment; do not claim it.
- [2.5] Re-baseline a golden set only deliberately, in the same commit as the
  intentional change, with the reason in the commit message.
- [7.3] Stage named files only. Never `git add -A` on a shared tree.

## Reporting results

- [6.3, 6.6] An exit code is a claim about a process, not about a check. It is
  evidence only in pairs: a known-good input exits 0 AND a known-bad input
  exits non-zero. `--selfcheck` on a tool with no argument parser exits 0
  because the import succeeded, and reads exactly like a pass. Never pipe a
  build or test through anything that swallows `$?`; report a truncated run as
  truncated.
- [6.6] A change to a running system is done when its effect is witnessed at a
  runtime surface - a metric, a log line, a queryable row - not when the
  deploy command exited 0. A surface that cannot report must say so: an
  endpoint degrading to an empty 200 turns "no data" into "all zero".
- [6.4] Prove a finding refutes the null before filing it. A false finding
  costs more trust than no finding.
- [5.1] Label every number you publish: measured, estimated with stated
  assumptions, or illustrative. In the artifact, not in your head.

## Model-backed features

- [4.1] The model phrases; it never invents. Every generated number traces to
  a computed value or is flagged unverifiable - mechanically, not by prompt.
- [4.3] Schema-validate every structured output with bounded corrective
  retries. A model response is untrusted input.

## Stop rule

- [8.3] When the marginal round of hardening, polishing, or testing yields
  less than the next cheapest activity, stop and switch.

---

Condensed from the Sutradhar doctrine. Full operating rules: `agent/AGENTS.md`.
The scar behind each number: `DOCTRINE.md`.
Source: https://github.com/sutradharhq/sutradhar
