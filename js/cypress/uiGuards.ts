/**
 * uiGuards - behavioral UI invariants for Cypress.
 *
 * Written after a session in which five UI defects were found by a human
 * clicking around and ZERO by the existing test suite. The suite asserted
 * that things RENDER; every defect was in what things DO.
 *
 * A first audit put that suite's selector rot at 53%. The number was wrong
 * (a literal-grep artifact that missed template-built testids); re-measured
 * properly it was ~26%. Recorded because the correction cuts both ways: a
 * testid PRESENT in source is not necessarily REACHABLE - one spec
 * referenced zero missing testids and was entirely dead, because its
 * component was mounted on exactly one page it never visited. Counting
 * strings measures neither rot nor coverage.
 *
 * That is the case for guards that assert behavior instead of selectors:
 * a suite pinned to selectors rots on every refactor, and a permanently-red
 * suite is worse than none because nobody reads it. These helpers assert
 * properties that hold for ANY correct page, so they survive refactors by
 * construction:
 *
 *   - assertNoErrorBoundary - the page rendered rather than crashing
 *   - meaningfulErrors      - nothing threw on the way
 *   - expectEffect          - a control that claims to do something did
 *   - overprintsIn          - no element paints over its neighbor
 *
 * They are cheap to run over every route, which is the point: breadth
 * first, then depth where a surface earns it.
 *
 * Configure once in cypress/support/e2e.ts:
 *
 *   import { configureUiGuards } from "./uiGuards";
 *   configureUiGuards({
 *     errorBoundaryText: "Something went wrong",
 *     persistedStateKeys: ["my_app_tenant", "my_app_scope"],
 *     ignoredConsole: ["Download the React DevTools"],
 *   });
 */

export interface UiGuardsConfig {
  /** Copy your ErrorBoundary renders when a view throws. */
  errorBoundaryText: string;
  /** localStorage/sessionStorage keys that count as app state for
   *  expectEffect. List the ones your controls legitimately mutate. */
  persistedStateKeys: string[];
  /** Console substrings that are noise, not defects. Keep this SHORT and
   *  keep a comment on every entry saying why it is safe to ignore - an
   *  ignore list without reasons grows until the guard is decoration. */
  ignoredConsole: string[];
}

let config: UiGuardsConfig = {
  errorBoundaryText: "Something went wrong",
  persistedStateKeys: [],
  ignoredConsole: [],
};

export function configureUiGuards(partial: Partial<UiGuardsConfig>): void {
  config = { ...config, ...partial };
}

/**
 * Console errors the app emitted, captured per test.
 *
 * Install via cy.visit's onBeforeLoad so the stub is in place before any
 * app code runs - a listener attached after mount misses the mount-time
 * throw, which is exactly when a crashing page fails.
 *
 *   const errors: string[] = [];
 *   cy.visit(route, { onBeforeLoad: (win) => captureConsoleErrors(win, errors) });
 */
export function captureConsoleErrors(win: Window, sink: string[]): void {
  const orig = win.console.error;
  win.console.error = (...args: unknown[]) => {
    sink.push(args.map((a) => String(a)).join(" "));
    orig.apply(win.console, args as []);
  };
}

/**
 * In-flight request counter, installed alongside the console capture.
 *
 * A fixed cy.wait(n) is the wrong tool for "has this page finished?" - and
 * that is not a style opinion, it cost a real miss: a route sweep asserted
 * at 1.2s and passed cleanly against a page that WAS crashing, because the
 * crash happened when a Promise.all of fetches resolved, a beat after the
 * assertion ran. Counting fetches lets the sweep wait exactly as long as
 * the page takes.
 */
export interface PendingState {
  inFlight: number;
  everStarted: number;
}

export function trackPendingRequests(win: Window, state: PendingState): void {
  const origFetch = win.fetch;
  win.fetch = function (...args: Parameters<typeof fetch>) {
    state.inFlight += 1;
    state.everStarted += 1;
    return origFetch.apply(win, args).finally(() => {
      state.inFlight -= 1;
    }) as ReturnType<typeof fetch>;
  } as typeof fetch;
}

/**
 * Settle: no request in flight, then a grace beat for the framework to
 * render the result (and to throw, if it is going to). Re-checks so a
 * render that kicks off a follow-up fetch is waited on too.
 */
export function waitForIdle(state: PendingState, graceMs = 700): void {
  cy.wrap(null, { timeout: 30000 }).should(() => {
    expect(state.inFlight, "requests still in flight").to.eq(0);
  });
  cy.wait(graceMs);
  cy.wrap(null, { timeout: 30000 }).should(() => {
    expect(state.inFlight, "follow-up requests still in flight").to.eq(0);
  });
  cy.wait(300);
}

/** Filter captured console errors down to the ones that are defects. */
export function meaningfulErrors(errors: string[]): string[] {
  return errors.filter(
    (e) => !config.ignoredConsole.some((i) => e.includes(i)),
  );
}

/** Fail if the route rendered the error boundary instead of the page. */
export function assertNoErrorBoundary(route: string): void {
  cy.get("body", { timeout: 20000 })
    .invoke("text")
    .then((text) => {
      expect(
        text.includes(config.errorBoundaryText),
        `${route} rendered the error boundary`,
      ).to.eq(false);
    });
}

/**
 * A control that claims to do something must actually do something.
 *
 * The incidents behind this: a scope picker rendered, opened, accepted a
 * selection and changed NOTHING (a context overwrote the choice on the same
 * tick); a sort header advertised three sort modes as static text with no
 * control behind it at all. Neither is visible to a test that only asserts
 * the control renders - which is what most suites do.
 *
 * expectEffect snapshots the observable world, runs the interaction, and
 * fails if nothing moved. Effects worth counting: the URL, the rendered
 * text, or persisted app state (the keys you configured).
 *
 * Deliberately OPT-IN per control rather than a sweep that clicks
 * everything on a page: real apps have "Reset", "Retry", and "Delete"
 * buttons, and a blanket auto-clicker will eventually fire one against a
 * live stack. Breadth belongs in the route sweep, which only reads.
 */
export function expectEffect(
  label: string,
  interact: () => void,
  opts: { settleMs?: number } = {},
): void {
  const snap = { url: "", text: "", store: "" };
  const readStore = (win: Window): string =>
    config.persistedStateKeys
      .map(
        (k) =>
          `${win.localStorage.getItem(k) ?? ""}|${win.sessionStorage.getItem(k) ?? ""}`,
      )
      .join("||");

  cy.location("href").then((h) => {
    snap.url = h;
  });
  cy.get("body")
    .invoke("text")
    .then((t) => {
      snap.text = t.replace(/\s+/g, " ").trim();
    });
  cy.window().then((win) => {
    snap.store = readStore(win);
  });

  cy.then(() => interact());
  cy.wait(opts.settleMs ?? 900);

  cy.location("href").then((afterUrl) => {
    cy.get("body")
      .invoke("text")
      .then((afterTextRaw) => {
        const afterText = afterTextRaw.replace(/\s+/g, " ").trim();
        cy.window().then((win) => {
          const afterStore = readStore(win);
          const moved =
            afterUrl !== snap.url ||
            afterText !== snap.text ||
            afterStore !== snap.store;
          expect(
            moved,
            `${label} changed nothing - no URL, DOM or persisted-state effect`,
          ).to.eq(true);
        });
      });
  });
}

/**
 * Fail if any element's INKED bounds cross its next sibling's.
 *
 * Measured with a Range over each element's contents, not
 * getBoundingClientRect on the box and not scrollWidth:
 *
 *   - grid/flex TRACKS by definition do not overlap each other, so a box
 *     scan cannot see content that has spilled OUT of its track;
 *   - scrollWidth only reports RIGHTWARD overflow in LTR, so it is blind
 *     to a flex-end cell overflowing leftward.
 *
 * Both blind spots were found the expensive way: two earlier drafts of this
 * check passed cleanly against a mutation reproducing a real overlap defect
 * (a badge painting over a currency figure in a data table).
 *
 * This is the outer-loop paint check that inner-loop runtime observation
 * structurally cannot do: a store can be correct and a fetch can be 200
 * while the pixels are wrong.
 *
 *   cy.get("[data-testid^=worklist-row]").each(($row) => {
 *     expect(overprintsIn($row[0]), "overprints").to.deep.eq([]);
 *   });
 */
export function overprintsIn(row: Element): string[] {
  const doc = row.ownerDocument;
  const kids = Array.from(row.children);
  const inked = kids
    .map((c) => {
      const track = c.getBoundingClientRect();
      if (track.width === 0 || track.height === 0) return null; // hidden
      const range = doc.createRange();
      range.selectNodeContents(c);
      const r = range.getBoundingClientRect();
      return {
        cls: c.className?.toString().slice(0, 40) || c.tagName,
        text: (c.textContent || "").trim().slice(0, 24),
        r: r.width > 0 ? r : track,
      };
    })
    .filter(Boolean) as { cls: string; text: string; r: DOMRect }[];

  const bad: string[] = [];
  for (let i = 1; i < inked.length; i++) {
    const prev = inked[i - 1];
    const cur = inked[i];
    // Only compare elements on the SAME visual line; a wrapped row's next
    // child legitimately starts to the left of the previous one's right
    // edge.
    const sameLine = Math.abs(prev.r.top - cur.r.top) < prev.r.height / 2;
    if (sameLine && prev.r.right > cur.r.left + 0.5) {
      bad.push(
        `"${prev.text}" (${prev.cls}) paints over "${cur.text}" (${cur.cls}) ` +
          `by ${Math.round(prev.r.right - cur.r.left)}px`,
      );
    }
  }
  return bad;
}
