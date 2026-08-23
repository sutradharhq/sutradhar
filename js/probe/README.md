# The Sutradhar probe - inner-loop runtime verification

Assert on a running app's actual state from an agent's terminal. Zero
dependencies on either side: the browser half is plain ESM, the bridge is
`node:http`, and the agent needs nothing but `curl` (an MCP adapter is
included for clients that prefer tools).

```
┌─────────────┐  long-poll   ┌──────────────┐   curl / MCP   ┌───────┐
│ running app │ ───────────► │ local bridge │ ◄───────────── │ agent │
│  (probe)    │ ◄─────────── │ 127.0.0.1    │                │       │
└─────────────┘   queries    └──────────────┘                └───────┘
```

## Setup

1. Start the bridge:
   ```bash
   node js/probe/server.mjs           # http://127.0.0.1:7071
   # → prints a shared token (or pass --token / SUTRADHAR_PROBE_TOKEN)
   ```
2. Install the probe in your app entry, dev only:
   ```js
   if (import.meta.env.DEV) {
     const { installProbe } = await import("./probe/browser.mjs");
     installProbe({
       token: "…the token the bridge printed…",
       expose: {
         route: () => window.location.pathname,
         cart:  () => useCartStore.getState(),
       },
       allowEval: true,   // opt-in: lets the agent evaluate expressions
     });
   }
   ```
3. Verify from the terminal:
   ```bash
   curl -s -H 'x-sutradhar-probe-token: <token>' http://127.0.0.1:7071/status
   ```
4. For the MCP adapter, export the same token:
   ```bash
   export SUTRADHAR_PROBE_TOKEN="<token>"
   ```

## What the agent can do

```bash
T='x-sutradhar-probe-token: <token>'
curl -s -H "$T" http://127.0.0.1:7071/status                 # page connected? which URL? what state exists?
curl -s -H "$T" http://127.0.0.1:7071/console?level=error    # everything that threw
curl -s -H "$T" http://127.0.0.1:7071/network?match=/api/pay # did the request fire, with what status, how slow
curl -s -H "$T" http://127.0.0.1:7071/state/cart             # LIVE app state, not a snapshot
curl -s -H "$T" -X POST http://127.0.0.1:7071/eval -H 'content-type: application/json' -d '{"expr":"document.title"}'
curl -s -H "$T" -X POST http://127.0.0.1:7071/clear          # reset buffers between steps
```

This replaces "take a screenshot and squint" in the inner loop: after an
edit, the agent checks that the request fired with a 200, the store holds
the new value, and the console is clean - runtime facts, not pixels.

MCP registration (optional):

```bash
claude mcp add sutradhar-probe -- node /path/to/js/probe/mcp.mjs
```

## Honesty contract

The probe polices honesty, so it degrades honestly itself:

- no page connected: state/eval return **503 with a stated reason**, never
  an empty 200;
- page frozen or navigating: queries **504 after a stated 10s bound**,
  never hang, never a fabricated value;
- eval without opt-in: an explicit refusal naming the switch;
- an unknown state name: an error that lists what IS exposed;
- a getter that throws: the exception text as the answer.

Every one of those paths is exercised by `selftest.mjs`, which runs the
REAL `ProbeCore` against the REAL bridge over real HTTP (the selftest
caught a live contract bug the day it was written). The trust refusals
are tested there too: no token, wrong token, the preflight-less POST a
hostile webpage can send, a rebound Host, malformed poll/result payloads,
and an oversized body. Run it:

```bash
node js/probe/selftest.mjs
```

## Security posture, stated plainly

This is a development tool in the same trust class as an open devtools
port. Five lines hold it (design note: [docs/design/probe-auth.md](../../docs/design/probe-auth.md)):

1. **Loopback only** - the bridge binds `127.0.0.1`.
2. **Shared token on every request** (`x-sutradhar-probe-token`) -
   generated at startup if not supplied, timing-safe compared, required
   by probe and agent alike. A request without it is a 403 naming the
   header.
3. **No CORS permission is ever sent** - every legitimate client is
   non-browser, so cross-origin reads die and preflighted custom-header
   requests are refused by the browser itself. A hostile webpage's one
   remaining move (the preflight-less simple POST) dies at the token gate.
4. **Host check** - DNS rebinding resolves `evil.example` to 127.0.0.1 but
   cannot forge its Host header; a non-loopback Host is a 403.
5. **Dev-only install** - `import.meta.env.DEV` around the install keeps
   the probe out of production bundles; the installer additionally refuses
   non-loopback bridge URLs (parsed with `new URL`, so userinfo tricks
   like `http://127.0.0.1@evil.example` do not pass).

`allowEval` still defaults to off. Do not weaken any of those five lines;
each exists because its absence was demonstrated in round 10.
