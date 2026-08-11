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
 * and no page at all must 503. A tool for verifying honesty must itself
 * degrade honestly.
 *
 * Run: node selftest.mjs   (exit 0 = pass; any failure exits nonzero)
 */
import assert from "node:assert/strict";
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

const { port, close } = await createBridge({ port: 0 });
const B = `http://127.0.0.1:${port}`;
const get = (p) => fetch(B + p).then(async (r) => ({ code: r.status, body: await r.json() }));
const post = (p, body) =>
  fetch(B + p, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  }).then(async (r) => ({ code: r.status, body: await r.json() }));

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

await close();

// ── report ───────────────────────────────────────────────────────────────
let failed = 0;
for (const [name, out] of results) {
  console.log(`  ${out === "ok" ? "ok " : "FAIL"} ${name}${out === "ok" ? "" : "  <- " + out}`);
  if (out !== "ok") failed++;
}
console.log(`\n[probe-selftest] ${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
