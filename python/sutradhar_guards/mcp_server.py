"""mcp_server - the guards as tools an agent calls MID-task, not after it.

Every other placement of these guards runs after the agent has stopped: CI
gates the pull request, the robustness loop reviews the finished work. Both
are right and both are slow. An agent that learns twenty minutes later that
the guard it wrote is decoration has already moved on.

This is the second placement. It is an MCP stdio server exposing nine guards
as tools, so an agent can ask `verify_guard` whether the guard it just wrote
actually goes red *while it is still writing it*, and get the answer in one
round trip. The design note is docs/design/mcp-server.md; it records the
spec URLs this was verified against and the numbers below.

    python mcp_server.py               # serve MCP over stdio
    python mcp_server.py --selfcheck   # spawn self, handshake, call a tool

Register (Claude Code):

    claude mcp add sutradhar -- python3 /path/to/sutradhar_guards/mcp_server.py

## Dual-era, because the protocol moved

The CURRENT protocol revision is `2026-07-28`, and it has NO handshake:
version, client identity and capabilities ride in every request's `_meta`,
and `server/discover` replaces `initialize`. The `initialize` /
`notifications/initialized` handshake is LEGACY (`2025-11-25` and earlier).
A server built from memory would speak only the legacy era, and by the
spec's own compatibility matrix a modern client talking to a legacy server
fails. So this server serves both, selecting era from how the client opens -
which the specification permits explicitly.

## The distinction this file turns on

MCP offers two ways to report trouble, and picking wrongly reproduces the
R3-1 scar inside the tool meant to prevent it: an instrument that cannot
tell "the subject failed" from "I failed" reports the wrong outage with
total confidence, and always reports it about the subject.

  - A guard that RAN and found something is a RESULT. Green or red, a
    verdict is a measurement. `DECORATION` is not a malformed call; it is
    the tool working. Returned with `isError: false` and the verdict in
    `structuredContent`.
  - A guard that could not run - file missing, spawn failed, timeout,
    unparseable exit code, bad arguments - is a JSON-RPC ERROR naming the
    INSTRUMENT as the failing party. No measurement was taken, and nothing
    is allowed to imply one was.

Exit codes are therefore partitioned per tool rather than globally. Exit 2
means INCONCLUSIVE for `verify_guard` (a deliberate tri-state verdict, and a
finding) and a usage error for every other guard (an instrument failure). A
single shared table would silently get one of those two backwards.

## Bounded output

A tool result goes straight into a model's context window, so an uncapped
one is the doctrine 2.6 unbounded-read class with a more expensive consumer:
it does not OOM a store, it evicts the agent's working memory. Each stream
is capped at MAX_OUTPUT_BYTES and truncation is STATED, never silent - a
partial finding list read as a complete one is worse than no list at all.
"""
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

SERVER_NAME = "sutradhar-guards"
SERVER_VERSION = "0.3.0"

# Verified against the specification on 2026-09-02; see docs/design/mcp-server.md
# for the page URLs. Newest first - `server/discover` reports this list, and a
# modern request naming anything outside it gets UnsupportedProtocolVersionError.
MODERN_VERSIONS = ("2026-07-28",)
LEGACY_VERSIONS = ("2025-11-25", "2025-06-18")
SUPPORTED_VERSIONS = MODERN_VERSIONS + LEGACY_VERSIONS

META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_CAPS = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

# Spec-defined JSON-RPC codes. The -32000..-32019 range is explicitly
# discouraged for new implementations, and -32020..-32099 belongs to the
# specification, so instrument failures use the standard -32603.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
UNSUPPORTED_PROTOCOL_VERSION = -32022

#: Captured bytes per stream per tool call. Declared in
#: docs/design/mcp-server.md, which `test_output_cap_matches_the_design_note`
#: pins to this constant so the note and the code cannot drift apart.
MAX_OUTPUT_BYTES = 65536

_KNOWN_FLAGS = {"--selfcheck", "--help", "-h"}


class RpcError(Exception):
    """A JSON-RPC error response. NOT how a red guard is reported."""

    def __init__(self, code: int, message: str, data: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def payload(self) -> dict:
        out: dict = {"code": self.code, "message": self.message}
        if self.data is not None:
            out["data"] = self.data
        return out


class InstrumentError(RpcError):
    """THIS SERVER failed, or the guard could not be run at all.

    Never raised because a guard reported a finding. The `party` field
    exists so a reader can never mistake our failure for the repo's,
    the endpoint's, or the guard's - doctrine 2.4, and the R3-1 scar.
    """

    def __init__(self, message: str, **extra: object) -> None:
        super().__init__(
            INTERNAL_ERROR,
            f"instrument: {message}",
            {"party": "instrument", **extra},
        )


def _log(message: str) -> None:
    """stderr only. stdout carries MCP messages and nothing else - the spec
    is explicit that a server MUST NOT write anything else there."""
    print(f"[sutradhar-mcp] {message}", file=sys.stderr)


# ── output capping ──────────────────────────────────────────────────────────

def cap_output(raw: str, limit: int = MAX_OUTPUT_BYTES) -> tuple[str, bool, int]:
    """Bound one captured stream. Returns (text, truncated, total_bytes).

    The ONLY function that turns subprocess output into something a caller
    sees, so there is no path to an uncapped result (doctrine 1.2). The
    total is always reported, because "1000 findings, showing 300" and "300
    findings" call for different actions and a silent cut cannot be told
    apart from the second one.
    """
    data = raw.encode("utf-8", errors="replace")
    total = len(data)
    if total <= limit:
        return raw, False, total
    return data[:limit].decode("utf-8", errors="ignore"), True, total


def _render_stream(name: str, text: str, truncated: bool, total: int) -> str:
    if not text and not truncated:
        return ""
    head = f"--- {name} ---\n{text}"
    if truncated:
        head += (
            f"\n[TRUNCATED: showing {len(text.encode('utf-8', 'replace')):,} of "
            f"{total:,} bytes. This {name} is INCOMPLETE - re-run the command "
            f"in a shell to see all of it.]"
        )
    return head


# ── argument reading ────────────────────────────────────────────────────────

def _bad_args(message: str) -> RpcError:
    return RpcError(INVALID_PARAMS, message, {"party": "caller"})


def _string(args: dict, key: str, *, required: bool = False,
            default: str | None = None) -> str | None:
    if key not in args or args[key] is None:
        if required:
            raise _bad_args(f"missing required argument {key!r}")
        return default
    value = args[key]
    if not isinstance(value, str) or not value:
        raise _bad_args(f"argument {key!r} must be a non-empty string, got {value!r}")
    return value


def _string_list(args: dict, key: str, *, required: bool = False) -> list[str]:
    if key not in args or args[key] is None:
        if required:
            raise _bad_args(f"missing required argument {key!r}")
        return []
    value = args[key]
    if isinstance(value, str):  # a lone path is a common and harmless slip
        value = [value]
    if not isinstance(value, list) or not all(
        isinstance(v, str) and v for v in value
    ):
        raise _bad_args(f"argument {key!r} must be an array of non-empty strings")
    if required and not value:
        raise _bad_args(f"argument {key!r} must name at least one path")
    return value


def _int(args: dict, key: str, *, default: int | None = None) -> int | None:
    if key not in args or args[key] is None:
        return default
    value = args[key]
    # bool is an int subclass and `samples: true` is a caller error, not a 1.
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _bad_args(f"argument {key!r} must be a positive integer, got {value!r}")
    return value


def _bool(args: dict, key: str, *, default: bool = False) -> bool:
    if key not in args or args[key] is None:
        return default
    if not isinstance(args[key], bool):
        raise _bad_args(f"argument {key!r} must be a boolean, got {args[key]!r}")
    return bool(args[key])


# ── the tool table ──────────────────────────────────────────────────────────
#
# `result_codes` is the load-bearing column: exit codes that mean the guard
# RAN and reached a verdict. Anything outside it is an instrument failure.
# There is no default - a tool added without one fails a class ratchet,
# because the partition is the thing most likely to be wrong.

_REPO = {
    "type": "string",
    "description": "Working directory to run the guard in. Other relative "
                   "paths resolve against it. Defaults to the server's cwd.",
}
_TIMEOUT = {
    "type": "integer",
    "description": "Seconds before the guard is killed and an instrument "
                   "failure is reported (never a verdict).",
}

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string"},
        "verdict": {"type": "string",
                    "description": "The guard's answer, e.g. VERIFIED, "
                                   "DECORATION, INCONCLUSIVE, OK, FINDINGS."},
        "ok": {"type": "boolean",
               "description": "True only when the guard found nothing to "
                              "report. False is a finding, not an error."},
        "exit_code": {"type": "integer"},
        "command": {"type": "string", "description": "The exact shell command "
                                                     "that produced this."},
        "cwd": {"type": "string"},
        "duration_ms": {"type": "integer"},
        "stdout": {"type": "string"},
        "stdout_truncated": {"type": "boolean"},
        "stdout_total_bytes": {"type": "integer"},
        "stderr": {"type": "string"},
        "stderr_truncated": {"type": "boolean"},
        "stderr_total_bytes": {"type": "integer"},
        "output_cap_bytes": {"type": "integer"},
    },
    "required": ["tool", "verdict", "ok", "exit_code", "command",
                 "stdout", "stdout_truncated", "stdout_total_bytes",
                 "stderr", "stderr_truncated", "stderr_total_bytes",
                 "output_cap_bytes"],
}


def _argv_verify_guard(a: dict) -> list[str]:
    argv = ["--guard-cmd", _string(a, "guard_cmd", required=True),
            "--commit", _string(a, "commit", default="HEAD"), "--json"]
    repo = _string(a, "repo")
    if repo:
        argv += ["--repo", repo]
    for pattern in _string_list(a, "code_paths"):
        argv += ["--code", pattern]
    for pattern in _string_list(a, "guard_paths"):
        argv += ["--guard-paths", pattern]
    for link in _string_list(a, "link"):
        argv += ["--link", link]
    setup = _string(a, "setup_cmd")
    if setup:
        argv += ["--setup-cmd", setup]
    return argv


def _argv_budget(a: dict) -> list[str]:
    return [_string(a, "design_dir", required=True),
            "--tests", _string(a, "tests_dir", required=True)]


def _argv_obsgate_check(a: dict) -> list[str]:
    argv = ["check", "--metrics", _string(a, "metrics", required=True),
            "--floor", _string(a, "floor", required=True)]
    samples = _int(a, "samples")
    if samples is not None:
        argv += ["--samples", str(samples)]
    interval = _int(a, "interval_ms")
    if interval is not None:
        argv += ["--interval-ms", str(interval)]
    return argv


def _argv_obsgate_snapshot(a: dict) -> list[str]:
    return ["snapshot", "--metrics", _string(a, "metrics", required=True),
            "--out", _string(a, "out", required=True)]


def _argv_obsgate_effects(a: dict) -> list[str]:
    return ["effects", "--before", _string(a, "before", required=True),
            "--after", _string(a, "after", required=True),
            "--floor", _string(a, "floor", required=True)]


def _argv_rounds(a: dict) -> list[str]:
    return [_string(a, "rounds_dir", required=True), "--check",
            "--doctrine", _string(a, "doctrine", default="DOCTRINE.md")]


def _argv_swallow(a: dict) -> list[str]:
    argv = list(_string_list(a, "paths", required=True))
    baseline = _string(a, "baseline")
    if baseline:
        argv += ["--baseline", baseline]
    for call in _string_list(a, "allow_call"):
        argv += ["--allow-call", call]
    return argv


def _argv_interpolation(a: dict) -> list[str]:
    argv = list(_string_list(a, "paths", required=True))
    keywords = _string(a, "keywords")
    if keywords:
        argv += ["--keywords", keywords]
    for call in _string_list(a, "safe_call"):
        argv += ["--safe-call", call]
    allowlist = _string(a, "allowlist")
    if allowlist:
        argv += ["--allowlist", allowlist]
    if _bool(a, "strict"):
        argv.append("--strict")
    return argv


def _argv_framework_only(a: dict) -> list[str]:
    argv = [_string(a, "repo", default=".")]
    guards = _string(a, "guards")
    if guards:
        argv += ["--guards", guards]
    return argv


TOOLS: tuple[dict, ...] = (
    {
        "name": "verify_guard",
        "title": "Prove a guard can fail",
        "module": "verify_guard",
        "description": (
            "Mechanise doctrine 2.2: revert the fix, and the guard must go RED. "
            "Checks out a commit in a throwaway worktree, runs your guard command "
            "(it must be green), reverts ONLY the production-code half of the "
            "commit, and runs it again. Verdicts: VERIFIED (the guard went red "
            "without the fix - it is real), DECORATION (it passed without the fix "
            "- it proves nothing), INCONCLUSIVE (premise broken, timeout, merge "
            "commit, bad usage - never reported as a pass). Call this before "
            "claiming a fix is guarded. SLOW: it builds a git worktree and runs "
            "your test command twice, so budget seconds to minutes, and do not "
            "call it in a loop."
        ),
        "argv": _argv_verify_guard,
        "result_codes": {0: "VERIFIED", 1: "DECORATION", 2: "INCONCLUSIVE"},
        "default_timeout": 900,
        "inputSchema": {
            "type": "object",
            "properties": {
                "guard_cmd": {"type": "string", "description":
                              "The command that runs the guard, e.g. "
                              "'python -m pytest tests/test_tenant.py::test_x'. "
                              "Stack-agnostic: go test, npx cypress run, anything."},
                "commit": {"type": "string", "description":
                           "Commit holding the fix AND its guard. Default HEAD."},
                "repo": _REPO,
                "code_paths": {"type": "array", "items": {"type": "string"},
                               "description": "Globs naming the production half "
                                              "to revert, if the default split is wrong."},
                "guard_paths": {"type": "array", "items": {"type": "string"},
                                "description": "Globs naming the test half to KEEP."},
                "setup_cmd": {"type": "string", "description":
                              "Command run in the worktree before the guard "
                              "(install, build)."},
                "link": {"type": "array", "items": {"type": "string"},
                         "description": "Directories to symlink into the "
                                        "worktree, e.g. node_modules."},
                "timeout_s": _TIMEOUT,
            },
            "required": ["guard_cmd"],
            "additionalProperties": False,
        },
    },
    {
        "name": "budget_check",
        "title": "Declared budgets must be enforced",
        "module": "budget",
        "description": (
            "Mechanise doctrine 1.1. Reads `sutradhar_budget` frontmatter from "
            "design notes and fails when a declared number (n, rps, p95_ms, "
            "memory_mb) is not enforced by any test. A budget written down and "
            "never enforced reads as a commitment and behaves like a wish. "
            "Verdicts: OK, or FINDINGS listing each unenforced budget and where "
            "it was declared. Call after adding or editing a design note."
        ),
        "argv": _argv_budget,
        "result_codes": {0: "OK", 1: "FINDINGS"},
        "default_timeout": 120,
        "inputSchema": {
            "type": "object",
            "properties": {
                "design_dir": {"type": "string", "description":
                               "Directory of design notes, e.g. docs/design/."},
                "tests_dir": {"type": "string", "description":
                              "Directory of tests that must enforce them."},
                "repo": _REPO,
                "timeout_s": _TIMEOUT,
            },
            "required": ["design_dir", "tests_dir"],
            "additionalProperties": False,
        },
    },
    {
        "name": "obsgate_check",
        "title": "Does the observability floor exist",
        "module": "obsgate",
        "description": (
            "Doctrine 6.6: a claim about a running system is worth what the "
            "surface that witnessed it is worth. Given a Prometheus-format "
            "metrics payload (file or URL) and a declared floor manifest, checks "
            "that every surface a claim will lean on has live series behind it, "
            "with label-cardinality caps. Pass `samples` (>1) to also detect a "
            "FROZEN exporter - byte-identical scrapes on a surface whose counters "
            "must move. Verdicts: OK, UNWITNESSED (floor unmet), INCONCLUSIVE "
            "(endpoint unreachable or timed out - never a pass), FROZEN. Call "
            "before trusting any number read off a dashboard."
        ),
        "argv": _argv_obsgate_check,
        "result_codes": {0: "OK", 1: "UNWITNESSED", 3: "INCONCLUSIVE", 4: "FROZEN"},
        "default_timeout": 300,
        "inputSchema": {
            "type": "object",
            "properties": {
                "metrics": {"type": "string", "description":
                            "Path to a metrics file, or an http(s) URL."},
                "floor": {"type": "string", "description":
                          "Path to the JSON floor manifest."},
                "samples": {"type": "integer", "description":
                            "Scrape this many times to detect a frozen exporter."},
                "interval_ms": {"type": "integer", "description":
                                "Delay between samples."},
                "repo": _REPO,
                "timeout_s": _TIMEOUT,
            },
            "required": ["metrics", "floor"],
            "additionalProperties": False,
        },
    },
    {
        "name": "obsgate_snapshot",
        "title": "Digest a metrics surface now",
        "module": "obsgate",
        "description": (
            "Write a deterministic digest of a metrics surface at this moment: "
            "per family its TYPE, series count, sorted label keys, "
            "order-independent value sum and a sha256. Take one BEFORE your "
            "change and one AFTER, then call obsgate_effects to find out whether "
            "the change was actually witnessed. Without a before, 'witnessed' "
            "cannot be computed, only asserted. Verdict: OK, or INCONCLUSIVE if "
            "the surface could not be read."
        ),
        "argv": _argv_obsgate_snapshot,
        "result_codes": {0: "OK", 1: "UNWITNESSED", 3: "INCONCLUSIVE", 4: "FROZEN"},
        "default_timeout": 300,
        "inputSchema": {
            "type": "object",
            "properties": {
                "metrics": {"type": "string", "description":
                            "Path to a metrics file, or an http(s) URL."},
                "out": {"type": "string", "description":
                        "Path to write the snapshot JSON to."},
                "repo": _REPO,
                "timeout_s": _TIMEOUT,
            },
            "required": ["metrics", "out"],
            "additionalProperties": False,
        },
    },
    {
        "name": "obsgate_effects",
        "title": "Was the change witnessed",
        "module": "obsgate",
        "description": (
            "Doctrine 6.6 as an exit code. Given two snapshots and a floor "
            "manifest declaring what a change must be SEEN to do (increased, "
            "appeared, no_vanished_series, stable_labels), answers whether each "
            "declared effect actually happened at the runtime surface. Names the "
            "DIRECTION of every miss, distinguishes a counter RESET from a "
            "decline, and answers UNANSWERABLE rather than passing when the "
            "snapshot cannot know. A manifest with no effects section refuses "
            "rather than returning a vacuous pass. Verdicts: OK, UNWITNESSED, "
            "INCONCLUSIVE. Call this to decide whether a change is DONE."
        ),
        "argv": _argv_obsgate_effects,
        "result_codes": {0: "OK", 1: "UNWITNESSED", 3: "INCONCLUSIVE", 4: "FROZEN"},
        "default_timeout": 300,
        "inputSchema": {
            "type": "object",
            "properties": {
                "before": {"type": "string", "description":
                           "Snapshot taken before the change."},
                "after": {"type": "string", "description":
                          "Snapshot taken after the change."},
                "floor": {"type": "string", "description":
                          "Floor manifest carrying the `effects` section."},
                "repo": _REPO,
                "timeout_s": _TIMEOUT,
            },
            "required": ["before", "after", "floor"],
            "additionalProperties": False,
        },
    },
    {
        "name": "rounds_check",
        "title": "Validate the round records",
        "module": "rounds",
        "description": (
            "Validate robustness-round records: the findings table parses, "
            "severities and statuses are legal (fixed/deferred/closed/retracted), "
            "and every cited doctrine rule id actually exists in DOCTRINE.md. A "
            "mistyped rule id silently loses the attribution doctrine 8.1 depends "
            "on, so this catches it the day it is written. Verdicts: OK, or "
            "FINDINGS naming the invalid records. Call after writing a round "
            "record, before committing it."
        ),
        "argv": _argv_rounds,
        "result_codes": {0: "OK", 1: "FINDINGS"},
        "default_timeout": 120,
        "inputSchema": {
            "type": "object",
            "properties": {
                "rounds_dir": {"type": "string", "description":
                               "Directory of round records, e.g. docs/rounds/."},
                "doctrine": {"type": "string", "description":
                             "Path to DOCTRINE.md. Default DOCTRINE.md."},
                "repo": _REPO,
                "timeout_s": _TIMEOUT,
            },
            "required": ["rounds_dir"],
            "additionalProperties": False,
        },
    },
    {
        "name": "swallow_lint",
        "title": "New silent exception swallows",
        "module": "swallow_lint",
        "description": (
            "Flag exception handlers that catch broadly and neither log, re-raise "
            "nor degrade explicitly - they return an empty value instead. A "
            "swallowed exception converts an outage into a lie: a failed datastore "
            "read swallowed into {} reads downstream as 'no data', flipping "
            "verdicts under a green status. This is a RATCHET against a per-file "
            "baseline, so it fails only on a NEW swallow. Verdicts: OK, or "
            "FINDINGS with file:line for each regression. Call after writing "
            "error handling. (Writing the baseline is deliberately not exposed "
            "here - raising your own floor mid-task would make any finding "
            "disappear. Run the CLI for that.)"
        ),
        "argv": _argv_swallow,
        "result_codes": {0: "OK", 1: "FINDINGS"},
        "default_timeout": 300,
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"},
                          "description": "Files or directories to scan."},
                "baseline": {"type": "string", "description":
                             "Baseline JSON path. Default swallow_baseline.json."},
                "allow_call": {"type": "array", "items": {"type": "string"},
                               "description": "Project-specific degrade helpers "
                                              "that make a swallow explicit."},
                "repo": _REPO,
                "timeout_s": _TIMEOUT,
            },
            "required": ["paths"],
            "additionalProperties": False,
        },
    },
    {
        "name": "interpolation_lint",
        "title": "Query-language interpolation risks",
        "module": "interpolation_lint",
        "description": (
            "Flag f-strings that interpolate a value into a query language (SQL, "
            "SPARQL, Cypher). The pattern is a hole even when today's value is a "
            "constant: it becomes the vulnerability the moment someone "
            "parameterises it, so the fix is applied while the value is still "
            "safe. Interpolations wrapped in an escaping call, or in int()/ "
            "float()/len(), are safe. Verdicts: OK, or FINDINGS with file:line "
            "and the offending expression. Call after writing any query-building "
            "code."
        ),
        "argv": _argv_interpolation,
        "result_codes": {0: "OK", 1: "FINDINGS"},
        "default_timeout": 300,
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"},
                          "description": "Files or directories to scan."},
                "keywords": {"type": "string", "description":
                             "Comma-separated presets or literal keywords: "
                             "sql, sparql, cypher. Default sql+sparql."},
                "safe_call": {"type": "array", "items": {"type": "string"},
                              "description": "Your project's escaping helpers."},
                "allowlist": {"type": "string", "description":
                              "Path to a JSON array of reviewed names."},
                "strict": {"type": "boolean", "description":
                           "Also flag bare interpolations such as LIMIT {n}, "
                           "not just quoted literal positions."},
                "repo": _REPO,
                "timeout_s": _TIMEOUT,
            },
            "required": ["paths"],
            "additionalProperties": False,
        },
    },
    {
        "name": "framework_only",
        "title": "Still copy-in, still zero-dependency",
        "module": "framework_only",
        "description": (
            "Check that the guard surface imports the standard library only and "
            "that no packaging or dependency manifest exists outside examples/. "
            "The first third-party import is the moment a copy-in toolkit becomes "
            "a pip-install product; this makes that a conscious diff rather than "
            "a quiet drift. Verdicts: OK, or FINDINGS naming each breach. Call "
            "after adding an import or a config file to a copy-in toolkit."
        ),
        "argv": _argv_framework_only,
        "result_codes": {0: "OK", 1: "FINDINGS"},
        "default_timeout": 180,
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description":
                         "Repository root to scan. Default '.'."},
                "guards": {"type": "string", "description":
                           "Path to the stdlib-only guard directory. Default "
                           "python/sutradhar_guards."},
                "timeout_s": _TIMEOUT,
            },
            "additionalProperties": False,
        },
    },
)

BY_NAME = {tool["name"]: tool for tool in TOOLS}


def guard_dir() -> Path:
    """Where the guard CLIs live.

    Defaults to this file's own directory, which is correct for both the
    repo layout and a copy-in that kept the files together. The override
    exists for an adopter who copied the guards to `scripts/` - and it is
    also what lets a test poison the dispatch to prove the selfcheck really
    calls a tool.
    """
    override = os.environ.get("SUTRADHAR_MCP_GUARD_DIR")
    return Path(override) if override else Path(__file__).resolve().parent


def public_tools() -> list[dict]:
    """The `tools/list` view: no internals, deterministic order."""
    return [
        {"name": t["name"], "title": t["title"], "description": t["description"],
         "inputSchema": t["inputSchema"], "outputSchema": _OUTPUT_SCHEMA}
        for t in TOOLS
    ]


# ── running a guard ─────────────────────────────────────────────────────────

def run_tool(name: str, arguments: dict) -> dict:
    """Run one guard through its REAL CLI and classify the outcome.

    Returns the MCP tool result. Raises RpcError ONLY when no measurement was
    taken - never because the guard reported a finding.
    """
    spec = BY_NAME.get(name)
    if spec is None:
        raise _bad_args(f"Unknown tool: {name}. Known tools: "
                        f"{', '.join(sorted(BY_NAME))}")
    if not isinstance(arguments, dict):
        raise _bad_args(f"`arguments` must be an object, got {type(arguments).__name__}")

    allowed = set(spec["inputSchema"]["properties"])
    unknown = sorted(set(arguments) - allowed)
    if unknown:
        # An unrecognised argument is never ignored, for the same reason an
        # unrecognised FLAG is never ignored in these CLIs: a typo that gets
        # silently dropped runs a different check than the caller asked for
        # and reports its exit code as if it were the answer.
        raise _bad_args(
            f"unknown argument(s) for {name}: {', '.join(unknown)}. "
            f"Known: {', '.join(sorted(allowed))}"
        )

    tail = spec["argv"](arguments)            # may raise RpcError(-32602)
    script = guard_dir() / f"{spec['module']}.py"
    if not script.is_file():
        raise InstrumentError(
            f"the guard CLI for {name!r} is not where this server expects it: "
            f"{script}. No check ran, so this says NOTHING about the code you "
            f"pointed it at. Set SUTRADHAR_MCP_GUARD_DIR if the guards live "
            f"elsewhere.",
            tool=name, expected_path=str(script),
        )

    cwd = arguments.get("repo") or os.getcwd()
    if not Path(cwd).is_dir():
        raise _bad_args(f"`repo` is not a directory: {cwd}")

    argv = [sys.executable, str(script), *tail]
    timeout = _int(arguments, "timeout_s", default=spec["default_timeout"])
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        raise InstrumentError(
            f"{name} was killed after {timeout}s. The guard did not finish, so "
            f"there is NO verdict - this is not a pass and not a failure of the "
            f"code under test. Raise `timeout_s` or narrow the scope.",
            tool=name, timeout_s=timeout,
        ) from None
    except OSError as exc:
        raise InstrumentError(
            f"could not start {name}: {type(exc).__name__}: {exc}. This is this "
            f"server's failure, not evidence about your repository.",
            tool=name, exception_type=type(exc).__name__,
        ) from None
    duration_ms = int((time.perf_counter() - started) * 1000)

    out, out_cut, out_total = cap_output(proc.stdout or "")
    err, err_cut, err_total = cap_output(proc.stderr or "")
    verdict = spec["result_codes"].get(proc.returncode)

    if verdict is None:
        # An exit code outside the declared partition means the guard did
        # something this server does not know how to read - a crash, a signal,
        # a version skew. Reporting it as a verdict would be inventing one.
        raise InstrumentError(
            f"{name} exited {proc.returncode}, which is not one of its known "
            f"verdict codes ({', '.join(str(c) for c in sorted(spec['result_codes']))}). "
            f"The guard crashed or this server is out of date with it; either "
            f"way no verdict was reached.",
            tool=name, exit_code=proc.returncode,
            stdout=out, stderr=err,
            command=" ".join(shlex.quote(a) for a in argv),
        )

    structured = {
        "tool": name,
        "verdict": verdict,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "command": " ".join(shlex.quote(a) for a in argv),
        "cwd": str(cwd),
        "duration_ms": duration_ms,
        "stdout": out,
        "stdout_truncated": out_cut,
        "stdout_total_bytes": out_total,
        "stderr": err,
        "stderr_truncated": err_cut,
        "stderr_total_bytes": err_total,
        "output_cap_bytes": MAX_OUTPUT_BYTES,
    }

    headline = (
        f"{name}: {verdict} (exit {proc.returncode}) in {duration_ms} ms\n"
        f"$ {structured['command']}"
    )
    blocks = [headline]
    for rendered in (_render_stream("stdout", out, out_cut, out_total),
                     _render_stream("stderr", err, err_cut, err_total)):
        if rendered:
            blocks.append(rendered)

    # isError stays FALSE for every verdict, red included. Per the spec,
    # isError: true means "actionable feedback the model can self-correct on
    # by adjusting parameters" - and DECORATION is not fixed by adjusting
    # parameters, it is fixed by writing a better guard. Flagged as an error
    # it reads as flakiness, and flakiness gets retried instead of acted on.
    return {"content": [{"type": "text", "text": "\n\n".join(blocks)}],
            "structuredContent": structured, "isError": False}


# ── JSON-RPC dispatch ───────────────────────────────────────────────────────

def _result(payload: dict) -> dict:
    """Every result carries `resultType` and serverInfo.

    Modern clients REQUIRE resultType; legacy clients ignore unknown fields
    and are told to read an absent one as "complete" anyway, so one shape
    serves both eras.
    """
    return {"resultType": "complete", "_meta": {
        META_SERVER_INFO: {"name": SERVER_NAME, "version": SERVER_VERSION},
    }, **payload}


def _check_era(method: str, params: dict) -> None:
    """Validate modern per-request metadata, when present."""
    meta = params.get("_meta")
    if not isinstance(meta, dict) or META_VERSION not in meta:
        return  # legacy or era-neutral; nothing to validate
    version = meta.get(META_VERSION)
    if version not in SUPPORTED_VERSIONS:
        raise RpcError(
            UNSUPPORTED_PROTOCOL_VERSION, "Unsupported protocol version",
            {"supported": list(SUPPORTED_VERSIONS), "requested": version},
        )
    if META_CLIENT_CAPS not in meta and method != "initialize":
        raise _bad_args(
            f"modern request is missing the required _meta field "
            f"{META_CLIENT_CAPS!r}"
        )


def dispatch(method: str, params: dict) -> dict:
    """Method -> result payload. Raises RpcError for anything else."""
    _check_era(method, params)

    if method == "initialize":
        # Legacy era. Echo a version we both speak, else our newest legacy one.
        asked = params.get("protocolVersion")
        agreed = asked if asked in SUPPORTED_VERSIONS else LEGACY_VERSIONS[0]
        return _result({
            "protocolVersion": agreed,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "Sutradhar's guards, callable mid-task. A RED verdict is a "
                "normal result, not an error: read `structuredContent.verdict`. "
                "A JSON-RPC error from this server means the guard could not be "
                "run at all, so nothing was measured."
            ),
        })

    if method == "server/discover":
        return _result({
            "supportedVersions": list(SUPPORTED_VERSIONS),
            "capabilities": {"tools": {"listChanged": False}},
            "instructions": (
                "Sutradhar's guards, callable mid-task. A RED verdict is a "
                "normal result, not an error: read `structuredContent.verdict`. "
                "A JSON-RPC error from this server means the guard could not be "
                "run at all, so nothing was measured."
            ),
        })

    if method == "ping":
        return _result({})

    if method == "tools/list":
        return _result({"tools": public_tools()})

    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise _bad_args("`name` is required and must be a tool name")
        return _result(run_tool(name, params.get("arguments") or {}))

    raise RpcError(METHOD_NOT_FOUND, f"method not found: {method}")


def handle_line(line: str) -> dict | None:
    """One inbound line -> one outbound message, or None for a notification.

    Nothing raised in here is allowed to end the session: a malformed request
    from a client mid-task must cost that request, not the conversation.
    """
    try:
        msg = json.loads(line)
    except (ValueError, TypeError) as exc:
        return {"jsonrpc": "2.0", "id": None, "error": {
            "code": PARSE_ERROR,
            "message": f"instrument: could not parse a line as JSON: "
                       f"{type(exc).__name__}",
            "data": {"party": "caller"}}}

    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": None, "error": {
            "code": INVALID_REQUEST,
            "message": "not a JSON-RPC 2.0 request object",
            "data": {"party": "caller"}}}

    mid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params")
    if not isinstance(params, dict):
        params = {}

    if not isinstance(method, str):
        if mid is None:
            return None
        return {"jsonrpc": "2.0", "id": mid, "error": {
            "code": INVALID_REQUEST, "message": "`method` must be a string",
            "data": {"party": "caller"}}}

    is_notification = "id" not in msg or mid is None

    try:
        result = dispatch(method, params)
    except RpcError as exc:
        if is_notification:
            _log(f"error on notification {method}: {exc.message}")
            return None
        return {"jsonrpc": "2.0", "id": mid, "error": exc.payload()}
    except Exception as exc:  # noqa: BLE001 - the containment boundary
        # Catch broadly HERE and nowhere else, print the TYPE, and say whose
        # failure it is. Without this, a bug in this server's own argument
        # handling would surface as a traceback the caller reads as a
        # statement about their repository (doctrine 2.4, the R3-1 scar).
        _log(f"unhandled {type(exc).__name__} in {method}: {exc}")
        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": mid, "error": InstrumentError(
            f"this server raised {type(exc).__name__} handling {method!r}: "
            f"{exc}. That is a bug in the MCP adapter, NOT evidence about the "
            f"code you asked it to check.",
            method=method, exception_type=type(exc).__name__,
        ).payload()}

    if is_notification:
        return None
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(stdin=None, stdout=None) -> int:
    """The stdio loop: newline-delimited JSON-RPC, one message per line."""
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    while True:
        line = stdin.readline()
        if not line:
            return 0  # EOF: the client closed stdin, which is the shutdown signal
        if not line.strip():
            continue
        response = handle_line(line)
        if response is None:
            continue
        # json.dumps escapes newlines, so a message can never contain one -
        # which the transport forbids and a guard's multi-line stdout would
        # otherwise produce on every single call.
        stdout.write(json.dumps(response) + "\n")
        stdout.flush()


# ── selfcheck ───────────────────────────────────────────────────────────────

class _Client:
    """A real stdio MCP client over a real subprocess. No shortcuts: the
    selfcheck must exercise the transport, not a function call."""

    def __init__(self, env: dict | None = None) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-u", str(Path(__file__).resolve())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
            env=env if env is not None else dict(os.environ),
        )
        self._id = 0

    def send_raw(self, line: str) -> dict:
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def call(self, method: str, params: dict | None = None,
             modern: bool = True) -> dict:
        self._id += 1
        body = dict(params or {})
        if modern:
            body["_meta"] = {
                META_VERSION: MODERN_VERSIONS[0],
                META_CLIENT_CAPS: {},
                "io.modelcontextprotocol/clientInfo": {
                    "name": "sutradhar-selfcheck", "version": SERVER_VERSION},
            }
        return self.send_raw(json.dumps(
            {"jsonrpc": "2.0", "id": self._id, "method": method, "params": body}))

    def notify(self, method: str) -> None:
        self.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=15)
        except Exception:  # noqa: BLE001
            self.proc.kill()


def selfcheck() -> bool:
    try:
        return _selfcheck_body()
    except Exception as exc:  # noqa: BLE001
        print(f"[mcp-server] SELFCHECK FAILED: the selfcheck itself raised "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return False


def _fail(message: str) -> bool:
    print(f"[mcp-server] SELFCHECK FAILED: {message}", file=sys.stderr)
    return False


def _selfcheck_body() -> bool:
    import tempfile

    ok = True

    # 1. The output cap, in isolation: it must cut AND say the total.
    text, cut, total = cap_output("x" * 100, limit=10)
    if not cut or len(text) != 10 or total != 100:
        ok = _fail("cap_output did not truncate to its limit while reporting "
                   "the true total - an uncapped tool result is a context-window "
                   "bomb and a silent one is worse")
    text, cut, total = cap_output("short", limit=10)
    if cut or text != "short":
        ok = _fail("cap_output truncated a stream that fits")

    # 2. Every tool must carry a schema AND an exit-code partition.
    for tool in TOOLS:
        schema = tool.get("inputSchema")
        if not isinstance(schema, dict) or schema.get("type") != "object" \
                or not isinstance(schema.get("properties"), dict):
            ok = _fail(f"tool {tool['name']} has no usable inputSchema")
        if not tool.get("result_codes"):
            ok = _fail(f"tool {tool['name']} declares no result_codes, so every "
                       f"verdict it reaches would read as an instrument failure")

    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        (tmp / "clean").mkdir()
        (tmp / "clean" / "ok.py").write_text(
            'def q(conn, name):\n'
            '    return conn.execute("SELECT * FROM t WHERE n = ?", (name,))\n'
        )
        (tmp / "dirty").mkdir()
        (tmp / "dirty" / "bad.py").write_text(
            'def q(conn, name):\n'
            '    return conn.execute(f\'SELECT * FROM t WHERE n = "{name}"\')\n'
        )

        client = _Client()
        try:
            # 3. Modern era: server/discover is the handshake-free entry point.
            res = client.call("server/discover")
            got = res.get("result", {})
            if MODERN_VERSIONS[0] not in got.get("supportedVersions", []):
                ok = _fail(f"server/discover did not advertise "
                           f"{MODERN_VERSIONS[0]}: {res}")
            if got.get("resultType") != "complete":
                ok = _fail("a result carried no resultType, which modern "
                           "clients require")

            # 4. tools/list returns every tool, each with a schema.
            listed = client.call("tools/list").get("result", {}).get("tools", [])
            names = {t["name"] for t in listed}
            if names != set(BY_NAME):
                ok = _fail(f"tools/list returned {sorted(names)}, expected "
                           f"{sorted(BY_NAME)}")
            if any("inputSchema" not in t for t in listed):
                ok = _fail("a listed tool carried no inputSchema, so an agent "
                           "cannot call it")

            # 5. A REAL tool call that passes.
            green = client.call("tools/call", {
                "name": "interpolation_lint",
                "arguments": {"paths": [str(tmp / "clean")], "keywords": "sql"},
            })
            if "result" not in green:
                ok = _fail(f"a clean tool call did not return a result: {green}")
            elif green["result"]["structuredContent"]["verdict"] != "OK":
                ok = _fail(f"a clean scan did not read OK: "
                           f"{green['result']['structuredContent']}")

            # 6. A REAL tool call that FINDS SOMETHING. This is the one the
            #    whole design turns on: a red guard is a RESULT.
            red = client.call("tools/call", {
                "name": "interpolation_lint",
                "arguments": {"paths": [str(tmp / "dirty")], "keywords": "sql"},
            })
            if "error" in red:
                ok = _fail(
                    "a guard that FOUND something came back as a JSON-RPC "
                    "error. A red guard is the tool working; reporting it as "
                    "an error tells the agent its call failed and should be "
                    "retried, which is the opposite of the truth: "
                    f"{red['error']}")
            elif red["result"]["structuredContent"]["verdict"] != "FINDINGS":
                ok = _fail(f"a planted SQL interpolation was not found: "
                           f"{red['result']['structuredContent']}")
            elif red["result"]["isError"]:
                ok = _fail("a red guard set isError, which means 'retry with "
                           "adjusted parameters' - it is not a call the agent "
                           "should retry")

            # 7. An unknown tool is an ERROR, not a verdict.
            unknown = client.call("tools/call", {"name": "no_such_tool"})
            if "error" not in unknown or unknown["error"]["code"] != INVALID_PARAMS:
                ok = _fail(f"an unknown tool did not produce an invalid-params "
                           f"error: {unknown}")

            # 8. A malformed line is answered and the session SURVIVES.
            bad = client.send_raw("{not json at all")
            if bad.get("error", {}).get("code") != PARSE_ERROR:
                ok = _fail(f"a malformed line did not produce a parse error: {bad}")
            if "result" not in client.call("tools/list"):
                ok = _fail("the session died after one malformed request - a "
                           "bad line must cost that request, not the "
                           "conversation an agent is mid-task in")

            # 9. An unsupported modern version is refused BY NAME.
            self_id = client._id + 1
            client._id = self_id
            skew = client.send_raw(json.dumps({
                "jsonrpc": "2.0", "id": self_id, "method": "tools/list",
                "params": {"_meta": {META_VERSION: "1900-01-01",
                                     META_CLIENT_CAPS: {}}}}))
            if skew.get("error", {}).get("code") != UNSUPPORTED_PROTOCOL_VERSION:
                ok = _fail(f"an unsupported protocol version was not refused "
                           f"with the spec's code: {skew}")
        finally:
            client.close()

        # 10. Legacy era: the initialize handshake still works end to end.
        legacy = _Client()
        try:
            init = legacy.call("initialize", {
                "protocolVersion": LEGACY_VERSIONS[-1],
                "capabilities": {},
                "clientInfo": {"name": "sutradhar-selfcheck", "version": "1"},
            }, modern=False)
            if init.get("result", {}).get("protocolVersion") not in SUPPORTED_VERSIONS:
                ok = _fail(f"the legacy initialize handshake did not agree a "
                           f"version: {init}")
            legacy.notify("notifications/initialized")
            listed = legacy.call("tools/list", modern=False)
            if "result" not in listed:
                ok = _fail(f"tools/list failed after a legacy handshake: {listed}")
        finally:
            legacy.close()

    if ok:
        print(
            f"[mcp-server] selfcheck ok: spawned itself over real stdio, "
            f"handshook in BOTH eras (modern server/discover {MODERN_VERSIONS[0]} "
            f"and legacy initialize {LEGACY_VERSIONS[-1]}), listed all "
            f"{len(TOOLS)} tools with schemas, CALLED interpolation_lint twice - "
            f"green and red - and confirmed the red one came back as a RESULT "
            f"(verdict FINDINGS, isError false) while an unknown tool, an "
            f"unsupported version and a malformed line each came back as "
            f"JSON-RPC errors that did not kill the session; output capped at "
            f"{MAX_OUTPUT_BYTES:,} bytes per stream with truncation stated"
        )
    return ok


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--selfcheck" in argv:
        return 0 if selfcheck() else 1

    for arg in argv:
        # An unrecognised flag is never ignored. Silently skipping it means a
        # typo like `--selfchek` starts a SERVER instead of running a check,
        # and a process that sits there reading stdin looks exactly like one
        # that passed.
        if arg not in _KNOWN_FLAGS:
            print(f"[mcp-server] unknown flag: {arg}", file=sys.stderr)
            return 2

    return serve()


if __name__ == "__main__":
    sys.exit(main())
