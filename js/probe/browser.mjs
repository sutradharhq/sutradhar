/**
 * Browser installer for the Sutradhar probe - the thin, DOM-touching half.
 *
 * Everything with logic lives in core.mjs (which the selftest exercises
 * against the real bridge); this file only wires the browser environment:
 * patch console + fetch, provide the eval function, start the loop.
 *
 * Install in your app entry, DEV ONLY:
 *
 *   if (import.meta.env.DEV) {
 *     const { installProbe } = await import("./probe/browser.mjs");
 *     const probe = installProbe({
 *       expose: {
 *         route: () => window.location.pathname,
 *         cart: () => useCartStore.getState(),   // any getter you want
 *       },
 *       allowEval: true,   // opt-in; lets the agent evaluate expressions
 *     });
 *     // expose more state later: probe.expose("user", () => store.user)
 *   }
 *
 * Security posture, stated plainly: this is a development tool in the same
 * trust class as an open devtools port. The bridge binds 127.0.0.1 and the
 * probe should never be installed in a production build - the import.meta
 * guard above is the mechanism, and the installer refuses non-local
 * bridges as a second line.
 */
import { ProbeCore } from "./core.mjs";

export function installProbe({
  serverUrl = "http://127.0.0.1:7071",
  allowEval = false,
  expose = {},
} = {}) {
  if (!/^https?:\/\/(127\.0\.0\.1|localhost)[:/]/.test(serverUrl + "/")) {
    throw new Error(
      `[sutradhar-probe] refusing non-local bridge "${serverUrl}" - ` +
      `the probe ships page state and must never leave the machine`,
    );
  }

  const core = new ProbeCore({
    serverUrl,
    fetchImpl: (...a) => nativeFetch(...a),
    allowEval,
    // Indirect eval evaluates in global scope, which is what an agent
    // asking "window.__store.cart.length" expects.
    evalFn: allowEval ? (expr) => (0, eval)(expr) : null,
    pageUrl: () => window.location.href,
  });

  for (const [name, getter] of Object.entries(expose)) core.expose(name, getter);

  // Console capture: errors and warnings, original behavior preserved.
  for (const level of ["error", "warn"]) {
    const orig = console[level].bind(console);
    console[level] = (...args) => {
      core.recordConsole(level, args.map((a) => stringify(a)).join(" "));
      orig(...args);
    };
  }
  window.addEventListener("error", (e) => {
    core.recordConsole("error", `uncaught: ${e.message} @ ${e.filename}:${e.lineno}`);
  });
  window.addEventListener("unhandledrejection", (e) => {
    core.recordConsole("error", `unhandled rejection: ${stringify(e.reason)}`);
  });

  // Network capture: summaries of every fetch the APP makes. The probe's
  // own traffic uses the saved native fetch, so it never records itself.
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const started = performance.now();
    const req = new Request(...args);
    try {
      const res = await nativeFetch(...args);
      let body;
      if ((res.headers.get("content-type") || "").includes("json")) {
        try {
          body = (await res.clone().text()).slice(0, 2000);
        } catch { /* stream already consumed elsewhere - summary only */ }
      }
      core.recordNetwork({
        method: req.method, url: req.url, status: res.status,
        ok: res.ok, ms: Math.round(performance.now() - started), body,
      });
      return res;
    } catch (e) {
      core.recordNetwork({
        method: req.method, url: req.url, status: 0, ok: false,
        ms: Math.round(performance.now() - started),
        body: `NETWORK ERROR: ${stringify(e)}`,
      });
      throw e;
    }
  };

  core.start();
  return core;
}

function stringify(v) {
  if (v instanceof Error) return `${v.name}: ${v.message}`;
  if (typeof v === "object" && v !== null) {
    try { return JSON.stringify(v).slice(0, 500); } catch { return String(v); }
  }
  return String(v);
}
