// Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
// Part of Sutradhar: https://github.com/sutradharhq/sutradhar
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
 *       token: "…the token the bridge printed when it started…",
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
 * trust class as an open devtools port. The bridge binds 127.0.0.1 only,
 * answers only with the shared token, sends no CORS permissions, and the
 * probe should never be installed in a production build - the import.meta
 * guard above is the mechanism, and the installer refuses non-loopback
 * bridges (parsed with `new URL`, so `http://127.0.0.1@evil.example` does
 * not pass) as a second line.
 */
import { ProbeCore } from "./core.mjs";

const LOOPBACK_HOSTNAMES = ["127.0.0.1", "localhost", "[::1]", "::1"];

export function installProbe({
  serverUrl = "http://127.0.0.1:7071",
  token,
  allowEval = false,
  expose = {},
} = {}) {
  let parsed;
  try {
    parsed = new URL(serverUrl);
  } catch {
    throw new Error(
      `[sutradhar-probe] bridge URL "${serverUrl}" does not parse - ` +
      `pass the origin the bridge printed (e.g. http://127.0.0.1:7071)`,
    );
  }
  if (!LOOPBACK_HOSTNAMES.includes(parsed.hostname) || !/^https?:$/.test(parsed.protocol)) {
    throw new Error(
      `[sutradhar-probe] refusing non-local bridge "${serverUrl}" - ` +
      `the probe ships page state and must never leave the machine`,
    );
  }
  if (!token || typeof token !== "string") {
    throw new Error(
      `[sutradhar-probe] missing bridge token - pass the token the bridge ` +
      `printed as installProbe({ token }) (design note: docs/design/probe-auth.md)`,
    );
  }
  // A page that is itself non-local (a preview deploy) reaches the
  // developer's own machine when its JS calls 127.0.0.1 - allowed, but it
  // states itself where the developer is actually looking. Sent natively,
  // before console patching below, so the probe never records its own notice.
  if (!LOOPBACK_HOSTNAMES.includes(window.location.hostname)) {
    window.console.warn(
      `[sutradhar-probe] active on a non-local page (${window.location.hostname}) - ` +
      `page state will be sent to the local bridge; do not ship this build`,
    );
  }

  const core = new ProbeCore({
    serverUrl: parsed.origin,
    fetchImpl: (...a) => nativeFetch(...a),
    token,
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
