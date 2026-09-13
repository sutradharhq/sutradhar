# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""The plugin must work in the layout it is INSTALLED in, not only built in.

R16-1, and the class is "tested only in the layout it was built in". Claude
Code copies an installed plugin into `~/.claude/plugins/cache`, and files
outside the plugin directory are not copied - so `${CLAUDE_PLUGIN_ROOT}/../
python/sutradhar_guards` resolved perfectly from a checkout and would have
been missing the first time anyone installed the plugin from a marketplace.
No test could see it, because every test ran from the checkout.

Two guards answer that, and they answer different halves:

  - the BUNDLE guard (byte-identity plus coverage of the scripts the plugin
    actually invokes, both derived from code rather than from a list
    somebody keeps by hand);
  - the INSTALLED-CONDITION guard, which runs the bundled MCP server over
    the real stdio transport from a temp cwd with the checkout's `python/`
    off `sys.path` and no environment overrides. That is the marketplace
    install reproduced closely enough to fail if `../` creeps back.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import sutradhar_guards
from sutradhar_guards.mcp_server import TOOLS

PKG = Path(sutradhar_guards.__path__[0])
REPO_ROOT = PKG.parent.parent
PLUGIN = REPO_ROOT / "plugin"
BUNDLE = PLUGIN / "guards"
SCRIPTS = PLUGIN / "scripts"

_SCRIPT_NAME = re.compile(r"^[a-z_][a-z0-9_]*\.py$")


def _sync_module():
    """`plugin/sync_guards.py` loaded by path - it is not importable as a
    package, and copying its BUNDLED list here would make this test a
    second hand-maintained list rather than a check on the first."""
    spec = importlib.util.spec_from_file_location(
        "sutradhar_sync_guards", PLUGIN / "sync_guards.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYNC = _sync_module()


def _script_names_referenced_by(path: Path) -> set[str]:
    """Every `<name>.py` string constant in a source file, by AST.

    This is how the hooks name the guards they spawn (`gdir /
    "interpolation_lint.py"`), so reading the constants back out is reading
    what the code will actually do rather than what a comment says it does.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and _SCRIPT_NAME.match(node.value)
    }


def scripts_the_plugin_invokes() -> set[str]:
    """Derived, never listed: the guard CLIs the plugin's own code names."""
    needed: set[str] = set()
    for name in ("_hooklib.py", "precommit_gate.py", "verify_before_done.py"):
        needed |= _script_names_referenced_by(SCRIPTS / name)
    # The MCP tool table names its guards in a `module` field, and the server
    # spawns `<module>.py`. Adding a tool adds a requirement here the same
    # day, without anyone remembering to.
    needed |= {f"{tool['module']}.py" for tool in TOOLS}
    needed.add("mcp_server.py")          # the server the plugin registers
    return needed


# ── the bundle is a copy, and a copy that is checked ────────────────────────

def test_the_bundle_is_not_empty():
    """Guards the guard: an empty BUNDLED would make every check below pass
    vacuously (3.6 - presence is not reachability)."""
    assert len(SYNC.BUNDLED) >= 8, SYNC.BUNDLED
    assert BUNDLE.is_dir(), f"no bundle at {BUNDLE}"


@pytest.mark.parametrize("name", sorted(SYNC.BUNDLED))
def test_each_bundled_guard_is_byte_identical_to_its_source(name):
    """Round 15 refused to copy because a copy is a second answer to "what
    does verify_guard do", and the first time they disagreed the copy would
    win silently. That argument is answered here rather than dropped: they
    cannot disagree by one byte without this going red."""
    src, dst = PKG / name, BUNDLE / name
    assert src.is_file(), f"{name} is bundled but no longer exists at {src}"
    assert dst.is_file(), f"{name} is in BUNDLED but missing from {BUNDLE}"
    assert dst.read_bytes() == src.read_bytes(), (
        f"{dst} differs from {src}. Run `python3 plugin/sync_guards.py`; if "
        f"the divergence was deliberate, it is a fork and needs saying out "
        f"loud rather than living in a copy nobody diffs.")


def test_the_bundle_covers_every_script_the_plugin_invokes():
    """The set is DERIVED from the plugin's own source and tool table, so a
    guard added to a hook or a tool added to the MCP table is covered the
    day it lands - not the day somebody remembers this list exists."""
    needed = scripts_the_plugin_invokes()
    assert needed, "derived nothing - this ratchet would pass vacuously"
    missing = sorted(needed - set(SYNC.BUNDLED))
    assert not missing, (
        f"the plugin spawns {missing}, and sync_guards.BUNDLED does not ship "
        f"them. Installed from a marketplace, those calls are an instrument "
        f"failure on every invocation.")


def test_nothing_in_the_bundle_is_missing_from_the_list():
    """The other direction: a file that arrived in `plugin/guards/` without
    passing through the list is unpinned, and an unpinned copy is exactly
    the second-answer problem round 15 was right about."""
    on_disk = {p.name for p in BUNDLE.glob("*.py")}
    stray = sorted(on_disk - set(SYNC.BUNDLED))
    assert not stray, (
        f"{stray} are in {BUNDLE} but not in sync_guards.BUNDLED, so nothing "
        f"pins them to a source file")


def test_sync_guards_check_agrees_with_this_file():
    """The CLI a human runs and the test CI runs must give the same answer,
    or one of them is decoration."""
    proc = subprocess.run(
        [sys.executable, str(PLUGIN / "sync_guards.py"), "--check"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ── the plugin points inside itself ─────────────────────────────────────────

def test_no_plugin_config_reaches_outside_the_plugin_directory():
    """A class ratchet over every JSON config the plugin ships.

    `${CLAUDE_PLUGIN_ROOT}/../anything` is the R16-1 defect itself: it
    resolves from a checkout and is simply absent after an install, with no
    error at the moment of installation to say so.
    """
    configs = sorted(PLUGIN.rglob("*.json"))
    assert configs, "no plugin config found - the ratchet would pass vacuously"
    for path in configs:
        text = path.read_text(encoding="utf-8")
        assert "${CLAUDE_PLUGIN_ROOT}/.." not in text, (
            f"{path} reaches outside the plugin directory. Installed plugins "
            f"are copied without their surroundings, so that path is present "
            f"only in a checkout.")


def test_mcp_json_points_at_the_bundled_server():
    config = json.loads((PLUGIN / ".mcp.json").read_text())
    target = config["mcpServers"]["sutradhar-guards"]["args"][0]
    assert target == "${CLAUDE_PLUGIN_ROOT}/guards/mcp_server.py", target
    assert (PLUGIN / "guards" / "mcp_server.py").is_file()


# ── the marketplace manifest ────────────────────────────────────────────────

def test_marketplace_manifest_resolves_to_a_real_plugin():
    """Read against the plugin docs on 2026-09-04: the marketplace manifest
    lives at `<repo>/.claude-plugin/marketplace.json`, and each entry's
    `source` is resolved relative to the marketplace root."""
    manifest = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["name"] == "sutradhar"
    assert data["owner"]["name"]
    assert data["plugins"], "a marketplace with no plugins installs nothing"
    for entry in data["plugins"]:
        assert entry["name"] and entry["description"]
        resolved = (REPO_ROOT / entry["source"]).resolve()
        assert resolved.is_dir(), f"{entry['source']} is not a directory"
        assert (resolved / ".claude-plugin" / "plugin.json").is_file(), (
            f"{entry['source']} has no .claude-plugin/plugin.json, so "
            f"installing it would find no plugin there")


# ── the update signal ───────────────────────────────────────────────────────

_RELEASE_HEADING = re.compile(r"^## \[?v?(\d+)\.(\d+)\.(\d+)\]?(?=\s|$)")


def test_no_manifest_pins_the_installed_plugin_to_a_version():
    """R21-1. Read against the plugin reference ("Version management") on
    2026-09-13: Claude Code takes the first of plugin.json's `version`, the
    marketplace entry's `version`, then the commit SHA, and that value is
    the key that decides whether an update exists at all.

    plugin.json said 0.3.0 from the day it was written. v0.5.1's security
    fix changed the `Stop` hook, `/plugin update` compared 0.3.0 with 0.3.0,
    and everyone who had installed the plugin kept the vulnerable copy while
    the release notes told them to upgrade. With neither field set, every
    commit is a version Claude Code can see."""
    plugin = json.loads(
        (PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert "version" not in plugin, (
        f"plugin.json declares version {plugin['version']!r}: an installed "
        f"plugin now updates only when that string changes, and a fix pushed "
        f"without bumping it never reaches anyone who already installed")
    market = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json")
                        .read_text(encoding="utf-8"))
    for entry in market["plugins"]:
        assert "version" not in entry, (
            f"marketplace entry {entry['name']!r} declares version "
            f"{entry['version']!r}, which pins installed copies the same way")


def test_every_version_string_names_the_newest_release():
    """R21-1's other half. `__version__` and the MCP server's
    `serverInfo.version` said 0.3.0 through three releases, so nothing in a
    copied guard or a running server could say which release it came from.
    The newest release heading in CHANGELOG.md is where a release is
    written down in the tree - CI checks out without tags - so every version
    string must name it.

    R21-10, from the outside review of v0.5.2: the first draft read only
    `## vX.Y.Z`, so a newer release spelled `## 0.6.0` or `## [0.6.0]` was
    skipped and stale strings passed; and it never looked at CITATION.cff
    (three releases behind) or the browser probe's own `serverInfo`. So
    every `## ` heading must read as a release or be `Unreleased`, and all
    four strings must agree with the newest."""
    from sutradhar_guards.mcp_server import SERVER_VERSION

    headings = [line for line in (REPO_ROOT / "CHANGELOG.md")
                .read_text(encoding="utf-8").splitlines()
                if line.startswith("## ")]
    unread = [h for h in headings
              if h.strip() != "## Unreleased" and not _RELEASE_HEADING.match(h)]
    assert not unread, (
        f"CHANGELOG headings this test cannot read as a release: {unread}. "
        f"Skipping one would compare against an older release and pass.")
    releases = [tuple(int(p) for p in _RELEASE_HEADING.match(h).groups())
                for h in headings if h.strip() != "## Unreleased"]
    assert releases, "CHANGELOG.md has no release heading to compare with"
    newest = ".".join(str(p) for p in max(releases))

    citation = re.search(r"^version:\s*[\"']?(\d+\.\d+\.\d+)[\"']?\s*$",
                         (REPO_ROOT / "CITATION.cff").read_text(encoding="utf-8"),
                         re.MULTILINE)
    probe = re.search(
        r'serverInfo:\s*\{\s*name:\s*"sutradhar-probe",\s*version:\s*"([^"]+)"',
        (REPO_ROOT / "js" / "probe" / "mcp.mjs").read_text(encoding="utf-8"))
    assert citation, "CITATION.cff has no `version:` line this test can read"
    assert probe, "js/probe/mcp.mjs has no serverInfo version this test can read"
    found = {
        "sutradhar_guards.__version__": sutradhar_guards.__version__,
        "mcp_server.SERVER_VERSION": SERVER_VERSION,
        "CITATION.cff version": citation.group(1),
        "js/probe/mcp.mjs serverInfo.version": probe.group(1),
    }
    wrong = {name: value for name, value in found.items() if value != newest}
    assert not wrong, (
        f"the newest CHANGELOG release is {newest}; these say otherwise: {wrong}")


# ── the installed condition, reproduced ─────────────────────────────────────

class _BundledServer:
    """The bundled MCP server over real stdio, in the marketplace-install
    condition: a temp cwd, no `SUTRADHAR_*` overrides, and the checkout's
    `python/` deliberately NOT on `sys.path`."""

    def __init__(self, cwd: Path):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("SUTRADHAR_")}
        env.pop("PYTHONPATH", None)
        self.proc = subprocess.Popen(
            [sys.executable, "-u", str(BUNDLE / "mcp_server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
            cwd=str(cwd), env=env,
        )
        self._id = 0

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self.proc.stdin.write(json.dumps({
            "jsonrpc": "2.0", "id": self._id, "method": method,
            "params": params or {}}) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        assert line, f"the server closed stdout: {self.proc.stderr.read()}"
        return json.loads(line)

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=30)
        except Exception:  # noqa: BLE001
            self.proc.kill()


def test_the_bundled_server_works_where_the_checkout_is_not(tmp_path):
    """The whole of R16-1 in one test.

    Nothing here can reach `python/sutradhar_guards`: the cwd is a temp
    directory, `PYTHONPATH` is stripped, and every `SUTRADHAR_*` override is
    removed. If the server or its guard-directory resolution reaches outside
    `plugin/`, this fails - which is what nothing did before, because every
    other test runs from the checkout.
    """
    work = tmp_path / "elsewhere"
    work.mkdir()
    (work / "ok.py").write_text(
        'def q(conn, name):\n'
        '    return conn.execute("SELECT * FROM t WHERE n = ?", (name,))\n')

    server = _BundledServer(work)
    try:
        listed = server.request("tools/list")
        assert "result" in listed, listed
        names = {t["name"] for t in listed["result"]["tools"]}
        assert names == {t["name"] for t in TOOLS}, names

        called = server.request("tools/call", {
            "name": "interpolation_lint",
            "arguments": {"paths": [str(work)], "keywords": "sql"}})
    finally:
        server.close()

    assert "error" not in called, (
        f"the bundled server could not run a guard from an installed layout: "
        f"{called.get('error')}")
    assert called["result"]["structuredContent"]["verdict"] == "OK", called


def test_the_hooks_find_their_guards_when_the_checkout_is_not_there(tmp_path):
    """The hook half of R16-1, and the only guard that can see it.

    `plugin/` is copied somewhere with nothing around it - which is what an
    install is - and the pre-commit gate is driven there against a fresh
    repository carrying a planted f-string SQL interpolation. A gate that
    cannot find its guards reports an instrument failure and ALLOWS, so the
    assertion has to be on the deny: "did not crash" is exactly what the
    broken version also does.

    Every test in this file except this one runs from the checkout, which is
    why the checkout is the one layout that proves nothing.
    """
    installed = tmp_path / "installed"
    shutil.copytree(PLUGIN, installed / "plugin")
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> None:
        proc = subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=T",
             "-c", "user.email=t@example.com", *args],
            capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, (args, proc.stderr)

    git("init", "-q", "-b", "main")
    (repo / "seed.py").write_text("x = 1\n")
    git("add", "seed.py")
    git("commit", "-q", "-m", "seed")
    (repo / "dirty.py").write_text(
        'def q(conn, n):\n'
        '    return conn.execute(f\'SELECT * FROM t WHERE n = "{n}"\')\n')
    git("add", "dirty.py")

    env = {k: v for k, v in os.environ.items() if not k.startswith("SUTRADHAR_")}
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, str(installed / "plugin" / "scripts" / "precommit_gate.py")],
        input=json.dumps({
            "session_id": "installed", "cwd": str(repo),
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "git commit -m x"}}),
        capture_output=True, text=True, timeout=300, env=env,
        cwd=str(installed))

    assert proc.returncode == 0, proc.stderr
    body = json.loads(proc.stdout)
    assert "instrument failure" not in json.dumps(body), (
        f"the gate could not find its guards from an installed layout, which "
        f"is R16-1: {body}")
    hook_out = body.get("hookSpecificOutput", {})
    assert hook_out.get("permissionDecision") == "deny", body
    assert "interpolation_lint" in hook_out["permissionDecisionReason"]
    assert "dirty.py" in hook_out["permissionDecisionReason"]


def test_the_bundled_server_selfcheck_passes_standalone():
    """`--selfcheck` on the COPY, not the source. The copy is what an
    installed plugin runs, and an exit code from the source says nothing
    about it (6.6: a claim is worth what the surface behind it is worth)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SUTRADHAR_")}
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, str(BUNDLE / "mcp_server.py"), "--selfcheck"],
        capture_output=True, text=True, timeout=600, env=env,
        cwd=str(BUNDLE))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "selfcheck ok" in proc.stdout
