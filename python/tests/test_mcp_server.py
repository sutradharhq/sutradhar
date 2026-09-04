# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""The MCP server, driven as a REAL stdio subprocess.

Not one test in this file imports a handler and calls it. The seam an agent
uses is a process reading newline-delimited JSON-RPC on stdin and writing it
on stdout (doctrine 2.3), and a server that passes when poked in-process and
fails over a pipe is the exact shape of the tested-but-half-dead fix
`verify_guard` exists to catch.

The load-bearing distinction, asserted from both sides:

  - a guard that RAN and found something is a RESULT (`isError: false`,
    verdict in `structuredContent`), because a red guard is the tool
    working;
  - a guard that could NOT run is a JSON-RPC error naming the INSTRUMENT,
    because no measurement was taken.

Get that backwards and the agent is told its call failed and should be
retried, about a call that succeeded and returned bad news - the R3-1 scar
class (doctrine 2.4) reproduced inside the tool meant to prevent it.

The client here is deliberately written from scratch rather than reusing
`mcp_server._Client`: a shared client would break identically under a
mutation and both sides would agree, which is how an instrument and its
subject stop being independent.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import sutradhar_guards
from sutradhar_guards.budget import budget, get_budget
from sutradhar_guards.mcp_server import (
    BY_NAME,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    LEGACY_VERSIONS,
    MAX_OUTPUT_BYTES,
    METHOD_NOT_FOUND,
    META_CLIENT_CAPS,
    META_VERSION,
    MODERN_VERSIONS,
    PARSE_ERROR,
    SUPPORTED_VERSIONS,
    TOOLS,
    UNSUPPORTED_PROTOCOL_VERSION,
    cap_output,
)

PKG = Path(sutradhar_guards.__path__[0])
PKG_PARENT = PKG.parent
REPO_ROOT = PKG_PARENT.parent
SERVER = PKG / "mcp_server.py"
DESIGN = REPO_ROOT / "docs" / "design"

MODERN_META = {
    META_VERSION: MODERN_VERSIONS[0],
    META_CLIENT_CAPS: {},
    "io.modelcontextprotocol/clientInfo": {"name": "pytest", "version": "1"},
}


class Server:
    """A real subprocess speaking real newline-delimited JSON-RPC."""

    def __init__(self, env_extra: dict | None = None, cwd: Path = REPO_ROOT):
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(PKG_PARENT), env["PYTHONPATH"]] if env.get("PYTHONPATH")
            else [str(PKG_PARENT)]
        )
        env.update(env_extra or {})
        self.proc = subprocess.Popen(
            [sys.executable, "-u", str(SERVER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1, cwd=str(cwd), env=env,
        )
        self._id = 0
        self.raw_lines: list[str] = []

    # -- transport ---------------------------------------------------------
    def send_line(self, line: str) -> dict:
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        raw = self.proc.stdout.readline()
        assert raw, "the server closed stdout instead of answering"
        self.raw_lines.append(raw)
        return json.loads(raw)

    def request(self, method: str, params: dict | None = None,
                modern: bool = True, request_id=None) -> dict:
        self._id += 1
        body = dict(params or {})
        if modern:
            body["_meta"] = dict(MODERN_META)
        return self.send_line(json.dumps({
            "jsonrpc": "2.0", "id": self._id if request_id is None else request_id,
            "method": method, "params": body}))

    def notify(self, method: str, params: dict | None = None) -> None:
        self.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "method": method, "params": params or {}}) + "\n")
        self.proc.stdin.flush()

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        return self.request("tools/call",
                            {"name": name, "arguments": arguments or {}})

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=30)
        except Exception:  # noqa: BLE001
            self.proc.kill()


@pytest.fixture
def server():
    s = Server()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def clean_tree(tmp_path):
    d = tmp_path / "clean"
    d.mkdir()
    (d / "ok.py").write_text(
        'def q(conn, name):\n'
        '    return conn.execute("SELECT * FROM t WHERE n = ?", (name,))\n'
    )
    return d


@pytest.fixture
def dirty_tree(tmp_path):
    d = tmp_path / "dirty"
    d.mkdir()
    (d / "bad.py").write_text(
        'def q(conn, name):\n'
        '    return conn.execute(f\'SELECT * FROM t WHERE n = "{name}"\')\n'
    )
    return d


# ── the tool table, as a class ratchet ──────────────────────────────────────

def test_the_table_actually_has_tools():
    """Guards the guard: an empty TOOLS would make every parametrised test
    below vacuously pass (doctrine 3.6)."""
    assert len(TOOLS) >= 9, f"expected the full tool set, found {len(TOOLS)}"


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["name"])
def test_every_tool_has_a_schema_and_a_result_code_partition(tool):
    """A class ratchet, not nine point tests (doctrine 2.1), so a tool added
    later is covered the day it lands.

    `result_codes` is the column most likely to be wrong, because it has no
    safe default: a tool with an empty partition reports every verdict it
    ever reaches - including exit 0 - as an instrument failure.
    """
    schema = tool["inputSchema"]
    assert schema["type"] == "object"
    assert isinstance(schema["properties"], dict) and schema["properties"]
    assert schema.get("additionalProperties") is False, (
        f"{tool['name']} accepts unknown arguments. An unrecognised argument "
        f"must be refused for the same reason an unrecognised FLAG is: a "
        f"silently dropped typo runs a different check than the caller asked "
        f"for and reports its exit code as the answer."
    )
    for required in schema.get("required", []):
        assert required in schema["properties"], (
            f"{tool['name']} requires {required!r}, which its schema does not "
            f"describe - an agent cannot supply it")
    assert tool["result_codes"], f"{tool['name']} declares no result_codes"
    assert 0 in tool["result_codes"], (
        f"{tool['name']} does not treat exit 0 as a verdict, so a passing "
        f"guard would be reported as a broken instrument")
    assert isinstance(tool["default_timeout"], int) and tool["default_timeout"] > 0
    assert len(tool["description"]) > 120, (
        f"{tool['name']}'s description is too thin for an agent to route on")


def test_verify_guards_exit_2_is_a_verdict_and_everyone_elses_is_not():
    """The partition that a single shared exit-code table would get wrong.

    `verify_guard` exit 2 is INCONCLUSIVE - a deliberate tri-state verdict
    meaning "I could not tell", which is a finding. Every other guard uses
    exit 2 for a usage error, which is the caller's or this server's fault.
    """
    assert BY_NAME["verify_guard"]["result_codes"][2] == "INCONCLUSIVE"
    for name in ("budget_check", "rounds_check", "swallow_lint",
                 "interpolation_lint", "framework_only"):
        assert 2 not in BY_NAME[name]["result_codes"], (
            f"{name} treats exit 2 as a verdict, but exit 2 is its "
            f"unknown-flag/bad-path refusal - an instrument failure")
    for name in ("obsgate_check", "obsgate_snapshot", "obsgate_effects"):
        assert 2 not in BY_NAME[name]["result_codes"]
        assert BY_NAME[name]["result_codes"][3] == "INCONCLUSIVE"
        assert BY_NAME[name]["result_codes"][4] == "FROZEN"


def test_verify_guards_exit_2_arrives_as_a_verdict(server, tmp_path):
    """The partition, asserted at the RUNTIME seam rather than in the table.

    Found by mutation: collapsing `result_codes` to one shared
    `{0: OK, 1: FINDINGS, 2: OK}` lookup inside `run_tool` left the table
    test above perfectly green, because that test reads the declaration and
    never exercises the code path that consults it. A declaration is not an
    effect (doctrine 3.6).

    A directory that is not a git repository makes `verify_guard` exit 2 =
    INCONCLUSIVE, which is a deliberate tri-state verdict meaning "I could
    not tell". That is a finding, and must arrive as a RESULT.
    """
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    # `repo` outside this server's own tree is refused by default (R16-3), so
    # the server that answers this one is told, explicitly, to go anywhere.
    s = Server(env_extra={"SUTRADHAR_MCP_ANY_REPO": "1"})
    try:
        res = s.call_tool("verify_guard",
                          {"guard_cmd": "true", "repo": str(outside)})
    finally:
        s.close()
    assert "error" not in res, (
        f"verify_guard's INCONCLUSIVE was reported as an instrument failure. "
        f"'I could not tell' is an answer, not a crash: {res.get('error')}")
    sc = res["result"]["structuredContent"]
    assert sc["exit_code"] == 2
    assert sc["verdict"] == "INCONCLUSIVE"
    assert sc["ok"] is False
    assert res["result"]["isError"] is False


def test_another_guards_exit_2_arrives_as_an_instrument_failure(server, tmp_path):
    """The other half of the same runtime assertion, and the reason a single
    shared exit-code table is wrong.

    `rounds` exits 2 when there is nothing to check. That is a usage error -
    the caller pointed it somewhere empty - and reporting it as a verdict
    would hand back a pass for a check that never ran, which is the vacuous
    green this whole toolkit exists to remove.
    """
    empty = tmp_path / "no-rounds"
    empty.mkdir()
    res = server.call_tool("rounds_check", {"rounds_dir": str(empty),
                                            "repo": str(REPO_ROOT)})
    assert "result" not in res, (
        f"a guard that found nothing to check returned the verdict "
        f"{res.get('result', {}).get('structuredContent', {}).get('verdict')!r} - "
        f"a pass for a check that never ran")
    assert res["error"]["code"] == INTERNAL_ERROR
    assert res["error"]["data"]["party"] == "instrument"
    assert res["error"]["data"]["exit_code"] == 2


# ── protocol: both eras ─────────────────────────────────────────────────────

def test_modern_discover_needs_no_handshake(server):
    """The current revision (2026-07-28) has no `initialize`. A client may
    send `server/discover` as its very first message."""
    res = server.request("server/discover")["result"]
    assert res["resultType"] == "complete"
    assert res["supportedVersions"] == list(SUPPORTED_VERSIONS)
    assert MODERN_VERSIONS[0] in res["supportedVersions"]
    assert "tools" in res["capabilities"]


def test_legacy_initialize_handshake_still_works(server):
    """Most shipped clients still open with `initialize`. Dual-era, which
    the spec permits explicitly."""
    res = server.request("initialize", {
        "protocolVersion": LEGACY_VERSIONS[-1],
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "1"},
    }, modern=False)["result"]
    assert res["protocolVersion"] == LEGACY_VERSIONS[-1]
    assert res["serverInfo"]["name"]
    server.notify("notifications/initialized")
    assert "result" in server.request("tools/list", modern=False)


def test_notifications_get_no_response(server):
    """A notification has no id and MUST NOT be answered. If the server
    replied, the next read would return the stale reply and every
    subsequent id would be off by one."""
    server.request("initialize", {"protocolVersion": LEGACY_VERSIONS[-1]},
                   modern=False)
    server.notify("notifications/initialized")
    res = server.request("ping", modern=False)
    assert res["result"]["resultType"] == "complete"
    assert res["id"] == 2, "a notification was answered and shifted the stream"


def test_tools_list_returns_every_tool_with_a_schema(server):
    tools = server.request("tools/list")["result"]["tools"]
    assert {t["name"] for t in tools} == set(BY_NAME)
    for t in tools:
        assert t["inputSchema"]["type"] == "object"
        assert t["outputSchema"]["type"] == "object"
        assert t["description"]
    assert [t["name"] for t in tools] == [t["name"] for t in TOOLS], (
        "tools/list is not in a deterministic order; the spec asks for one "
        "so clients can cache the list")


def test_unsupported_protocol_version_is_refused_by_name(server):
    res = server.send_line(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/list",
        "params": {"_meta": {META_VERSION: "1900-01-01", META_CLIENT_CAPS: {}}}}))
    assert res["error"]["code"] == UNSUPPORTED_PROTOCOL_VERSION
    assert res["error"]["data"]["supported"] == list(SUPPORTED_VERSIONS)
    assert res["error"]["data"]["requested"] == "1900-01-01"


def test_unknown_method_is_method_not_found(server):
    res = server.request("tools/frobnicate")
    assert res["error"]["code"] == METHOD_NOT_FOUND


# ── results vs errors: the distinction the design turns on ──────────────────

def test_green_guard_is_a_result(server, clean_tree):
    res = server.call_tool("interpolation_lint",
                           {"paths": [str(clean_tree)], "keywords": "sql"})
    assert "error" not in res, res
    sc = res["result"]["structuredContent"]
    assert sc["verdict"] == "OK"
    assert sc["ok"] is True
    assert sc["exit_code"] == 0
    assert res["result"]["isError"] is False


def test_red_guard_is_a_result_not_an_error(server, dirty_tree):
    """THE test. A guard that found something is the tool WORKING.

    Reported as a JSON-RPC error it tells the agent "your call failed" about
    a call that succeeded and returned bad news; per the spec, `isError` is
    for feedback a model self-corrects on by adjusting parameters, and
    FINDINGS is not fixed by adjusting parameters. An error reads as
    flakiness, and flakiness gets retried instead of acted on.
    """
    res = server.call_tool("interpolation_lint",
                           {"paths": [str(dirty_tree)], "keywords": "sql"})
    assert "error" not in res, (
        f"a red guard came back as a JSON-RPC error: {res.get('error')}")
    result = res["result"]
    sc = result["structuredContent"]
    assert sc["verdict"] == "FINDINGS"
    assert sc["ok"] is False
    assert sc["exit_code"] == 1
    assert result["isError"] is False, (
        "a red guard set isError, which means 'retry with adjusted "
        "parameters' - it is not a call the agent should retry")
    assert "bad.py" in sc["stdout"], "the finding itself did not reach the agent"
    assert sc["command"].endswith(("--keywords sql", "sql")) or "interpolation_lint" \
        in sc["command"]


def test_red_and_green_differ_only_in_the_verdict(server, clean_tree, dirty_tree):
    """A verdict that never varies is decoration. Both calls must reach the
    same SHAPE with opposite answers, or one of them is not being computed."""
    green = server.call_tool("interpolation_lint",
                             {"paths": [str(clean_tree)], "keywords": "sql"})
    red = server.call_tool("interpolation_lint",
                           {"paths": [str(dirty_tree)], "keywords": "sql"})
    g, r = green["result"]["structuredContent"], red["result"]["structuredContent"]
    assert (g["verdict"], r["verdict"]) == ("OK", "FINDINGS")
    assert g["ok"] is True and r["ok"] is False
    assert set(g) == set(r)


def test_instrument_failure_is_an_error_naming_the_instrument(tmp_path, clean_tree):
    """A guard that could not RUN took no measurement, and must never be
    allowed to look like one. The message names the failing party."""
    empty = tmp_path / "no-guards"
    empty.mkdir()
    s = Server(env_extra={"SUTRADHAR_MCP_GUARD_DIR": str(empty)})
    try:
        res = s.call_tool("interpolation_lint",
                          {"paths": [str(clean_tree)], "keywords": "sql"})
    finally:
        s.close()
    assert "result" not in res, (
        "a guard that does not exist produced a VERDICT - the server "
        "invented an answer about code it never checked")
    assert res["error"]["code"] == INTERNAL_ERROR
    assert res["error"]["data"]["party"] == "instrument"
    assert "instrument:" in res["error"]["message"]
    assert "interpolation_lint.py" in res["error"]["message"]


@pytest.mark.parametrize("arguments,why", [
    ({}, "missing the required `paths`"),
    ({"paths": []}, "an empty path list"),
    ({"paths": [str(REPO_ROOT)], "nosuchargument": 1}, "an unknown argument"),
    ({"paths": 7}, "a non-string path list"),
    ({"paths": [str(REPO_ROOT)], "strict": "yes"}, "a non-boolean flag"),
    ({"paths": [str(REPO_ROOT)], "timeout_s": 0}, "a non-positive timeout"),
    ({"paths": [str(REPO_ROOT)], "timeout_s": True}, "a boolean where an int goes"),
])
def test_bad_arguments_are_a_caller_error_not_a_verdict(server, arguments, why):
    res = server.call_tool("interpolation_lint", arguments)
    assert "result" not in res, f"{why} produced a verdict instead of an error"
    assert res["error"]["code"] == INVALID_PARAMS, why


def test_unknown_tool_is_an_error(server):
    res = server.call_tool("no_such_tool")
    assert res["error"]["code"] == INVALID_PARAMS
    assert "Unknown tool" in res["error"]["message"]


# ── `repo` confinement (R16-3) ──────────────────────────────────────────────
#
# These tools run guard CLIs in whatever `repo` names, and `verify_guard`
# runs the caller's own command there, as the user running the server. The
# arguments are written by a model. So `repo` is a boundary, not a hint.

def test_a_repo_outside_this_servers_tree_is_a_caller_error(server, tmp_path):
    elsewhere = tmp_path / "somebody-elses-checkout"
    elsewhere.mkdir()
    res = server.call_tool("interpolation_lint",
                           {"paths": [str(elsewhere)], "repo": str(elsewhere)})
    assert "result" not in res, (
        "a `repo` outside the server's own repository was accepted; these "
        "tools run commands there")
    assert res["error"]["code"] == INVALID_PARAMS, res["error"]
    assert res["error"]["data"]["party"] == "caller", (
        "an out-of-bounds argument is the caller's, not a broken instrument")
    assert str(elsewhere) in res["error"]["message"]


def test_a_repo_inside_this_servers_tree_is_fine(server, clean_tree):
    """The half that makes the refusal above mean something: a confinement
    that refused everything would pass that test and switch the tool off."""
    inside = REPO_ROOT / "python"
    res = server.call_tool("interpolation_lint",
                           {"paths": [str(clean_tree)], "repo": str(inside)})
    assert "error" not in res, res.get("error")
    assert res["result"]["structuredContent"]["cwd"] == str(inside)


def test_the_confinement_can_be_lifted_deliberately(tmp_path):
    """An override that has to be typed. The default is the boundary; the
    escape hatch exists and is named in the refusal message, so nobody has
    to guess at it."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "ok.py").write_text("x = 1\n")
    s = Server(env_extra={"SUTRADHAR_MCP_ANY_REPO": "1"})
    try:
        res = s.call_tool("interpolation_lint",
                          {"paths": [str(elsewhere)], "repo": str(elsewhere)})
    finally:
        s.close()
    assert "error" not in res, res.get("error")
    assert res["result"]["structuredContent"]["verdict"] == "OK"


def test_a_server_outside_a_git_repo_is_confined_to_its_own_cwd(tmp_path):
    """No git toplevel, no repository to confine to - so the cwd is the
    boundary. The failure to avoid is falling back to "anywhere"."""
    home = tmp_path / "home"
    home.mkdir()
    (home / "ok.py").write_text("x = 1\n")
    away = tmp_path / "away"
    away.mkdir()
    s = Server(cwd=home)
    try:
        inside = s.call_tool("interpolation_lint",
                             {"paths": [str(home)], "repo": str(home)})
        outside = s.call_tool("interpolation_lint",
                              {"paths": [str(away)], "repo": str(away)})
    finally:
        s.close()
    assert "error" not in inside, inside.get("error")
    assert outside["error"]["code"] == INVALID_PARAMS, outside


# ── the session survives bad input ──────────────────────────────────────────

def test_malformed_request_does_not_kill_the_session(server, clean_tree):
    """A bad line must cost that request, not the conversation the agent is
    mid-task in."""
    bad = server.send_line("{this is not json")
    assert bad["error"]["code"] == PARSE_ERROR
    assert bad["id"] is None

    not_rpc = server.send_line(json.dumps({"hello": "world"}))
    assert not_rpc["error"]["code"] == -32600

    wrong_type = server.send_line(json.dumps(
        {"jsonrpc": "2.0", "id": 99, "method": 12}))
    assert wrong_type["error"]["code"] == -32600

    still_alive = server.call_tool("interpolation_lint",
                                   {"paths": [str(clean_tree)], "keywords": "sql"})
    assert still_alive["result"]["structuredContent"]["verdict"] == "OK", (
        "the server stopped serving after a malformed request")


def test_no_message_ever_contains_an_embedded_newline(server, dirty_tree):
    """The transport forbids it, and a guard's multi-line stdout would
    produce one on every single call if the encoder were bypassed."""
    server.request("tools/list")
    server.call_tool("interpolation_lint",
                     {"paths": [str(dirty_tree)], "keywords": "sql"})
    assert server.raw_lines
    for raw in server.raw_lines:
        assert raw.endswith("\n")
        assert "\n" not in raw[:-1], "a message carried an embedded newline"
        json.loads(raw)


# ── the output cap ──────────────────────────────────────────────────────────

def test_cap_output_truncates_and_reports_the_true_total():
    text, cut, total = cap_output("x" * 100, limit=10)
    assert (len(text), cut, total) == (10, True, 100)
    text, cut, total = cap_output("short", limit=10)
    assert (text, cut, total) == ("short", False, 5)


def test_output_cap_truncates_and_says_so(server, tmp_path):
    """End to end, through the real seam, with a guard that really does
    print more than the cap.

    An MCP tool result goes straight into a model's context window, so an
    uncapped result is the doctrine 2.6 unbounded-read class with a more
    expensive consumer. A SILENT cut is worse than the flood: a partial
    finding list read as a complete one is a wrong answer wearing a right
    one's shape.
    """
    big = tmp_path / "big"
    big.mkdir()
    lines = ["def q(conn, v):", "    return ["]
    lines += [f"        f'SELECT * FROM t{i} WHERE n = \"{{v}}\"'," for i in range(2500)]
    lines += ["    ]", ""]
    (big / "big.py").write_text("\n".join(lines))

    res = server.call_tool("interpolation_lint",
                           {"paths": [str(big)], "keywords": "sql"})
    sc = res["result"]["structuredContent"]

    assert sc["stdout_total_bytes"] > MAX_OUTPUT_BYTES, (
        "the fixture did not produce enough output to exercise the cap; this "
        "test would pass vacuously")
    assert sc["stdout_truncated"] is True, "output over the cap was not capped"
    assert len(sc["stdout"].encode("utf-8")) <= MAX_OUTPUT_BYTES
    assert sc["output_cap_bytes"] == MAX_OUTPUT_BYTES

    text = res["result"]["content"][0]["text"]
    assert "TRUNCATED" in text, "the cut was silent"
    assert f"{sc['stdout_total_bytes']:,}" in text, (
        "the truncation notice does not say how much was withheld, so the "
        "agent cannot tell a long list from a capped one")


def test_output_cap_matches_the_design_note():
    """Pin the mirror between the note and the constant, so a change to
    either fails rather than letting the documented contract drift away
    from the enforced one."""
    note = (DESIGN / "mcp-server.md").read_text(encoding="utf-8")
    declared = {int(m.replace(",", "")) for m in
                re.findall(r"([\d,]{4,})\s*(?:bytes|\(`MAX_OUTPUT_BYTES`\))", note)}
    assert MAX_OUTPUT_BYTES in declared, (
        f"docs/design/mcp-server.md declares {sorted(declared)} as its output "
        f"cap; the code enforces {MAX_OUTPUT_BYTES}")


# ── the declared envelope ───────────────────────────────────────────────────

def test_mcp_roundtrip_holds_its_declared_envelope():
    """`b.n` IS the 200 declared in docs/design/mcp-server.md. Nobody
    hand-picks a comfortable number of round trips here.

    The ceiling is a tripwire, not a fit. The shape that breaks it is
    per-call work that should be per-session - re-reading the guard
    directory, or re-spawning a subprocess per `tools/list` - which lands
    one to two orders of magnitude above it.
    """
    n = get_budget("mcp-roundtrip", root=DESIGN).n
    s = Server()
    try:
        assert "result" in s.request("server/discover")  # warm, excluded
        with budget("mcp-roundtrip", root=DESIGN) as b:
            for _ in range(b.n):
                assert "tools" in s.request("tools/list")["result"]
    finally:
        s.close()
    assert n == b.n


# ── the CLI seam ────────────────────────────────────────────────────────────

def _cli(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(PKG_PARENT), env["PYTHONPATH"]] if env.get("PYTHONPATH")
        else [str(PKG_PARENT)]
    )
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(SERVER), *args], capture_output=True, text=True,
        cwd=str(REPO_ROOT), env=env, timeout=300,
    )


def test_unknown_flag_exits_2():
    """Without this, exit 0 from `--selfcheck` proves only that the module
    imported. Worse here than elsewhere: a swallowed typo does not run the
    default scan, it starts a SERVER, and a process sitting there reading
    stdin looks exactly like one that passed.
    """
    proc = _cli("--zzz-not-a-real-flag")
    assert proc.returncode == 2, (proc.stdout, proc.stderr)
    assert "unknown flag" in proc.stderr


def test_selfcheck_exits_0_and_names_what_it_proved():
    proc = _cli("--selfcheck")
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "mcp-server" in proc.stdout, "a silent pass cannot be told apart " \
                                        "from a check that never ran"
    for claim in ("tools", "FINDINGS", "RESULT"):
        assert claim in proc.stdout, (
            f"the selfcheck's success line does not mention {claim!r}, so it "
            f"does not say what it proved")


def test_selfcheck_actually_calls_a_tool():
    """The guard on the guard (doctrine 2.2, applied to the selfcheck).

    Point the server at a directory holding no guards. If the selfcheck
    really invokes a tool over the wire, every tool call becomes an
    instrument failure and it must go RED. A selfcheck that only handshakes
    and lists tools would not notice, and would report green - which is the
    `--selfcheck`-that-checks-nothing class this repo already has a scar
    from.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as empty:
        proc = _cli("--selfcheck", env_extra={"SUTRADHAR_MCP_GUARD_DIR": empty})
    assert proc.returncode != 0, (
        "the selfcheck passed with no guards on disk, so it never actually "
        "called one:\n" + proc.stdout + proc.stderr)
    assert "SELFCHECK FAILED" in proc.stderr


def test_help_exits_0_and_describes_the_server():
    proc = _cli("--help")
    assert proc.returncode == 0
    assert "mcp_server" in proc.stdout
