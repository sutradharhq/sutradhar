# Frontend playbook: the two loops

Frontend verification is two different loops with two different tools, and
most teams (and most agents) run neither properly. The failure mode this
playbook exists for: a session in which five UI defects were found by a
human clicking around and zero by the test suite - because the suite
asserted that things render, and every defect was in what things do.

## The inner loop: while building

**Assert on the running app's runtime state. Never eyeball pixels.**

While you are building a feature, your feedback loop is the running dev
server. The discipline:

- Verify against **network responses** (did the request fire, what came
  back), **store/state values** (did the selection persist), and the
  **console** (did anything throw) - through runtime observation.
  Sutradhar ships its own tool for this: the
  [runtime probe](../js/probe/README.md) - install it in the dev build,
  and any agent with `curl` can read the live console, network log, and
  exposed store state (an MCP adapter is included). Browser devtools
  protocol tooling or [Reticle](https://github.com/reticlehq/reticle)
  work here too; the discipline matters more than the tool.
- A screenshot that "looks right" proves nothing in either direction: the
  data can be hardcoded, the control can be dead, the store can be stale.
  Pixels lie both ways.
- The inner loop is fast and disposable. Its assertions do NOT need to be
  committed; they need to be *true right now*.

## The outer loop: the regression gate

**The committed e2e suite asserts behavior, not existence.**

The inner loop dies with the session. What protects the feature next month
is the committed suite, and it must assert the things that actually break:

1. **Route baseline** (breadth, cheap, first): every route x role renders,
   is not bounced by auth, shows no error boundary, settles all fetches,
   logs zero meaningful console errors. One spec, generated from the route
   table. See [js/cypress/routeSweep.example.cy.ts](../js/cypress/routeSweep.example.cy.ts).
2. **Effect assertions** (depth, opt-in per control): every interactive
   control asserts an EFFECT - URL, DOM, or persisted state changed
   (`expectEffect`). The control-that-does-nothing class ships constantly
   under render-only suites: a picker whose choice a context overwrote on
   the same tick, a "sort" header that was static text. Both rendered
   perfectly.
3. **Paint checks** (the outer loop's exclusive job): overprint and
   occlusion detection (`overprintsIn`). Runtime state can be correct while
   the pixels are wrong, so geometry assertions belong in the committed
   suite - and they must measure inked bounds via Range, because box
   geometry and scrollWidth are both blind to real overlap defects (we
   proved this against a reproduction, twice).

## The assertion must be able to fail

Two ways an e2e test reports green while testing nothing (doctrine 3.7):

1. **The assertion is too weak.** `expect(status).to.not.eq(500)` passes on
   404, 403, 401 and 400. Assert the contract you expect.
2. **The target no longer exists.** A request to a deleted route cannot fail
   however strong the assertion, because it never reaches real behaviour.

Gate both against the app's own route table, wherever your stack is already
up (the e2e job usually):

```python
from sutradhar_guards.dead_route_lint import find_dead_routes
from sutradhar_guards.ratchet import Ratchet

routes = set(requests.get(f"{API}/openapi.json").json()["paths"])
Ratchet("tests/baselines/dead_routes.json").assert_only_shrinks(
    find_dead_routes("cypress/e2e/", routes)
)
```

Any route source works - OpenAPI paths, a `rails routes` dump, an Express
router walk. A real suite hid 28 dead-route references behind "not 500" for
months. Ask of every check: *what would have to break for this to go red?*

## Instrumentation is source work

- Give every new component stable testids AT BUILD TIME, one naming idiom
  per project. A surface shipped without anchors is unanchorable, and
  retrofitting ids costs more than a sprint of specs.
- Do not measure a suite by counting selectors. A testid can exist and be
  unreachable (component mounted on one page nobody visits); a spec can
  pass vacuously (`not.exist` against long-deleted UI, catch-all redirects
  masking dead routes). Measure REACHABILITY (the sweep actually landed on
  the route) and EFFECT (the interaction changed something).

## Waiting is measurement, not sleep

A fixed `wait(1200)` is a bet that the app is done; against a slow fetch it
silently asserts against the pre-crash frame. Count in-flight requests
(patch `fetch` before app code runs) and settle on zero, then a grace beat,
then re-check for follow-up fetches. The helper is `trackPendingRequests` +
`waitForIdle` in [js/cypress/uiGuards.ts](../js/cypress/uiGuards.ts).

## Console ignore lists have rules

Every ignored console pattern carries a comment saying why it is safe. An
ignore list without reasons only grows, and a guard whose ignore list has
swallowed it is decoration that still runs in CI.
