# Round 10 - 2026-08-23

Lenses: external adversarial review, trust surface, self-application

**What this round was.** An independent adversarial review of the whole
framework and its sibling repo - run deliberately (doctrine 8.4: one
mind, or one family of agents, shares blind spots with itself). The
reviewers read every guard, drove the running bridge and the receipt
chain, and probed where the code disagrees with its own docstrings. The
probe bridge's transport failed hardest; this round is the fix. Recorded
because the framework that polices honesty had an unauthenticated,
browser-readable fabrication channel in the tool it ships for asserting
runtime honesty.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R10-1 | high | 2.4 | external review, live probe of the bridge | fixed | any webpage open in the dev's browser could reach the loopback bridge cross-origin: `access-control-allow-origin: *` made every response readable, preflight-less POSTs reached handlers, `/probe/poll` let a hostile page impersonate the probe outright, and `/probe/result` forwarded arbitrary payload shapes to agent queries - a fabrication channel into exactly the tool whose contract is "never a fabricated value". Four independent layers now refuse it: token on every request, no CORS headers at all, Host check against rebinding, shape-validated field-filtered results. Each layer mutation-verified |
| R10-2 | high | 1.2 | external review, URL parsing | fixed | the installer's local-bridge guard was a regex over the front of the string, so `http://127.0.0.1@evil.example` passed and page state would ship off-machine; dev-only installation was enforced only by prose. The parser is now `new URL()` deciding on `.hostname`, the token is required at install, and a source ratchet holds the class across future edits |
| R10-3 | med | 2.6 | external review, reading obsgate's scar back onto the tool | fixed | POST endpoints read request bodies without bound - the unbounded-read rule unapplied to the tool's own front door. Bodies are now capped with a 413 that states the cap, drained before refusal so the client can actually read the verdict |
| R10-4 | med | 2.4 | found while writing R10-1's failure-path tests | fixed | a query that timed out stayed in the delivery queue forever: the next poll would deliver a question whose waiter was gone, and the answer was silently discarded - work for the page, and a queue that grew across dead pages. Timed-out queries now leave the queue when their waiter dies |
| R10-5 | low | - | external review | fixed | the MCP adapter encoded `match`/`name` but not `level`; all query params are now encoded. Also: unknown CLI arguments to `server.mjs` were silently ignored - the verify_guard flag-swallowing scar recurring in miniature - and are now refused |

## Corrected premises

- **"Binding loopback is the boundary."** It is not, for anything a
  browser runs: webpages the developer browses can reach 127.0.0.1 from
  JavaScript, and DNS rebinding points foreign origins at it without any
  browser bug at all. The boundary is the credential plus the absence of
  CORS permission, not the bind address. The old security posture said
  "the same trust class as an open devtools port" and then shipped fewer
  guards than devtools has.
- **"The selftest covered the contract."** It covered the honesty half
  (503s, 504s, refusals naming reasons) and none of the trust half - not
  one case asked who may ask. A contract with no authentication cases
  tested the protocol, not the system.
- **"The budget gate reads intent."** First real use caught the author
  quoting the budget id in backticks in the enforcing test - the gate
  demanded a literal quoted reference and refused the decoration. The
  gate held the line against the person writing the enforcement.

## Harness gotchas

- The fabricated-result test initially raced the bridge's staleness
  window: after stop()'s 20s drain-hold plus a 10s timeout bound, no page
  is recent enough for a queued flush, so the test must register its page
  FIRST and fire the query into the held poll. Test-order coupling to a
  time window is a flake factory; the deterministic ordering (page, then
  query) is not.
- node's own HTTP/1.1 parser refuses a missing Host header before any
  handler runs (empty-body 400). The selftest asserts the contract ("no
  Host means no service"), not whose status code says so - asserting our
  specific message there would break on every node upgrade for no
  behavioral difference.

## Stop decision

CONTINUE - two HIGH findings this round. The sibling repo (Ledger)
carries the review's other HIGH findings (tail-truncation overclaim,
self-declared evidence grades); they are recorded in its own logbook,
not here.
