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
   ```
2. Install the probe in your app entry, dev only:
   ```js
   if (import.meta.env.DEV) {
     const { installProbe } = await import("./probe/browser.mjs");
     installProbe({
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
   curl -s http://127.0.0.1:7071/status
   ```

## What the agent can do

```bash
curl -s http://127.0.0.1:7071/status                 # page connected? which URL? what state exists?
curl -s http://127.0.0.1:7071/console?level=error    # everything that threw
curl -s http://127.0.0.1:7071/network?match=/api/pay # did the request fire, with what status, how slow
curl -s http://127.0.0.1:7071/state/cart             # LIVE app state, not a snapshot
curl -s -X POST http://127.0.0.1:7071/eval -H 'content-type: application/json' -d '{"expr":"document.title"}'
curl -s -X POST http://127.0.0.1:7071/clear          # reset buffers between steps
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
caught a live contract bug the day it was written). Run it:

```bash
node js/probe/selftest.mjs
```

## Security posture, stated plainly

This is a development tool in the same trust class as an open devtools
port. The bridge binds `127.0.0.1` only; the installer refuses non-local
bridge URLs; `allowEval` is off by default; and the probe must be behind a
dev-only guard (`import.meta.env.DEV`) so it never ships in a production
bundle. Do not weaken any of those four lines.
