#!/usr/bin/env node
// Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
// Part of Sutradhar: https://github.com/sutradharhq/sutradhar
/**
 * Sutradhar probe bridge - the local server between a running app and an
 * agent's terminal.
 *
 * Zero dependencies (node:http only), binds 127.0.0.1, dev-only by design.
 * The browser probe long-polls it; agents query it with plain curl - which
 * makes it usable by ANY agent that has a shell, with no MCP client
 * required (an MCP adapter is provided separately in mcp.mjs).
 *
 * Agent-facing endpoints (ALL require the shared token):
 *   GET  /status            is a page connected, its URL, buffer counts, state keys
 *   GET  /console           captured console errors/warnings (?level=error)
 *   GET  /network           request summaries (?match=substring)
 *   GET  /state/<name>      evaluate a registered state getter in the page
 *   POST /eval {expr}       evaluate an expression in the page (probe must opt in)
 *   POST /clear             reset buffers between verification steps
 *
 * Honesty rules encoded here:
 *   - a state/eval query when no page is connected is a 503 with a stated
 *     reason, never an empty 200
 *   - a query the page does not answer within 10s is a 504, never a hang
 *     and never a fabricated value
 *
 * Trust rules encoded here (design note: docs/design/probe-auth.md):
 *   - every request carries the shared token in `x-sutradhar-probe-token`;
 *     a request without it is a 403 naming the header, never a best-effort
 *     answer. The legitimate clients are curl, the MCP adapter, and the
 *     page's own probe - no browser ever needs permission from this server,
 *     so NO CORS headers are sent: cross-origin reads and preflighted
 *     custom-header requests die in the browser, and the token kills the
 *     preflight-less simple-request bypass.
 *   - a Host header that is not loopback is a 403: DNS rebinding points
 *     evil.example at 127.0.0.1 but cannot forge its Host header.
 *   - /probe/poll and /probe/result validate their shapes before any state
 *     changes or waiter resolves - a fabricated or malformed payload is a
 *     refusal, never a silent accept.
 *
 * Run:  node server.mjs           (port 7071, or SUTRADHAR_PROBE_PORT)
 * Token: --token <value>, or SUTRADHAR_PROBE_TOKEN, or generated & printed.
 */
import http from "node:http";
import crypto from "node:crypto";

const QUERY_TIMEOUT_MS = 10_000;
const POLL_HOLD_MS = 20_000;
const STALE_MS = 8_000;
export const TOKEN_HEADER = "x-sutradhar-probe-token";
const MAX_BODY_BYTES = 5_000_000; // doctrine 2.6 applies to our own front door

/** Constant-time token comparison: digest first so lengths never leak. */
function tokenMatches(supplied, expected) {
  const a = crypto.createHash("sha256").update(String(supplied)).digest();
  const b = crypto.createHash("sha256").update(String(expected)).digest();
  return crypto.timingSafeEqual(a, b);
}

/** Loopback hostnames only - the hostname, not whatever precedes an "@".
 *  This is the same class of hole as `http://user@evil.example`, so the
 *  URL parser decides, not a regex over the front of the string. */
export function isLoopbackHost(hostHeader) {
  try {
    const { hostname } = new URL(`http://${hostHeader}`);
    return ["127.0.0.1", "localhost", "[::1]", "::1"].includes(hostname);
  } catch {
    return false;
  }
}

export function createBridge({ port = 0, token } = {}) {
  // A missing token is generated, not defaulted: a bridge that answered
  // without one would be exactly the hole this file exists to close.
  const authToken =
    token !== undefined && token !== null && String(token).length > 0
      ? String(token)
      : crypto.randomBytes(32).toString("hex");

  const state = {
    probe: null, // {probeId, pageUrl, stateKeys, lastSeen}
    consoleBuf: [],
    networkBuf: [],
    queue: [], // pending queries not yet delivered to the page
    inflight: new Map(), // id -> {resolve}
    heldPoll: null, // {res, timer} - a poll request we are holding open
    nextId: 1,
  };

  const connected = () =>
    Boolean(state.probe && Date.now() - state.probe.lastSeen < STALE_MS + POLL_HOLD_MS);

  function flushPoll() {
    if (!state.heldPoll || state.queue.length === 0) return;
    const { res, timer } = state.heldPoll;
    clearTimeout(timer);
    state.heldPoll = null;
    json(res, 200, { queries: state.queue.splice(0) });
  }

  function askPage(kind, arg) {
    return new Promise((resolve) => {
      const id = String(state.nextId++);
      const timer = setTimeout(() => {
        state.inflight.delete(id);
        // A timed-out query also leaves the queue: otherwise the next poll
        // would deliver a question whose waiter is gone, and the page's
        // answer would be silently discarded - work for the page, and a
        // queue that only grows across dead pages.
        const qi = state.queue.findIndex((q) => q.id === id);
        if (qi !== -1) state.queue.splice(qi, 1);
        resolve({
          ok: false, timeout: true,
          error: `page did not answer within ${QUERY_TIMEOUT_MS / 1000}s - it may be frozen, navigating, or the probe stopped`,
        });
      }, QUERY_TIMEOUT_MS);
      state.inflight.set(id, {
        resolve: (r) => {
          clearTimeout(timer);
          resolve(r);
        },
      });
      state.queue.push({ id, kind, arg });
      flushPoll();
    });
  }

  function json(res, code, body) {
    // Deliberately NO access-control-allow-* headers: every legitimate
    // client is non-browser, and a CORS permission here would re-open the
    // cross-origin read hole the token exists to close. A hostile page's
    // preflight succeeds against this silence and the browser then refuses
    // to send the actual request.
    const text = JSON.stringify(body);
    res.writeHead(code, { "content-type": "application/json" });
    res.end(text);
  }

  async function readBody(req, res) {
    let size = 0;
    const chunks = [];
    let tooBig = false;
    for await (const chunk of req) {
      if (tooBig) continue; // drain before refusing, or the client's view of the 413 dies with the socket
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        tooBig = true;
        continue;
      }
      chunks.push(chunk);
    }
    if (tooBig) {
      json(res, 413, {
        error: `request body exceeds ${MAX_BODY_BYTES} bytes - refused`,
      });
      return undefined;
    }
    const raw = Buffer.concat(chunks).toString("utf8");
    try {
      return raw ? JSON.parse(raw) : {};
    } catch {
      json(res, 400, { error: "body is not valid JSON" });
      return undefined;
    }
  }

  /** The gate every request passes before any handler: loopback Host, then
   *  the token. Returns true when the response has been written. */
  function refused(req, res) {
    const host = req.headers.host;
    if (!host || !isLoopbackHost(host)) {
      json(res, 403, {
        error: `refused: Host header ${JSON.stringify(host ?? null)} is not the loopback bridge - this server answers only to 127.0.0.1/localhost (DNS-rebinding guard)`,
      });
      return true;
    }
    const supplied = req.headers[TOKEN_HEADER];
    if (!supplied || !tokenMatches(supplied, authToken)) {
      json(res, 403, {
        error: `refused: missing or wrong '${TOKEN_HEADER}' header - the token is printed when the bridge starts (or set SUTRADHAR_PROBE_TOKEN / pass --token)`,
      });
      return true;
    }
    return false;
  }

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://x");
    const path = url.pathname;
    try {
      // Browser preflight: acknowledged with permission deliberately
      // withheld (see json()). Everything real is gated below.
      if (req.method === "OPTIONS") return json(res, 204, {});
      if (refused(req, res)) return;

      // ── probe side ────────────────────────────────────────────────────
      if (path === "/probe/poll" && req.method === "POST") {
        const body = await readBody(req, res);
        if (body === undefined) return;
        if (
          typeof body.probeId !== "string" || body.probeId.length === 0 ||
          typeof body.pageUrl !== "string" ||
          !Array.isArray(body.stateKeys) ||
          !Array.isArray(body.console) || !Array.isArray(body.network)
        ) {
          return json(res, 400, {
            error: "malformed poll - expected {probeId: string, pageUrl: string, stateKeys: string[], console: [], network: []}",
          });
        }
        state.probe = {
          probeId: body.probeId,
          pageUrl: body.pageUrl,
          stateKeys: body.stateKeys,
          lastSeen: Date.now(),
        };
        for (const e of body.console) state.consoleBuf.push(e);
        for (const e of body.network) state.networkBuf.push(e);
        if (state.consoleBuf.length > 1000) state.consoleBuf.splice(0, state.consoleBuf.length - 1000);
        if (state.networkBuf.length > 1000) state.networkBuf.splice(0, state.networkBuf.length - 1000);

        if (state.queue.length > 0) {
          return json(res, 200, { queries: state.queue.splice(0) });
        }
        // Hold the poll open so a query reaches the page immediately.
        const timer = setTimeout(() => {
          if (state.heldPoll && state.heldPoll.res === res) {
            state.heldPoll = null;
            json(res, 200, { queries: [] });
          }
        }, POLL_HOLD_MS);
        if (state.heldPoll) {
          clearTimeout(state.heldPoll.timer);
          json(state.heldPoll.res, 200, { queries: [] });
        }
        state.heldPoll = { res, timer };
        req.on("close", () => {
          if (state.heldPoll && state.heldPoll.res === res) {
            clearTimeout(state.heldPoll.timer);
            state.heldPoll = null;
          }
        });
        return;
      }

      if (path === "/probe/result" && req.method === "POST") {
        const body = await readBody(req, res);
        if (body === undefined) return;
        // Shape-validated and field-filtered: only a well-formed answer for
        // a known query id reaches a waiter, so nothing else can shape what
        // the agent reads.
        if (
          typeof body.id !== "string" || body.id.length === 0 ||
          typeof body.ok !== "boolean"
        ) {
          return json(res, 400, {
            error: "malformed result - expected {id: string, ok: boolean, value?|error?}",
          });
        }
        const waiter = state.inflight.get(body.id);
        if (waiter) {
          state.inflight.delete(body.id);
          waiter.resolve(
            body.ok
              ? { id: body.id, ok: true, value: body.value }
              : { id: body.id, ok: false, error: String(body.error ?? "") },
          );
        }
        return json(res, 200, {});
      }

      // ── agent side ────────────────────────────────────────────────────
      if (path === "/status") {
        return json(res, 200, {
          connected: connected(),
          pageUrl: state.probe?.pageUrl || null,
          lastSeenMsAgo: state.probe ? Date.now() - state.probe.lastSeen : null,
          stateKeys: state.probe?.stateKeys || [],
          consoleCount: state.consoleBuf.length,
          networkCount: state.networkBuf.length,
        });
      }

      if (path === "/console") {
        const level = url.searchParams.get("level");
        const entries = level
          ? state.consoleBuf.filter((e) => e.level === level)
          : state.consoleBuf;
        return json(res, 200, { entries });
      }

      if (path === "/network") {
        const match = url.searchParams.get("match");
        const entries = match
          ? state.networkBuf.filter((e) => (e.url || "").includes(match))
          : state.networkBuf;
        return json(res, 200, { entries });
      }

      if (path === "/clear" && req.method === "POST") {
        state.consoleBuf = [];
        state.networkBuf = [];
        return json(res, 200, { cleared: true });
      }

      if (path.startsWith("/state/")) {
        if (!connected()) {
          return json(res, 503, {
            ok: false,
            error: "no page connected - is the app running with the probe installed?",
          });
        }
        const r = await askPage("state", decodeURIComponent(path.slice(7)));
        return json(res, r.ok ? 200 : r.timeout ? 504 : 400, r);
      }

      if (path === "/eval" && req.method === "POST") {
        if (!connected()) {
          return json(res, 503, {
            ok: false,
            error: "no page connected - is the app running with the probe installed?",
          });
        }
        const body = await readBody(req, res);
        if (body === undefined) return;
        const r = await askPage("eval", String(body.expr || ""));
        return json(res, r.ok ? 200 : r.timeout ? 504 : 400, r);
      }

      json(res, 404, {
        error: `unknown path ${path}`,
        endpoints: ["/status", "/console", "/network", "/state/<name>", "POST /eval", "POST /clear"],
      });
    } catch (e) {
      json(res, 500, { error: String((e && e.message) || e) });
    }
  });

  return new Promise((resolve) => {
    server.listen(port, "127.0.0.1", () => {
      resolve({
        port: server.address().port,
        token: authToken,
        close: () => new Promise((r) => {
          if (state.heldPoll) {
            clearTimeout(state.heldPoll.timer);
            json(state.heldPoll.res, 200, { queries: [] });
            state.heldPoll = null;
          }
          server.close(r);
          server.closeAllConnections?.();
        }),
      });
    });
  });
}

// Run directly: bind the configured port, resolve the token, stay up.
// An unknown argument is REFUSED, never ignored - a silently-dropped
// `--tocken` would start an unconfigured bridge and report success.
if (import.meta.url === `file://${process.argv[1]}`) {
  let port = Number(process.env.SUTRADHAR_PROBE_PORT || 7071);
  let cliToken = process.env.SUTRADHAR_PROBE_TOKEN || "";
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--token") {
      cliToken = argv[++i] ?? "";
      if (!cliToken) {
        console.error("[sutradhar-probe] --token needs a value");
        process.exit(2);
      }
    } else if (argv[i] === "--port") {
      port = Number(argv[++i]);
      if (!Number.isFinite(port) || port <= 0) {
        console.error("[sutradhar-probe] --port needs a positive number");
        process.exit(2);
      }
    } else if (argv[i] === "--help" || argv[i] === "-h") {
      console.log("usage: node server.mjs [--port N] [--token T]");
      process.exit(0);
    } else {
      console.error(`[sutradhar-probe] unknown argument: ${argv[i]} (known: --port, --token, --help)`);
      process.exit(2);
    }
  }

  createBridge({ port, token: cliToken || undefined }).then(({ port: p, token: t }) => {
    const shown = cliToken ? t : `${t}   (generated - pass this as ${TOKEN_HEADER})`;
    console.log(`[sutradhar-probe] bridge on http://127.0.0.1:${p}`);
    console.log(`  token: ${shown}`);
    console.log(`  try:   curl -s -H '${TOKEN_HEADER}: ${cliToken ? t : "<token>"}' http://127.0.0.1:${p}/status`);
  });
}
