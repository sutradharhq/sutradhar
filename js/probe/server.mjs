#!/usr/bin/env node
/**
 * Sutradhar probe bridge - the local server between a running app and an
 * agent's terminal.
 *
 * Zero dependencies (node:http only), binds 127.0.0.1, dev-only by design.
 * The browser probe long-polls it; agents query it with plain curl - which
 * makes it usable by ANY agent that has a shell, with no MCP client
 * required (an MCP adapter is provided separately in mcp.mjs).
 *
 * Agent-facing endpoints:
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
 * Run:  node server.mjs           (port 7071, or SUTRADHAR_PROBE_PORT)
 */
import http from "node:http";

const QUERY_TIMEOUT_MS = 10_000;
const POLL_HOLD_MS = 20_000;
const STALE_MS = 8_000;

export function createBridge({ port = 0 } = {}) {
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
    const text = JSON.stringify(body);
    res.writeHead(code, {
      "content-type": "application/json",
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "content-type",
    });
    res.end(text);
  }

  async function readBody(req) {
    let raw = "";
    for await (const chunk of req) raw += chunk;
    return raw ? JSON.parse(raw) : {};
  }

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://x");
    const path = url.pathname;
    try {
      if (req.method === "OPTIONS") return json(res, 204, {});

      // ── probe side ────────────────────────────────────────────────────
      if (path === "/probe/poll" && req.method === "POST") {
        const body = await readBody(req);
        state.probe = {
          probeId: body.probeId,
          pageUrl: body.pageUrl,
          stateKeys: body.stateKeys || [],
          lastSeen: Date.now(),
        };
        for (const e of body.console || []) state.consoleBuf.push(e);
        for (const e of body.network || []) state.networkBuf.push(e);
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
        const body = await readBody(req);
        const waiter = state.inflight.get(body.id);
        if (waiter) {
          state.inflight.delete(body.id);
          waiter.resolve(body);
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
        const body = await readBody(req);
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

// Run directly: bind the configured port and stay up.
if (import.meta.url === `file://${process.argv[1]}`) {
  const port = Number(process.env.SUTRADHAR_PROBE_PORT || 7071);
  createBridge({ port }).then(({ port: p }) => {
    console.log(`[sutradhar-probe] bridge on http://127.0.0.1:${p}`);
    console.log(`  try: curl -s http://127.0.0.1:${p}/status`);
  });
}
