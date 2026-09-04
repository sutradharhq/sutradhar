# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""The two session hooks, driven as REAL subprocesses over real repositories.

Not one test here imports a hook function and calls it. The seam Claude Code
uses is a process that reads one JSON payload on stdin and answers with one
JSON object on stdout (doctrine 2.3), and the payloads below are the shapes
documented at <https://code.claude.com/docs/en/hooks> - `tool_name`,
`tool_input`, `cwd`, `stop_hook_active`, `session_id`.

The load-bearing assertions are the ones about what does NOT happen:

  - a guard that could not run never becomes a pass (2.9);
  - a hook that crashes never blocks (2.4 - and see `docs/design/
    agent-loop-hooks.md`, "The honesty rule"). An instrument whose error
    branch cannot say WHOSE failure it is reports the wrong outage with
    total confidence, and a hook's version of that mistake takes somebody's
    commit away;
  - an exit code outside a guard's documented partition is an instrument
    failure, not a verdict.

Guard-verdict shaping is done with STUB guard directories rather than by
contriving real red findings for every case: the stub is how a guard's exit
code reaches the hook in production too (a subprocess), so the seam is real.
The real guards are exercised end to end by the red/green tests and by the
budget test, which run the actual CLIs over an actual repository.
"""
from __future__ import annotations

import ast
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

import sutradhar_guards
from sutradhar_guards.budget import budget, get_budget

PKG_PARENT = Path(sutradhar_guards.__path__[0]).parent
REPO_ROOT = PKG_PARENT.parent
PLUGIN = REPO_ROOT / "plugin"
SCRIPTS = PLUGIN / "scripts"
GATE = SCRIPTS / "precommit_gate.py"
DONE = SCRIPTS / "verify_before_done.py"
DESIGN = REPO_ROOT / "docs" / "design"
NOTE = DESIGN / "agent-loop-hooks.md"

#: The fast path (a Bash call that is not a commit) may cost at most this
#: multiple of a bare interpreter start, measured in the same run. An
#: absolute millisecond figure for a path dominated by CPython startup
#: measures the machine; the ratio measures the change. Pinned to the design
#: note by `test_fast_path_factor_matches_the_design_note`.
FAST_PATH_BUDGET_FACTOR = 3.0

RED_SOURCE = (
    "def find(conn, tenant):\n"
    "    return conn.execute(f\"SELECT * FROM meters WHERE tenant = '{tenant}'\")\n"
)
CLEAN_SOURCE = (
    "def find(conn, tenant):\n"
    "    return conn.execute('SELECT * FROM meters WHERE tenant = ?', (tenant,))\n"
)


# ── driving the seam ────────────────────────────────────────────────────────

def run_hook(script: Path, payload: dict, env_extra: dict | None = None,
             timeout: int = 300) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("SUTRADHAR_GUARD_DIR", None)
    env.pop("SUTRADHAR_HOOK_SELFTEST", None)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(script)], input=json.dumps(payload),
        capture_output=True, text=True, timeout=timeout, env=env,
        cwd=str(REPO_ROOT),
    )


def out(proc: subprocess.CompletedProcess) -> dict:
    """The one JSON object a hook is allowed to print. Empty stdout is a
    silent allow and answers `{}` here."""
    text = proc.stdout.strip()
    if not text:
        return {}
    return json.loads(text)


def decision(proc: subprocess.CompletedProcess) -> str | None:
    return out(proc).get("hookSpecificOutput", {}).get("permissionDecision")


def reason(proc: subprocess.CompletedProcess) -> str:
    o = out(proc)
    return (o.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
            or o.get("reason", "") or o.get("systemMessage", ""))


def pre_tool_use(cwd: Path, command: str = "git commit -m x") -> dict:
    return {
        "session_id": "test-session", "cwd": str(cwd),
        "hook_event_name": "PreToolUse", "tool_name": "Bash",
        "tool_input": {"command": command}, "tool_use_id": "toolu_test",
    }


def marks(tmp_path: Path) -> dict:
    """Per-test marker directory. The Stop hook remembers which HEAD it has
    already reported; without isolation one test silences the next, and the
    suite would be measuring leftovers from the last run."""
    d = tmp_path / "marks"
    d.mkdir(exist_ok=True)
    return {"TMPDIR": str(d)}


def stop(cwd: Path, session: str = "test-session", active: bool = False) -> dict:
    return {
        "session_id": session, "cwd": str(cwd), "hook_event_name": "Stop",
        "stop_hook_active": active, "last_assistant_message": "done",
    }


# ── fixtures ────────────────────────────────────────────────────────────────

def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=t@example.com", *args],
        cwd=str(repo), capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, (args, proc.stdout, proc.stderr)
    return proc.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    # A LOCAL identity, matching the one every commit here is authored with.
    # The Stop hook only runs a `Guard-cmd:` trailer written by the current
    # git user (R16-2), so a fixture whose repo has no `user.email` would
    # exercise the not-my-commit branch on every test in this file.
    git(r, "config", "user.name", "Test")
    git(r, "config", "user.email", "t@example.com")
    (r / "README.md").write_text("fixture\n")
    git(r, "add", "README.md")
    git(r, "commit", "-q", "-m", "initial")
    return r


def with_rounds(repo: Path) -> Path:
    """Give the fixture a valid `docs/rounds/` and DOCTRINE.md, so the rounds
    guard is applicable and green - copied from this repo rather than faked,
    because a hand-written record that happens to parse proves nothing about
    the one the guard actually reads."""
    (repo / "docs").mkdir(exist_ok=True)
    shutil.copytree(REPO_ROOT / "docs" / "rounds", repo / "docs" / "rounds",
                    dirs_exist_ok=True)
    shutil.copy(REPO_ROOT / "DOCTRINE.md", repo / "DOCTRINE.md")
    return repo


def with_baseline(repo: Path) -> Path:
    (repo / "swallow_baseline.json").write_text("{}\n")
    return repo


def stage(repo: Path, name: str, source: str) -> Path:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    git(repo, "add", name)
    return path


def stub_guards(tmp_path: Path, **exits: int) -> Path:
    """A guard directory whose CLIs exit on command.

    This is how a guard's exit code reaches the hook in production - through
    a subprocess - so shaping verdicts this way tests the real partition,
    not a mocked one.
    """
    d = tmp_path / "stub-guards"
    d.mkdir(exist_ok=True)
    for name, code in exits.items():
        (d / f"{name}.py").write_text(
            "import sys\n"
            f"print('[{name}] planted output, exit {code}')\n"
            f"raise SystemExit({code})\n"
        )
    return d


# ── the fast path ───────────────────────────────────────────────────────────

def test_a_non_commit_command_allows_silently(repo: Path):
    proc = run_hook(GATE, pre_tool_use(repo, "ls -la"))
    assert proc.returncode == 0
    assert proc.stdout == "", proc.stdout


def test_a_quoted_git_commit_is_not_a_commit(repo: Path):
    """`echo "git commit"` must not gate. A substring match would, and would
    then run three guards on every echo in the session."""
    proc = run_hook(GATE, pre_tool_use(repo, 'echo "git commit"'))
    assert proc.returncode == 0
    assert proc.stdout == ""


def test_a_commit_inside_a_chain_is_still_a_commit(repo: Path):
    with_rounds(repo)
    proc = run_hook(GATE, pre_tool_use(repo, "npm test && git commit -m x"))
    assert "rounds OK" in reason(proc), proc.stdout


def test_a_non_shell_tool_is_ignored(repo: Path):
    payload = pre_tool_use(repo)
    payload["tool_name"] = "Read"
    proc = run_hook(GATE, payload)
    assert proc.returncode == 0 and proc.stdout == ""


# ── verdicts ────────────────────────────────────────────────────────────────

def test_red_guard_denies_with_the_guards_own_output(repo: Path):
    """The agent gets the text a person would have seen. A paraphrase would
    make it re-run the guard to find out what happened."""
    stage(repo, "app/query.py", RED_SOURCE)
    proc = run_hook(GATE, pre_tool_use(repo))
    assert proc.returncode == 0
    assert decision(proc) == "deny", proc.stdout
    body = reason(proc)
    assert "interpolation_lint" in body
    assert "app/query.py" in body
    assert "interpolation risk" in body
    assert "{tenant}" in body


def test_green_guards_allow_and_name_what_ran(repo: Path):
    with_rounds(with_baseline(repo))
    stage(repo, "app/query.py", CLEAN_SOURCE)
    proc = run_hook(GATE, pre_tool_use(repo))
    assert decision(proc) is None, proc.stdout
    body = reason(proc)
    assert "interpolation_lint OK" in body
    assert "swallow_lint OK" in body
    assert "rounds OK" in body


def test_inapplicable_guard_allows_and_says_which_one(repo: Path):
    """Doctrine 2.9: a guard that did not run is reported as not run. The
    instrument's own absence is never a reason to block - a gate that
    refused every repo without a baseline would be uninstalled by lunch."""
    stage(repo, "app/query.py", CLEAN_SOURCE)
    proc = run_hook(GATE, pre_tool_use(repo))
    assert decision(proc) is None
    body = reason(proc)
    assert "swallow_lint skipped" in body and "swallow_baseline.json" in body
    assert "rounds skipped" in body


def test_measuring_nothing_is_not_reported_as_green(repo: Path):
    """Every guard inapplicable: allowed, and said out loud. A gate with no
    applicable instrument reporting silence is the empty-200 lie."""
    stage(repo, "notes.md", "# not code\n")
    proc = run_hook(GATE, pre_tool_use(repo))
    assert decision(proc) is None
    assert "measured NOTHING" in reason(proc)


def test_gate_names_the_tree_it_measured(repo: Path):
    """Backflow B-15: a gate must prove it gated the tree you are pushing.
    These guards read the working tree; the commit takes the index. When
    they differ the message says so, and never implies otherwise."""
    path = stage(repo, "app/query.py", CLEAN_SOURCE)
    path.write_text(CLEAN_SOURCE + "# changed after staging\n")
    body = reason(run_hook(GATE, pre_tool_use(repo)))
    assert "working tree" in body
    assert "staged path(s) differ" in body
    assert "app/query.py" in body


def test_commit_dash_a_widens_the_scope_to_tracked_changes(repo: Path):
    """`git commit -a` stages tracked modifications at commit time, so a
    dirty tracked file IS part of the commit and must be scanned."""
    stage(repo, "app/query.py", CLEAN_SOURCE)
    git(repo, "commit", "-q", "-m", "clean")
    (repo / "app" / "query.py").write_text(RED_SOURCE)
    proc = run_hook(GATE, pre_tool_use(repo, "git commit -am wip"))
    assert decision(proc) == "deny", proc.stdout


# ── the honesty rule ────────────────────────────────────────────────────────

@pytest.mark.parametrize("script", [GATE, DONE], ids=["precommit", "stop"])
def test_a_crashing_hook_allows_with_an_instrument_message(
        script: Path, repo: Path, tmp_path: Path):
    """Mutation verification of the catch-all itself (2.2): the hook is made
    to raise inside its own body, and must still allow - naming ITSELF as
    the failing party, with the exception TYPE, because "something went
    wrong" attached to a commit is read as a finding about the commit."""
    payload = pre_tool_use(repo) if script == GATE else stop(repo)
    proc = run_hook(script, payload,
                    {"SUTRADHAR_HOOK_SELFTEST": "raise", **marks(tmp_path)})
    assert proc.returncode == 0, proc.stderr
    body = out(proc)
    assert "instrument failure" in body["systemMessage"]
    assert "RuntimeError" in body["systemMessage"]
    assert "hookSpecificOutput" not in body and "decision" not in body
    assert "instrument failure" in proc.stderr


@pytest.mark.parametrize("script", [GATE, DONE], ids=["precommit", "stop"])
def test_a_missing_guard_directory_is_an_instrument_failure(
        script: Path, repo: Path, tmp_path: Path):
    with_rounds(repo)
    stage(repo, "app/query.py", RED_SOURCE)
    git(repo, "commit", "-q", "-m", "red\n\nGuard-cmd: true")
    stage(repo, "app/other.py", RED_SOURCE)
    payload = pre_tool_use(repo) if script == GATE else stop(repo)
    proc = run_hook(script, payload,
                    {"SUTRADHAR_GUARD_DIR": "/nope/not/here", **marks(tmp_path)})
    assert proc.returncode == 0
    body = out(proc)
    assert "decision" not in body and "hookSpecificOutput" not in body
    assert "instrument failure" in body["systemMessage"]
    assert "not/here" in body["systemMessage"]


def test_an_unknown_exit_code_never_becomes_a_pass(repo: Path, tmp_path: Path):
    """The partition is a lookup with an explicit instrument default. The
    tempting shape - `if code: red else: green` - turns every code nobody
    anticipated into a pass, silently, in the direction that costs most."""
    stage(repo, "app/query.py", CLEAN_SOURCE)
    stubs = stub_guards(tmp_path, interpolation_lint=7)
    proc = run_hook(GATE, pre_tool_use(repo), {"SUTRADHAR_GUARD_DIR": str(stubs)})
    assert decision(proc) is None
    body = reason(proc)
    assert "exited 7" in body and "not a verdict" in body
    assert "INSTRUMENT-FAILURE" in body


def test_a_red_guard_still_denies_when_another_guard_broke(repo: Path, tmp_path: Path):
    """A finding is a finding even when a second instrument failed; the
    denial is justified by the guard that RAN, and the failure is reported
    alongside rather than swallowed."""
    with_baseline(repo)
    stage(repo, "app/query.py", RED_SOURCE)
    stubs = stub_guards(tmp_path, swallow_lint=9)
    shutil.copy(REPO_ROOT / "python" / "sutradhar_guards" / "interpolation_lint.py",
                stubs / "interpolation_lint.py")
    proc = run_hook(GATE, pre_tool_use(repo), {"SUTRADHAR_GUARD_DIR": str(stubs)})
    assert decision(proc) == "deny"
    body = reason(proc)
    assert "interpolation_lint" in body
    assert "exited 9" in body


def test_the_gate_says_nothing_outside_a_git_repository(tmp_path: Path):
    proc = run_hook(GATE, pre_tool_use(tmp_path, "git commit -m x"))
    assert proc.returncode == 0
    assert "instrument failure" in out(proc)["systemMessage"]
    assert "hookSpecificOutput" not in out(proc)


# ── the Stop hook ───────────────────────────────────────────────────────────

def commit_with_trailer(repo: Path, trailer: str = "true") -> None:
    stage(repo, "app/query.py", CLEAN_SOURCE)
    git(repo, "commit", "-q", "-m", f"fix\n\nGuard-cmd: {trailer}")


def test_stop_hook_blocks_on_decoration(repo: Path, tmp_path: Path):
    """DECORATION uses the documented Stop decision shape: top-level
    `decision: "block"` with `reason`. NOT `hookSpecificOutput.continue` -
    a summary of the docs said that, and the raw page does not."""
    commit_with_trailer(repo)
    stubs = stub_guards(tmp_path, verify_guard=1)
    proc = run_hook(DONE, stop(repo),
                    {"SUTRADHAR_GUARD_DIR": str(stubs), **marks(tmp_path)})
    body = out(proc)
    assert body["decision"] == "block", body
    assert "DECORATION" in body["reason"]
    assert "planted output" in body["reason"]
    assert "Guard-cmd: true" in body["reason"]


def test_stop_hook_reports_inconclusive_as_inconclusive(repo: Path, tmp_path: Path):
    """Doctrine 2.9. INCONCLUSIVE is not a pass and not a block: it is said
    by name, with what would resolve it. Reported as either of the other two
    it becomes a lie in one direction or a loop in the other."""
    commit_with_trailer(repo)
    stubs = stub_guards(tmp_path, verify_guard=2)
    proc = run_hook(DONE, stop(repo),
                    {"SUTRADHAR_GUARD_DIR": str(stubs), **marks(tmp_path)})
    body = out(proc)
    assert "decision" not in body, body
    assert "INCONCLUSIVE" in body["systemMessage"]
    assert "NOT a pass" in body["systemMessage"]


def test_stop_hook_is_silent_when_the_guard_is_verified(repo: Path, tmp_path: Path):
    commit_with_trailer(repo)
    stubs = stub_guards(tmp_path, verify_guard=0)
    proc = run_hook(DONE, stop(repo),
                    {"SUTRADHAR_GUARD_DIR": str(stubs), **marks(tmp_path)})
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout


def test_stop_hook_respects_stop_hook_active(repo: Path, tmp_path: Path):
    """The harness overrides a Stop hook after eight consecutive blocks. A
    hook that has to be overridden is a hook that gets removed."""
    commit_with_trailer(repo)
    stubs = stub_guards(tmp_path, verify_guard=1)
    proc = run_hook(DONE, stop(repo, active=True),
                    {"SUTRADHAR_GUARD_DIR": str(stubs), **marks(tmp_path)})
    assert proc.returncode == 0 and proc.stdout == ""


def test_stop_hook_reports_a_head_once_per_session(repo: Path, tmp_path: Path):
    """Stop fires every turn. Re-running the verifier - and re-blocking -
    on every one of them is how this hook would earn its own uninstall."""
    commit_with_trailer(repo)
    stubs = stub_guards(tmp_path, verify_guard=1)
    env = {"SUTRADHAR_GUARD_DIR": str(stubs), **marks(tmp_path)}
    first = run_hook(DONE, stop(repo, session="s1"), env)
    second = run_hook(DONE, stop(repo, session="s1"), env)
    assert out(first)["decision"] == "block"
    assert second.stdout == "", second.stdout
    other = run_hook(DONE, stop(repo, session="s2"), env)
    assert out(other)["decision"] == "block", "a new session is a new report"


def test_stop_hook_reminds_when_prod_and_test_move_without_a_trailer(
        repo: Path, tmp_path: Path):
    """A reminder, never a block: the commit already happened, and a Stop
    block over a missing trailer is a loop the agent cannot exit by
    working."""
    stage(repo, "app/billing.py", CLEAN_SOURCE)
    stage(repo, "tests/test_billing.py", "def test_x():\n    assert True\n")
    git(repo, "commit", "-q", "-m", "fix billing")
    proc = run_hook(DONE, stop(repo), marks(tmp_path))
    body = out(proc)
    assert "decision" not in body, body
    assert "Guard-cmd:" in body["systemMessage"]
    assert "app/billing.py" in body["systemMessage"]


def test_stop_hook_will_not_run_someone_elses_trailer(repo: Path, tmp_path: Path):
    """R16-2. A `Guard-cmd:` trailer is a command that runs on this machine.

    HEAD is whatever is checked out - a pulled branch, a contributor's PR, a
    merge - so "the commit at HEAD" and "a commit this developer wrote" are
    different things, and the hook may only act on the second. The planted
    trailer writes a sentinel file: if the hook spawned `verify_guard`, the
    file exists, and no assertion about the message would have noticed.
    """
    sentinel = tmp_path / "the-trailer-ran"
    script = tmp_path / "trailer.py"
    script.write_text(f"open({str(sentinel)!r}, 'w').close()\n")
    trailer = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"

    stage(repo, "app/query.py", CLEAN_SOURCE)
    subprocess.run(
        ["git", "-c", "user.name=Someone Else",
         "-c", "user.email=someone-else@example.com",
         "commit", "-q", "-m", f"their fix\n\nGuard-cmd: {trailer}"],
        cwd=str(repo), capture_output=True, text=True, timeout=60, check=True,
    )

    proc = run_hook(DONE, stop(repo), marks(tmp_path))
    body = out(proc)
    assert "decision" not in body, body
    assert "someone-else@example.com" in body["systemMessage"], body
    assert "t@example.com" in body["systemMessage"], body
    assert "verify_guard.py" in body["systemMessage"], body
    assert not sentinel.exists(), (
        "the hook RAN a command chosen by whoever authored HEAD. Checking out "
        "a pull request is enough to reach this path.")


def test_stop_hook_will_not_run_a_trailer_when_the_repo_has_no_identity(
        repo: Path, tmp_path: Path):
    """Unset `user.email` is not a match. It cannot be: nothing in the
    repository can then say the commit is yours, and defaulting to "run it"
    would make the check disappear on exactly the machines least configured
    to have one."""
    commit_with_trailer(repo)
    subprocess.run(["git", "config", "--unset", "user.email"], cwd=str(repo),
                   capture_output=True, text=True, timeout=60)
    stubs = stub_guards(tmp_path, verify_guard=1)
    proc = run_hook(DONE, stop(repo), {
        "SUTRADHAR_GUARD_DIR": str(stubs),
        # Unsetting the LOCAL identity is not enough: git falls back to the
        # global file, which on a developer's machine is set. The hook must
        # be tested against a repository that genuinely has no identity.
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
        **marks(tmp_path)})
    body = out(proc)
    assert "decision" not in body, body
    assert "no `user.email` set" in body["systemMessage"], body


def test_stop_hook_runs_the_trailer_when_the_commit_is_yours(
        repo: Path, tmp_path: Path):
    """The other half of the pair. An author check that refused everything
    would pass the test above while switching the whole hook off."""
    commit_with_trailer(repo)
    stubs = stub_guards(tmp_path, verify_guard=1)
    proc = run_hook(DONE, stop(repo),
                    {"SUTRADHAR_GUARD_DIR": str(stubs), **marks(tmp_path)})
    body = out(proc)
    assert body.get("decision") == "block", body
    assert "DECORATION" in body["reason"]


def test_stop_hook_is_silent_on_a_docs_only_commit(repo: Path, tmp_path: Path):
    stage(repo, "docs/notes.md", "# notes\n")
    git(repo, "commit", "-q", "-m", "docs")
    proc = run_hook(DONE, stop(repo), marks(tmp_path))
    assert proc.returncode == 0 and proc.stdout == ""


def test_stop_hook_is_silent_outside_a_git_repository(tmp_path: Path):
    """This event fires on every turn. A message here would be noise in
    every session in every non-git directory, and noise is what gets a hook
    removed - there is nothing to verify, so nothing is claimed."""
    proc = run_hook(DONE, stop(tmp_path), marks(tmp_path))
    assert proc.returncode == 0 and proc.stdout == ""


# ── budgets ─────────────────────────────────────────────────────────────────

def _budget_repo(tmp_path: Path) -> Path:
    r = tmp_path / "budget-repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    (r / "README.md").write_text("fixture\n")
    git(r, "add", "README.md")
    git(r, "commit", "-q", "-m", "initial")
    with_rounds(with_baseline(r))
    stage(r, "app/query.py", CLEAN_SOURCE)
    return r


def test_precommit_gate_holds_its_declared_envelope(tmp_path: Path):
    """`b.n` IS the 10 declared in docs/design/agent-loop-hooks.md.

    The ceiling is a tripwire, not a fit. R14-2 is a guard that was correct
    and was switched off the same afternoon because its signal cost more
    than it paid; a gate on every commit has the same failure with a
    shorter fuse. The shape this catches is a slow guard moving into the
    fast path - `verify_guard` (688-778 ms by mcp-server.md) or a test
    suite - which lands one to two orders of magnitude past the ceiling.
    """
    repo = _budget_repo(tmp_path)
    payload = pre_tool_use(repo)
    assert decision(run_hook(GATE, payload)) is None, "warm-up must be green"
    n = get_budget("precommit-gate", root=DESIGN).n
    with budget("precommit-gate", root=DESIGN) as b:
        for _ in range(b.n):
            proc = run_hook(GATE, payload)
            assert proc.returncode == 0
    assert n == b.n


def test_fast_path_costs_about_what_the_interpreter_costs(repo: Path):
    """The fast path fires on EVERY Bash call, so its budget is a ratio to a
    bare interpreter start measured in the same run - an absolute figure for
    a path dominated by CPython startup measures the machine, not the
    change. It goes red when the hook starts doing work (a git call, a walk,
    an import) before it knows the command is even a commit.
    """
    payload = pre_tool_use(repo, "ls -la")
    run_hook(GATE, payload)  # warm the filesystem cache
    rounds = 12

    t0 = time.perf_counter()
    for _ in range(rounds):
        subprocess.run([sys.executable, "-c", "pass"], capture_output=True)
    bare = (time.perf_counter() - t0) / rounds

    t0 = time.perf_counter()
    for _ in range(rounds):
        run_hook(GATE, payload)
    hook = (time.perf_counter() - t0) / rounds

    assert hook <= bare * FAST_PATH_BUDGET_FACTOR, (
        f"fast path {hook * 1000:.1f} ms vs bare interpreter {bare * 1000:.1f} ms "
        f"= {hook / bare:.1f}x, over the declared {FAST_PATH_BUDGET_FACTOR}x")


def test_fast_path_factor_matches_the_design_note():
    """Pin the note to the constant. A budget stated in prose and enforced
    from a different number is two budgets, and the wrong one is the one
    people read."""
    text = NOTE.read_text()
    assert f"{FAST_PATH_BUDGET_FACTOR} (`FAST_PATH_BUDGET_FACTOR`)" in text


# ── class ratchets over the plugin ──────────────────────────────────────────

# Read from <https://code.claude.com/docs/en/hooks> on 2026-09-04. A hook
# registered under a name outside this set never fires, silently, and the
# only symptom is a guard that never runs.
DOCUMENTED_EVENTS = {
    "SessionStart", "Setup", "UserPromptSubmit", "UserPromptExpansion",
    "PreToolUse", "PermissionRequest", "PermissionDenied", "PostToolUse",
    "PostToolUseFailure", "PostToolBatch", "Notification", "MessageDisplay",
    "SubagentStart", "SubagentStop", "TaskCreated", "TaskCompleted", "Stop",
    "StopFailure", "TeammateIdle", "InstructionsLoaded", "ConfigChange",
    "CwdChanged", "DirectoryAdded", "FileChanged", "WorktreeCreate",
    "WorktreeRemove", "PreCompact", "PostCompact", "PreModelSwitch",
    "PostModelSwitch", "Elicitation", "ElicitationResult", "SessionEnd",
}


def test_hooks_json_matches_the_documented_schema():
    config = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
    assert set(config) == {"hooks"}
    assert config["hooks"], "a hooks.json with no events registers nothing"
    for event, entries in config["hooks"].items():
        assert event in DOCUMENTED_EVENTS, f"{event} is not a documented event"
        for entry in entries:
            for handler in entry["hooks"]:
                assert handler["type"] == "command"
                # Exec form: `args` present, so path placeholders are passed
                # as single arguments with no shell quoting to get wrong.
                assert handler["args"], "path placeholders need exec form"
                target = handler["args"][0]
                assert target.startswith("${CLAUDE_PLUGIN_ROOT}/"), target
                script = PLUGIN / target.split("}/", 1)[1]
                assert script.is_file(), f"{event} points at a missing {script}"


def test_mcp_json_points_inside_the_plugin(tmp_path: Path):
    """It used to point at `${CLAUDE_PLUGIN_ROOT}/../python/sutradhar_guards`
    - referenced, not copied, so there would be one server and one version.

    That was right about the risk and wrong about the mechanism. An
    installed plugin is copied into `~/.claude/plugins/cache` WITHOUT the
    files around it, so `../` resolved from a checkout and would simply not
    exist after a marketplace install (R16-1). The server is now bundled,
    and the second-answer risk is answered by
    `test_plugin_bundle.py`, which fails on a one-byte divergence.
    """
    config = json.loads((PLUGIN / ".mcp.json").read_text())
    server = config["mcpServers"]["sutradhar-guards"]
    target = server["args"][0]
    assert target.startswith("${CLAUDE_PLUGIN_ROOT}/")
    assert "/.." not in target, target
    resolved = (PLUGIN / target.split("}/", 1)[1]).resolve()
    assert resolved.is_file()
    assert PLUGIN.resolve() in resolved.parents


def test_plugin_manifest_is_where_the_docs_say_it_is():
    manifest = PLUGIN / ".claude-plugin" / "plugin.json"
    data = json.loads(manifest.read_text())
    assert data["name"] == "sutradhar"
    # Every other component lives at the plugin ROOT. The docs call the
    # inverse the common mistake, and it fails silently: the component is
    # simply never discovered.
    for component in ("hooks", "skills", "scripts", ".mcp.json"):
        assert (PLUGIN / component).exists()
        assert not (PLUGIN / ".claude-plugin" / component).exists()


def test_every_canonical_skill_has_a_plugin_wrapper():
    """A class ratchet, not a pair of point tests: a skill added to
    `agent/skills/` later is covered the day it lands, rather than being
    silently absent from the plugin until someone notices."""
    canonical = sorted((REPO_ROOT / "agent" / "skills").glob("*.md"))
    assert canonical, "no canonical skills found - the ratchet would pass vacuously"
    for path in canonical:
        wrapper = PLUGIN / "skills" / path.stem / "SKILL.md"
        assert wrapper.is_file(), f"{path.name} has no plugin wrapper"
        text = wrapper.read_text()
        assert text.startswith("---\n") and "description:" in text.split("---")[1]
        assert f"${{CLAUDE_PLUGIN_ROOT}}/../agent/skills/{path.name}" in text


def test_no_hook_script_can_shell_out_or_exit_2():
    """Two invariants that walk the source rather than one example each.

    `shell=True` would make a repo path containing a semicolon a command.
    Exit 2 is the harness's BLOCK signal, so a hook that reaches it by any
    path - including a usage error in its own configuration - denies
    somebody's commit for our mistake.

    Over the AST, not the text: a substring search reads the sentence in
    `_hooklib` that promises never to pass `shell=True` as a violation of
    itself, which is a guard that goes red at the documentation of its own
    rule and teaches everyone to delete it.
    """
    scripts = sorted(SCRIPTS.glob("*.py"))
    assert len(scripts) >= 3
    for path in scripts:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    assert not (kw.arg == "shell"
                                and isinstance(kw.value, ast.Constant)
                                and kw.value.value), f"{path}:{node.lineno} shell=True"
                name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
                if name in ("SystemExit", "exit", "_exit") and node.args:
                    arg = node.args[0]
                    assert not (isinstance(arg, ast.Constant) and arg.value == 2), (
                        f"{path}:{node.lineno} exits 2, which BLOCKS")


@pytest.mark.parametrize("script", [GATE, DONE], ids=["precommit", "stop"])
def test_each_hook_has_a_selfcheck_that_could_fail(script: Path):
    """Doctrine 6.7: an exit code is evidence only in pairs. `--selfcheck`
    exiting 0 proves the file imported; the unknown-flag case is what makes
    that zero informative.

    The unknown flag exits 1, not 2, and that is deliberate: 2 blocks. A
    typo in this hook's own configuration must not be able to deny a user's
    tool call.
    """
    ok = subprocess.run([sys.executable, str(script), "--selfcheck"],
                        capture_output=True, text=True, timeout=120)
    assert ok.returncode == 0, ok.stderr
    assert "selfcheck OK" in ok.stdout

    bad = subprocess.run([sys.executable, str(script), "--zzz-not-a-real-flag"],
                         capture_output=True, text=True, timeout=120)
    assert bad.returncode == 1, (bad.returncode, bad.stdout, bad.stderr)
    assert "unknown flag" in bad.stderr
    assert bad.stdout == "", "a usage error must not print a decision"
