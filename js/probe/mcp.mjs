#!/usr/bin/env node
/**
 * MCP adapter for the Sutradhar probe bridge - optional sugar.
 *
 * The bridge is already usable by any agent with a shell (curl). This
 * adapter additionally exposes it as an MCP stdio server for clients that
 * prefer tools over shell, with zero dependencies: MCP's stdio transport
 * is newline-delimited JSON-RPC 2.0, small enough to implement directly.
 *
 * Register (Claude Code):
 *   claude mcp add sutradhar-probe -- node /path/to/probe/mcp.mjs
 *
 * The bridge must be running (node server.mjs) and the app open with the
 * probe installed.
 */
import readline from "node:readline";

const BRIDGE = process.env.SUTRADHAR_PROBE_URL || "http://127.0.0.1:7071";

const TOOLS = [
  {
    name: "probe_status",
    description:
      "Is a page connected to the probe bridge; its URL, exposed state keys, buffer counts.",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "probe_console",
    description:
      "Console errors/warnings captured from the running page since start (or last clear).",
    inputSchema: {
      type: "object",
      properties: { level: { type: "string", enum: ["error", "warn"] } },
    },
  },
  {
    name: "probe_network",
    description:
      "Summaries of network requests the page made: method, url, status, duration, response body head.",
    inputSchema: {
      type: "object",
      properties: { match: { type: "string", description: "substring filter on URL" } },
    },
  },
  {
    name: "probe_state",
    description:
      "Read a named piece of live app state the app exposed (probe_status lists the names).",
    inputSchema: {
      type: "object",
      properties: { name: { type: "string" } },
      required: ["name"],
    },
  },
  {
    name: "probe_eval",
    description:
      "Evaluate a JS expression in the running page (works only if the app opted in with allowEval).",
    inputSchema: {
      type: "object",
      properties: { expr: { type: "string" } },
      required: ["expr"],
    },
  },
  {
    name: "probe_clear",
    description: "Clear the console/network buffers (use between verification steps).",
    inputSchema: { type: "object", properties: {} },
  },
];

async function callBridge(name, args) {
  const get = (p) => fetch(`${BRIDGE}${p}`).then((r) => r.json());
  switch (name) {
    case "probe_status":
      return get("/status");
    case "probe_console":
      return get(`/console${args?.level ? `?level=${args.level}` : ""}`);
    case "probe_network":
      return get(`/network${args?.match ? `?match=${encodeURIComponent(args.match)}` : ""}`);
    case "probe_state":
      return get(`/state/${encodeURIComponent(args.name)}`);
    case "probe_eval":
      return fetch(`${BRIDGE}/eval`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ expr: args.expr }),
      }).then((r) => r.json());
    case "probe_clear":
      return fetch(`${BRIDGE}/clear`, { method: "POST" }).then((r) => r.json());
    default:
      throw new Error(`unknown tool ${name}`);
  }
}

const rl = readline.createInterface({ input: process.stdin });
const send = (msg) => process.stdout.write(JSON.stringify(msg) + "\n");

rl.on("line", async (line) => {
  if (!line.trim()) return;
  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return;
  }
  const { id, method, params } = msg;
  try {
    if (method === "initialize") {
      send({
        jsonrpc: "2.0", id,
        result: {
          protocolVersion: params?.protocolVersion || "2025-06-18",
          capabilities: { tools: {} },
          serverInfo: { name: "sutradhar-probe", version: "0.2.0" },
        },
      });
    } else if (method === "notifications/initialized") {
      // notification - no response
    } else if (method === "ping") {
      send({ jsonrpc: "2.0", id, result: {} });
    } else if (method === "tools/list") {
      send({ jsonrpc: "2.0", id, result: { tools: TOOLS } });
    } else if (method === "tools/call") {
      const result = await callBridge(params.name, params.arguments || {});
      send({
        jsonrpc: "2.0", id,
        result: {
          content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
          isError: result && result.ok === false,
        },
      });
    } else if (id !== undefined) {
      send({
        jsonrpc: "2.0", id,
        error: { code: -32601, message: `method not found: ${method}` },
      });
    }
  } catch (e) {
    if (id !== undefined) {
      send({
        jsonrpc: "2.0", id,
        error: { code: -32000, message: String((e && e.message) || e) },
      });
    }
  }
});
