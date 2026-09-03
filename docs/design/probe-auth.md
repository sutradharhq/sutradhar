---
sutradhar_scar: R10-1
sutradhar_budget: probe-auth
n: 128
n_unit: token bits
---

# Design note: probe bridge authentication

<!-- Why this note exists: an external adversarial review (round 10, R10-1)
     demonstrated that any webpage open in the developer's browser could
     reach the loopback bridge cross-origin: `access-control-allow-origin:
     *` made every response readable, simple POSTs needed no preflight,
     `/probe/poll` let a hostile page impersonate the probe outright, and
     `/probe/result` let it answer the agent's queries with fabricated
     values - poisoning exactly the channel whose contract is "never a
     fabricated value". A tool whose product is honesty had a fabrication
     hole in its transport. -->

## What and why

The bridge is a loopback server that can read page state and execute JS in
the app's origin. Its legitimate clients are `curl`, the MCP adapter, and
the page's own probe - none of which are other webpages. The threat this
design refuses is **the browser as attacker**: a malicious page the
developer happens to have open, reaching `http://127.0.0.1:<port>`
from JavaScript.

## The four layers, each independent

1. **No CORS headers at all.** No legitimate client is a browser, so
   `access-control-allow-origin` served only hostile pages. Without it,
   cross-origin *reads* are dead.
2. **A shared token required on every request**, carried in the custom
   header `x-sutradhar-probe-token`. Custom headers force a preflight for
   browser requests; the preflight response carries no CORS permission, so
   the browser refuses to send the actual request. This kills the
   simple-request bypass (`text/plain` POST) that reads alone do not.
   Comparison is timing-safe (sha256 then `timingSafeEqual`). If no token
   is supplied (`--token`, `SUTRADHAR_PROBE_TOKEN`, or the `createBridge`
   option), the bridge generates 32 random bytes and prints them once -
   secure by default, one copy to use.
3. **Host header check.** Requests whose Host is not the bound loopback
   host are refused. DNS rebinding resolves `evil.example` to 127.0.0.1;
   its Host header still says `evil.example`, which is now a refusal.
4. **`/probe/result` shape validation.** Only `{id: string, ok: boolean}`
   plus `value`/`error` is forwarded to a waiter; anything else is a 400.
   An impersonating page that somehow obtained a poll slot cannot inject
   arbitrary payload shapes into agent answers.

Request bodies are capped (5 MB, 413 with a reason): the anti-unbounded-read
rule applies to this tool's own front door too.

And on the installer side: the bridge URL is parsed with `new URL()` and
accepted only when `.hostname` is loopback - the previous regex accepted
`http://127.0.0.1@evil.example` (userinfo trick), shipping page state
off-machine.

## Cardinalities and budgets  <!-- doctrine 1.1 -->

| Dimension | Design N | Enforced by |
|---|---|---|
| generated token entropy | >= 128 bits | `test_probe_token_meets_declared_entropy` |

One number, because one number is honestly enforced. The auth check itself
is one Map lookup and one digest comparison per request - O(1), no
accumulating state - so there is no meaningful latency or memory envelope
to freeze; declaring p95/memory numbers for it would be decoration, and
undeclared numbers are exactly what the gate is for. The 5 MB body cap and
the refusal paths are enforced behaviorally by `selftest.mjs` through the
real seam rather than by envelope numbers.

## Failure story  <!-- doctrine 1.4 -->

| Actor sees | When | Response |
|---|---|---|
| curl/MCP without the token | any endpoint | `403` naming the missing header and where the token is printed |
| curl/MCP with wrong token | any endpoint | `403`; same message shape |
| hostile webpage (read attempt) | GET any endpoint | preflight-less request sent, response unreadable (no ACAO); if sent anyway, 403 |
| hostile webpage (simple POST, no custom header possible) | `/eval` etc. | 403 before any handler runs |
| rebound DNS (Host mismatch) | any endpoint | 403 naming the Host check |
| probe page without token | install | installer throws naming the option and where the token is printed |
| oversized body | POST endpoints | 413 with the cap stated |

No path degrades to an empty 200, and none of these refusals can be
distinguished from success by a caller who does not check the status code -
so the status code IS the contract, and the selftest asserts it.

## What deliberately did not change

The dev-only rule stays where it was: `import.meta.env.DEV` around the
install remains THE mechanism keeping the probe out of production bundles;
the bridge's token raises the cost of accidental exposure but does not
replace that guard. `allowEval` still defaults to off. The bridge still
binds `127.0.0.1` only.
