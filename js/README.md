# js/ - the frontend outer loop

Behavioral UI guards for Cypress. Copy `cypress/uiGuards.ts` into your
project's `cypress/support/`, configure it once in `e2e.ts`, and start with
the route sweep.

```ts
// cypress/support/e2e.ts
import { configureUiGuards } from "./uiGuards";

configureUiGuards({
  errorBoundaryText: "Something went wrong",   // your ErrorBoundary's copy
  persistedStateKeys: ["myapp_tenant", "myapp_scope"],
  ignoredConsole: [
    // Every entry needs a reason, or the list grows until the guard is
    // decoration:
    "Download the React DevTools",  // dev-mode advisory, not a defect
  ],
});
```

## The rules these enforce

1. **Every interactive control has an asserted effect** (`expectEffect`).
   A control that renders is not a control that works.
2. **Every route has a baseline**: renders, not bounced by auth, no error
   boundary, console clean, fetches settled (`routeSweep.example.cy.ts`).
3. **Paint defects live in the outer loop** (`overprintsIn`). Runtime state
   can be correct while the pixels are wrong; only geometry checks see it.

## The inner loop is not here, on purpose

While BUILDING, do not use Cypress as your feedback loop; it is too slow
and too coarse. Assert on the running app's actual runtime state through
browser devtools protocol / MCP browser tooling / Reticle-class tools:
network responses, store values, console output. See
[docs/frontend.md](../docs/frontend.md) for the full two-loop playbook.

## Adopting on an existing suite

Do not rewrite your suite. Add the route sweep first (one file, immediate
breadth), then add `expectEffect` to controls as you touch them. Measure
your suite by reachability and effect coverage, not by testid counts - a
selector can exist and be unreachable, and a spec can pass vacuously
against deleted UI.
