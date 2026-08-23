#!/usr/bin/env node
// Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
// Part of Sutradhar: https://github.com/sutradharhq/sutradhar
/**
 * Probe selftest - runs the REAL ProbeCore against the REAL bridge over
 * real HTTP, so the two halves cannot drift. Only browser.mjs's thin
 * wiring (console/fetch patching) is exercised by construction rather
 * than by this test.
 *
 * Per the doctrine, the failure paths are tested as first-class cases:
 * eval-disabled must error (not fabricate), an unknown state name must
 * name what IS available, a dead page must 504 (never hang, never invent),
 * no page at all must 503 - and (round 10) an unauthenticated or
 * hostile-origin request must be refused with a stated reason: no token,
 * wrong token, the preflight-less simple-request bypass, a rebound or
 * missing Host, a malformed poll or result, a fabricated payload's junk
 * fields, and an oversized body. A tool for verifying honesty must itself
 * degrade honestly.
 *
 * Run: node selftest.mjs   (exit 0 = pass; any failure exits nonzero)
 */
import assert from "node:assert/strict";
import http from "node:http";
import { createBridge } from "./server.mjs";
import { ProbeCore } from "./core.mjs";

const results = [];
async function test(name, fn) {
  try {
    await fn();
    results.push([name, "ok"]);
  } catch (e) {
    results.push([name, `FAIL: ${e.message}`]);
  }
}

// Generated, not passed in: proves the secure-by-default path and gives
// every later request its credential.
const { port, close, token } = await createBridge({ port: 0 });
const B = `http://127.0.0.1:${port}`;
const AUTH = { "x-sutradhar-probe-token": token };
const get = (p, headers = AUTH) =>
  fetch(B + p, { headers }).then(async (r) => ({
    code: r.status,
    acao: r.headers.get("access-control-allow-origin"),
    body: await r.json(),
  }));
const post = (p, body, headers = {}) =>
  fetch(B + p, {
    method: "POST",
    headers: { ...AUTH, "content-type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  }).then(async (r) => ({
    code: r.status,
    acao: r.headers.get("access-control-allow-origin"),
    body: await r.json(),
  }));
/** Raw HTTP for what fetch() forbids setting (the Host header). */
function rawRequest({ host, omitHost = false }) {
  return new Promise((resolve, reject) => {
    const headers = { ...AUTH };
    if (host) headers.host = host;
    const req = http.request(`${B}/status`, { headers, setHost: false }, (res) => {
      let raw = "";
      res.on("data", (c) => (raw += c));
      res.on("end", () => {
        // A refusal may come from this bridge or from node's own
        // HTTP/1.1 parser (which rejects a missing Host before any
        // handler runs) - so the body may not be ours.
        let json = null;
        try {
          json = raw ? JSON.parse(raw) : null;
        } catch { /* non-JSON refusal body */ }
        resolve({ code: res.statusCode, json });
      });
    });
    req.on("error", reject);
    req.end();
  });
}
/** Poll exactly as the page would, over raw http so we can read the held response. */
function pollAsPage(probeId) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      `${B}/probe/poll`,
      { method: "POST", headers: { ...AUTH, "content-type": "application/json" } },
      (res) => {
        let raw = "";
        res.on("data", (c) => (raw += c));
        res.on("end", () => resolve(JSON.parse(raw)));
      },
    );
    req.on("error", reject);
    req.end(JSON.stringify({ probeId, pageUrl: "http://localhost:5173/manual", stateKeys: [], console: [], network: [] }));
  });
}

// ── trust: the unauthenticated world is refused with reasons ─────────────
await test("budget probe-auth: generated token carries at least 128 bits", () => {
  // hex = 4 bits/char; the bridge generates 32 CSPRNG bytes (256 bits).
  assert.ok(token.length >= 32 && /^[0-9a-f]+$/.test(token), `token too weak: ${token.length} chars`);
});
await test("request with no token is a 403 naming the header", async () => {
  const { code, body } = await get("/status", {});
  assert.equal(code, 403);
  assert.match(body.error, /x-sutradhar-probe-token/);
});
await test("request with a wrong token is a 403", async () => {
  const { code } = await get("/status", { "x-sutradhar-probe-token": "nope" });
  assert.equal(code, 403);
});
await test("preflight-less simple POST cannot reach a handler", async () => {
  // What a hostile webpage can send cross-origin without preflight: a
  // text/plain body, no custom headers. It dies at the gate even though
  // the body would otherwise be valid JSON for /eval.
  const { code, body } = await post("/eval", '{"expr":"1"}', {
    "content-type": "text/plain",
    "x-sutradhar-probe-token": "",
  });
  assert.equal(code, 403);
  assert.match(body.error, /refused/);
});
await test("rebound Host header is a 403 naming the check", async () => {
  const body = await rawRequest({ host: "evil.example" });
  assert.equal(body.code, 403);
  assert.match(body.json.error, /Host/);
});
await test("missing Host header is refused before any handler", async () => {
  const body = await rawRequest({ omitHost: true });
  // node's own HTTP/1.1 parser answers this one (400) - the contract is
  // "no Host means no service", not whose status code says so.
  assert.ok(body.code === 400 || body.code === 403, `expected refusal, got ${body.code}`);
});
await test("browser preflight succeeds but grants no permission", async () => {
  const res = await fetch(B + "/eval", {
    method: "OPTIONS",
    headers: {
      origin: "https://evil.example",
      "access-control-request-method": "POST",
      "access-control-request-headers": "content-type,x-sutradhar-probe-token",
    },
  });
  assert.equal(res.status, 204);
  assert.equal(res.headers.get("access-control-allow-origin"), null);
});
await test("no CORS permission on any verdict: 200, 403, 404", async () => {
  assert.equal((await get("/status")).acao, null);
  assert.equal((await get("/status", {})).acao, null);
  const missing = await get("/definitely-not-a-path");
  assert.equal(missing.code, 404);
  assert.equal(missing.acao, null);
});

// ── with no page connected: honest 503s, not empty 200s ──────────────────
await test("status: disconnected before any probe", async () => {
  const { body } = await get("/status");
  assert.equal(body.connected, false);
});
await test("state query with no page is a 503 with a reason", async () => {
  const { code, body } = await get("/state/cart");
  assert.equal(code, 503);
  assert.match(body.error, /no page connected/);
});

// ── connect a real ProbeCore (the browser's exact code path) ─────────────
const app = { cart: { items: 2, total: 84.5 }, user: "asha" };
const core = new ProbeCore({
  serverUrl: B,
  fetchImpl: fetch,
  token,
  allowEval: true,
  evalFn: (expr) => Function(`"use strict"; return (${expr})`)(),
  pageUrl: () => "http://localhost:5173/checkout",
});
core.expose("cart", () => app.cart);
core.expose("throws", () => {
  throw new Error("getter exploded");
});
core.recordConsole("error", "TypeError: x is undefined");
core.recordNetwork({ method: "GET", url: "/api/cart", status: 200, ok: true, ms: 41 });
core.recordNetwork({ method: "POST", url: "/api/pay", status: 500, ok: false, ms: 230 });
core.start();
await new Promise((r) => setTimeout(r, 300)); // first poll lands

await test("status: connected, page URL and state keys visible", async () => {
  const { body } = await get("/status");
  assert.equal(body.connected, true);
  assert.equal(body.pageUrl, "http://localhost:5173/checkout");
  assert.deepEqual(body.stateKeys.sort(), ["cart", "throws"]);
});
await test("console buffer reached the bridge", async () => {
  const { body } = await get("/console?level=error");
  assert.equal(body.entries.length, 1);
  assert.match(body.entries[0].text, /TypeError/);
});
await test("network buffer + match filter", async () => {
  const { body } = await get("/network?match=/api/pay");
  assert.equal(body.entries.length, 1);
  assert.equal(body.entries[0].status, 500);
});
await test("state query returns CURRENT value via round-trip", async () => {
  app.cart.items = 3; // mutate AFTER expose: getter must see it
  const { code, body } = await get("/state/cart");
  assert.equal(code, 200);
  assert.equal(body.value.items, 3);
});
await test("unknown state name errors and lists what exists", async () => {
  const { code, body } = await get("/state/nope");
  assert.equal(code, 400);
  assert.match(body.error, /no state named "nope"/);
  assert.match(body.error, /cart/);
});
await test("a getter that throws is an answer, not a dead loop", async () => {
  const { code, body } = await get("/state/throws");
  assert.equal(code, 400);
  assert.match(body.error, /getter exploded/);
});
await test("eval round-trip", async () => {
  const { code, body } = await post("/eval", { expr: "1 + 2" });
  assert.equal(code, 200);
  assert.equal(body.value, 3);
});
await test("clear resets buffers", async () => {
  await post("/clear", {});
  const { body } = await get("/console");
  assert.equal(body.entries.length, 0);
});

// ── eval disabled: refuse, never fabricate ───────────────────────────────
await test("eval disabled is an explicit refusal", async () => {
  core.allowEval = false;
  const { code, body } = await post("/eval", { expr: "1" });
  assert.equal(code, 400);
  assert.match(body.error, /eval disabled/);
  core.allowEval = true;
});

// ── dead page: bounded 504, never a hang ─────────────────────────────────
await test("query against a stopped page times out honestly", async () => {
  await core.stop();
  // NB: this waits for the server's QUERY_TIMEOUT (10s) - the point IS the bound.
  const started = Date.now();
  const { code, body } = await get("/state/cart");
  assert.equal(code, 504);
  assert.match(body.error, /did not answer/);
  assert.ok(Date.now() - started < 15_000, "timeout was not bounded");
});

// ── the probe channel itself: impersonation dies, payloads are filtered ──
// (runs after the real core has stopped, so no live poller races these)
await test("/probe/poll without the token cannot impersonate a page", async () => {
  const res = await post(
    "/probe/poll",
    { probeId: "evil", pageUrl: "http://evil.example/", stateKeys: [], console: [], network: [] },
    { "x-sutradhar-probe-token": "" },
  );
  assert.equal(res.code, 403);
  // Non-vacuous: a page IS registered right now (the real core's drain);
  // the refused poll must NOT have overwritten it with the attacker's URL.
  const { body } = await get("/status");
  assert.notEqual(body.pageUrl, "http://evil.example/");
});
await test("/probe/poll with a malformed shape is a 400", async () => {
  const res = await post("/probe/poll", { probeId: "x" });
  assert.equal(res.code, 400);
  assert.match(res.body.error, /malformed poll/);
});
await test("/probe/result with a malformed shape is a 400, never a silent accept", async () => {
  const bad = await post("/probe/result", { id: 42, ok: "yes" });
  assert.equal(bad.code, 400);
  assert.match(bad.body.error, /malformed result/);
});
await test("a fabricated result reaches the agent field-filtered", async () => {
  // The page registers FIRST and its poll is held open by the bridge;
  // the agent query then flushes straight into that held poll. (Firing
  // the query first would race the staleness window - after the 20s
  // drain-hold plus this suite's 10s bounds, no page is recent enough.)
  const heldPromise = pollAsPage("manual-page");
  await new Promise((r) => setTimeout(r, 100)); // registration lands
  const agentAnswer = get("/state/cart");
  const held = await heldPromise;
  const q = (held.queries || []).find((e) => e.kind === "state" && e.arg === "cart");
  assert.ok(q, "the held poll should have flushed the pending state query");
  // The answer carries junk a hostile channel might add; only validated
  // fields may reach the waiter.
  const ack = await post("/probe/result", { id: q.id, ok: true, value: app.cart, injected: "hostile junk" });
  assert.equal(ack.code, 200);
  const { body } = await agentAnswer;
  assert.equal(body.value.items, app.cart.items);
  assert.equal(body.injected, undefined, "junk fields must be stripped before the waiter resolves");
});

// ── unbounded reads: our own front door refuses them too ────────────────
await test("oversized body is a 413 with the cap stated", async () => {
  const big = JSON.stringify({ expr: "x".repeat(5_200_000) });
  const res = await post("/eval", big);
  assert.equal(res.code, 413);
  assert.match(res.body.error, /exceeds/);
});

await close();

// ── report ───────────────────────────────────────────────────────────────
let failed = 0;
for (const [name, out] of results) {
  console.log(`  ${out === "ok" ? "ok " : "FAIL"} ${name}${out === "ok" ? "" : "  <- " + out}`);
  if (out !== "ok") failed++;
}
console.log(`\n[probe-selftest] ${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
