/**
 * ProbeCore - the environment-agnostic half of the Sutradhar runtime probe.
 *
 * Runs inside the page (installed by browser.mjs) OR inside a Node test
 * (the selftest drives this exact class), which is why it takes its fetch
 * implementation by injection and never touches the DOM. The selftest runs
 * the REAL probe code against the REAL bridge, so the protocol cannot
 * drift between the two halves; only the thin browser installer is
 * exercised by construction rather than by test.
 *
 * Responsibilities:
 *   - buffer console errors/warnings and network request summaries
 *   - hold a registry of named state getters the app exposes
 *   - long-poll the local bridge, piggybacking buffered events on each
 *     poll, and answer state/eval queries the bridge relays from an agent
 *
 * Transport is deliberately boring: HTTP long-polling with plain fetch.
 * No WebSocket, no deps, nothing to build.
 */

export class ProbeCore {
  /**
   * @param {object} opts
   * @param {string} opts.serverUrl        bridge origin, e.g. http://127.0.0.1:7071
   * @param {typeof fetch} opts.fetchImpl  injected fetch
   * @param {boolean} [opts.allowEval]     allow the agent to evaluate expressions
   * @param {(expr: string) => any} [opts.evalFn]  evaluator (browser: window.eval)
   * @param {() => string} [opts.pageUrl]  current page URL getter
   */
  constructor({ serverUrl, fetchImpl, allowEval = false, evalFn = null, pageUrl }) {
    this.serverUrl = serverUrl.replace(/\/$/, "");
    this.fetch = fetchImpl;
    this.allowEval = allowEval;
    this.evalFn = evalFn;
    this.pageUrl = pageUrl || (() => "");
    this.getters = new Map();
    this.consoleBuf = [];
    this.networkBuf = [];
    this.running = false;
    this.probeId = Math.random().toString(36).slice(2, 10);
  }

  /** Expose a named piece of app state. The getter runs per query, so the
   *  agent always sees CURRENT state, never a snapshot. */
  expose(name, getter) {
    this.getters.set(name, getter);
  }

  recordConsole(level, text) {
    this.consoleBuf.push({ level, text: String(text).slice(0, 2000), ts: Date.now() });
    if (this.consoleBuf.length > 500) this.consoleBuf.shift();
  }

  /** @param {{method:string,url:string,status:number,ms:number,ok:boolean,body?:string}} entry */
  recordNetwork(entry) {
    this.networkBuf.push({ ...entry, ts: Date.now() });
    if (this.networkBuf.length > 500) this.networkBuf.shift();
  }

  async handleQuery(q) {
    try {
      if (q.kind === "state") {
        const getter = this.getters.get(q.arg);
        if (!getter) {
          return {
            id: q.id, ok: false,
            error: `no state named "${q.arg}" - exposed: [${[...this.getters.keys()].join(", ")}]`,
          };
        }
        return { id: q.id, ok: true, value: await getter() };
      }
      if (q.kind === "eval") {
        if (!this.allowEval || !this.evalFn) {
          return {
            id: q.id, ok: false,
            error: "eval disabled - pass allowEval: true to installProbe (dev only)",
          };
        }
        return { id: q.id, ok: true, value: await this.evalFn(q.arg) };
      }
      return { id: q.id, ok: false, error: `unknown query kind "${q.kind}"` };
    } catch (e) {
      // An exception during a query is an ANSWER (the agent asked about
      // state that throws), never a reason to kill the poll loop.
      return { id: q.id, ok: false, error: String(e && e.message || e) };
    }
  }

  async _pollOnce() {
    const payload = {
      probeId: this.probeId,
      pageUrl: this.pageUrl(),
      stateKeys: [...this.getters.keys()],
      console: this.consoleBuf.splice(0),
      network: this.networkBuf.splice(0),
    };
    const res = await this.fetch(`${this.serverUrl}/probe/poll`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    for (const q of data.queries || []) {
      const result = await this.handleQuery(q);
      await this.fetch(`${this.serverUrl}/probe/result`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(result),
      });
    }
  }

  start() {
    if (this.running) return;
    this.running = true;
    const loop = async () => {
      while (this.running) {
        try {
          await this._pollOnce();
        } catch {
          // Bridge not up (yet): back off quietly. The probe must never
          // break the app it observes.
          await new Promise((r) => setTimeout(r, 2000));
        }
      }
    };
    this._loop = loop();
  }

  async stop() {
    this.running = false;
    // One drain so buffered events land server-side before shutdown.
    try { await this._pollOnce(); } catch { /* bridge already gone */ }
  }
}
