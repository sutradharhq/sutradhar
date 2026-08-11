// Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
// Part of Sutradhar: https://github.com/sutradharhq/sutradhar
/**
 * Route sweep - the outer-loop baseline every app should have.
 *
 * For every route x role: the page LANDED (was not bounced to login),
 * rendered real content, did not crash to the error boundary, finished all
 * its fetches, and logged zero meaningful console errors.
 *
 * This one spec catches the page-crashes-on-mount class that code review
 * structurally cannot see (the crash is in the interaction between the
 * page, the router, and live data). It found real defects on day one in
 * the codebase it was written for.
 *
 * Copy into cypress/e2e/, adjust ROUTES and the login command, delete this
 * banner.
 */
import {
  assertNoErrorBoundary,
  captureConsoleErrors,
  meaningfulErrors,
  trackPendingRequests,
  waitForIdle,
  type PendingState,
} from "../support/uiGuards";

/** Every user-reachable route, with the roles that may see it. */
const ROUTES: { path: string; roles: string[] }[] = [
  { path: "/", roles: ["admin", "viewer"] },
  { path: "/dashboard", roles: ["admin", "viewer"] },
  { path: "/settings", roles: ["admin"] },
  // ... enumerate ALL of them. A route missing from this list is a route
  // with no baseline. Consider generating this list from your router
  // config so the sweep cannot drift from the app.
];

describe("route sweep: renders, no crash, console clean", () => {
  for (const { path, roles } of ROUTES) {
    for (const role of roles) {
      it(`${path} as ${role}`, () => {
        const errors: string[] = [];
        const pending: PendingState = { inFlight: 0, everStarted: 0 };

        cy.login(role); // your auth command
        cy.visit(path, {
          onBeforeLoad: (win) => {
            captureConsoleErrors(win, errors);
            trackPendingRequests(win, pending);
          },
        });

        waitForIdle(pending);

        // Landed, not bounced: an auth redirect that dumps a viewer on the
        // login page "passes" every render assertion unless you check the
        // URL you ended up on.
        cy.location("pathname").should("not.include", "/login");

        assertNoErrorBoundary(path);

        // Non-empty body: a blank page with a happy status code is still a
        // defect.
        cy.get("body").invoke("text").should("have.length.greaterThan", 50);

        cy.then(() => {
          expect(
            meaningfulErrors(errors),
            `console errors on ${path} as ${role}`,
          ).to.deep.eq([]);
        });
      });
    }
  }
});
