# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""R21-11: a check on which host may be read is a check on the first request
only, for as long as redirects are followed.

Found by the outside review of v0.5.2. The MCP server's loopback check judged
the `metrics` URL, and obsgate's fetch then followed a 302 from an allowed
loopback server to wherever its Location pointed - another port, a name, the
cloud metadata address - attempting a connection each time. obsgate now takes
`--redirects refuse`, which reports the Location as INCONCLUSIVE and fetches
nothing more, and the MCP server passes it for every URL a model chose unless
SUTRADHAR_MCP_ANY_URL=1. The CLI still follows by default, because there a
person named the URL.

Every test here counts requests at a real target server, so "not followed" is
witnessed as a request that never arrived rather than inferred from a message.
"""
from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import sutradhar_guards
from sutradhar_guards.obsgate import read_payload

PKG = Path(sutradhar_guards.__path__[0])
OBSGATE = PKG / "obsgate.py"
SERVER = PKG / "mcp_server.py"
BODY = b"# TYPE up gauge\nup 1\n"


@pytest.fixture
def redirect():
    """A loopback server answering 302 to a second loopback server, which
    serves metrics and records every request it receives."""
    hits: list = []

    class Target(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", str(len(BODY)))
            self.end_headers()
            self.wfile.write(BODY)

        def log_message(self, *args):
            pass

    target = http.server.HTTPServer(("127.0.0.1", 0), Target)
    location = f"http://127.0.0.1:{target.server_address[1]}/metrics"

    class Start(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    start = http.server.HTTPServer(("127.0.0.1", 0), Start)
    servers = (target, start)
    for srv in servers:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield {"url": f"http://127.0.0.1:{start.server_address[1]}/start",
               "location": location, "hits": hits}
    finally:
        for srv in servers:
            srv.shutdown()
            srv.server_close()


def test_the_library_follows_by_default_and_refuses_when_told(redirect):
    text, why = read_payload(redirect["url"], timeout=5)
    assert (text, why) == (BODY.decode(), ""), why
    assert redirect["hits"] == ["/metrics"]

    text, why = read_payload(redirect["url"], timeout=5, follow_redirects=False)
    assert text is None, text
    assert redirect["location"] in why and "not followed" in why, why
    assert redirect["hits"] == ["/metrics"], "the refused redirect reached its target"


def _cli(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(OBSGATE), *args], cwd=cwd,
                          capture_output=True, text=True, timeout=60)


def test_the_cli_reports_a_refused_redirect_as_inconclusive(redirect, tmp_path):
    out = tmp_path / "snap.json"
    refused = _cli(tmp_path, "snapshot", "--metrics", redirect["url"],
                   "--out", str(out), "--redirects", "refuse")
    assert refused.returncode == 3, refused
    assert redirect["location"] in refused.stderr, refused
    assert redirect["hits"] == [] and not out.exists(), refused

    followed = _cli(tmp_path, "snapshot", "--metrics", redirect["url"], "--out", str(out))
    assert followed.returncode == 0 and out.is_file(), followed
    assert redirect["hits"] == ["/metrics"]


def test_a_misspelt_redirect_mode_is_refused_not_guessed(tmp_path):
    proc = _cli(tmp_path, "snapshot", "--metrics", "x.txt", "--out", "s.json",
                "--redirects", "refuze")
    assert proc.returncode == 2, proc
    assert "--redirects must be follow or refuse" in proc.stderr, proc


def test_obsgate_check_refuses_it_too(redirect, tmp_path):
    """`check` reads through `gate` and `sample_payloads`, a different path
    from `snapshot`'s; a flag honoured by one reader and dropped by the other
    is a refusal with a hole in it. Two samples, so the refusal is carried
    through the sampling loop and not only its first pass."""
    floor = tmp_path / "floor.json"
    floor.write_text(json.dumps({"surfaces": [{"name": "up", "pattern": "^up$"}]}))
    refused = _cli(tmp_path, "check", "--metrics", redirect["url"], "--floor",
                   str(floor), "--redirects", "refuse", "--samples", "2")
    assert refused.returncode == 3, refused
    assert redirect["location"] in refused.stdout + refused.stderr, refused
    assert redirect["hits"] == [], refused

    followed = _cli(tmp_path, "check", "--metrics", redirect["url"], "--floor", str(floor))
    assert followed.returncode != 3, followed
    assert redirect["hits"] == ["/metrics"], followed


def _mcp_snapshot(cwd: Path, url: str, out: Path, env_extra: dict | None = None) -> dict:
    """One obsgate_snapshot call through the real MCP server over stdio."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SUTRADHAR_")}
    env.update(env_extra or {})
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "obsgate_snapshot",
                    "arguments": {"metrics": url, "out": str(out), "timeout_s": 60}}},
    ]
    proc = subprocess.run([sys.executable, "-u", str(SERVER)], cwd=cwd, env=env,
                          input="".join(json.dumps(m) + "\n" for m in messages),
                          capture_output=True, text=True, timeout=120)
    replies = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    matching = [r for r in replies if r.get("id") == 2]
    assert matching, f"no reply to the tool call: {proc.stdout!r} {proc.stderr!r}"
    return matching[0]


def test_the_mcp_server_does_not_follow_a_redirect_a_model_chose(redirect, tmp_path):
    out = tmp_path / "snap.json"
    res = _mcp_snapshot(tmp_path, redirect["url"], out)
    shown = json.dumps(res)
    assert "error" not in res, res
    assert "INCONCLUSIVE" in shown and redirect["location"] in shown, res
    assert redirect["hits"] == [] and not out.exists(), res


def test_the_operator_opt_in_follows_it(redirect, tmp_path):
    """The pair (6.7): with any host allowed, the redirect is followed and the
    target is read. Without this, the refusal above could be passing because
    the fetch had broken."""
    out = tmp_path / "snap.json"
    res = _mcp_snapshot(tmp_path, redirect["url"], out, {"SUTRADHAR_MCP_ANY_URL": "1"})
    assert "error" not in res and out.is_file(), res
    assert redirect["hits"] == ["/metrics"]
