#!/usr/bin/env python3
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Run Sutradhar's guards for the GitHub Action (`action.yml` at the root).

`action.yml` is a composite action with one step: it hands every input to
this script through an environment variable and runs it with the runner's
`python3`. Nothing here goes through a shell. An input is never pasted into
a `run:` body - that is the Actions injection hole, and doctrine 2.8's shape
in YAML - and every guard is started as an argument list, so a value cannot
become a command whatever it holds. A value that looks like a shell
metacharacter or a flag where a path belongs is still refused, because it is
far more likely a mistake than a path, and a mistake read as a path scans
the wrong tree and says OK.

What runs by default, with no configuration:

    swallow            swallow_lint.py over PATHS          (2.7)
    interpolation      interpolation_lint.py over PATHS    (2.8)
    conflated-degrade  conflated_degrade_lint.py over PATHS (2.7)
    ci-step            ci_step_lint.py over WORKFLOWS      (6.3, 6.7)

Opt in by naming them in `guards`: `budget` (needs a design-notes directory
and a tests directory, 1.1) and `rounds` (needs round records, 8.1).
`framework_only` and `framework_shape` are refused by name: they gate a
promise only the Sutradhar repository makes, and in an adopter's tree they
can only ever pass (R20-4). A gate that cannot fail is decoration (3.7).

Every guard exits 0 clean, 1 a finding, 2 could not run. Read here as:

    0                  pass
    1                  finding - fails the job
    2                  could not run - fails the job unless
                       on-cannot-run is `skip`, and is never silent
    70, or anything else:
                       crashed - fails the job whatever on-cannot-run says.
                       A crash is the instrument's failure, not a verdict
                       about the code (6.8, 6.11), and it is named as such.

A crash is decided by the exit code alone, never by reading the output. A
guard's output quotes the pull request under test - an f-string expression,
a filename - on stdout and on stderr alike, so any text test over it is a
verdict the pull request can forge: a file named `Traceback (most recent
call last).py` used to turn a finding into "crashed - the guard failed, not
your code" (R24-1). Each guard is therefore started under a launcher this
script owns (`_LAUNCH`), which runs it exactly as `python3 guard.py` would
and turns an exception that escapes the guard - including a guard file that
cannot be read - into exit 70, a code no guard uses. Every adopter-derived
string written to the step summary is escaped to inert text (`md_inert`).

`on-cannot-run` defaults to `fail`, because a job that goes green when a
guard read nothing is the R21-2 lie (an OK over zero files) told one level
up. `skip` exists for a tree where a guard deliberately has nothing to read;
each skip still prints the guard's own sentence, raises a warning annotation
and a row in the step summary, and a run in which every selected guard was
skipped fails anyway - nothing was checked, and that is not a pass (2.9).

On a pull request the two ratchet baselines are also compared with the base
branch's copies (`baseline-vs-base`, default `check`): a pull request that adds
a swallow and banks it in the same diff is a finding, because otherwise the
gate reads the floor the change itself just raised (B-64). The base copy is
read with `git cat-file` from the base commit the event names, fetched at
depth 1 if the checkout does not hold it; it is data, parsed as JSON by the
guard, and nothing from it is run. A base copy that cannot be had is a named
could-not-run row, under the same `on-cannot-run` as everything else. On any
other event there is no base to compare with, and the summary says so.

Usage (the action sets these; locally you can too):

    SUTRADHAR_PATHS=src python3 action/run_guards.py
    python3 action/run_guards.py --selfcheck

Exit 0 every guard that ran passed, 1 a finding or a crashed guard, 2 the
run could not be made: an input refused, or a guard could not run under
`on-cannot-run: fail`, or nothing at all was checked.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

GUARDS_DIR = Path(__file__).resolve().parent.parent / "python" / "sutradhar_guards"

#: name -> script. The order is the order they run in.
SCRIPTS = {
    "swallow": "swallow_lint.py",
    "interpolation": "interpolation_lint.py",
    "conflated-degrade": "conflated_degrade_lint.py",
    "ci-step": "ci_step_lint.py",
    "budget": "budget.py",
    "rounds": "rounds.py",
}
DEFAULT_GUARDS = ("swallow", "interpolation", "conflated-degrade", "ci-step")
OPT_IN_GUARDS = ("budget", "rounds")

#: Named so the refusal can say why, instead of "unknown guard".
REFUSED_GUARDS = {
    "framework-only": "framework_only.py",
    "framework_only": "framework_only.py",
    "framework-shape": "framework_shape.py",
    "framework_shape": "framework_shape.py",
}

#: name -> environment variable action.yml sets. One table, so the test that
#: every declared input reaches this script reads the same names this does.
ENV = {
    "guards": "SUTRADHAR_GUARDS",
    "paths": "SUTRADHAR_PATHS",
    "workflows": "SUTRADHAR_WORKFLOWS",
    "on-cannot-run": "SUTRADHAR_ON_CANNOT_RUN",
    "swallow-baseline": "SUTRADHAR_SWALLOW_BASELINE",
    "conflated-degrade-baseline": "SUTRADHAR_CONFLATED_DEGRADE_BASELINE",
    "interpolation-allowlist": "SUTRADHAR_INTERPOLATION_ALLOWLIST",
    "interpolation-keywords": "SUTRADHAR_INTERPOLATION_KEYWORDS",
    "design-dir": "SUTRADHAR_DESIGN_DIR",
    "tests-dir": "SUTRADHAR_TESTS_DIR",
    "rounds-dir": "SUTRADHAR_ROUNDS_DIR",
    "baseline-vs-base": "SUTRADHAR_BASELINE_VS_BASE",
}
DEFAULTS = {
    "guards": ",".join(DEFAULT_GUARDS),
    "paths": ".",
    "workflows": ".github/workflows",
    "on-cannot-run": "fail",
    "swallow-baseline": "",
    "conflated-degrade-baseline": "",
    "interpolation-allowlist": "",
    "interpolation-keywords": "",
    "design-dir": "docs/design",
    "tests-dir": "tests",
    "rounds-dir": "docs/rounds",
    "baseline-vs-base": "check",
}

#: guard -> (baseline input, the file the guard reads when none is named,
#: what an empty baseline of its shape is). B-64.
RATCHETS = {
    "swallow": ("swallow-baseline", "swallow_baseline.json", "{}"),
    "conflated-degrade": ("conflated-degrade-baseline",
                          "conflated_degrade_baseline.json", "[]"),
}
_SHA_RX = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")

#: A path is letters, digits, and `. _ / -`, and does not start with `-`.
#: Narrow on purpose: everything outside it is either a shell metacharacter
#: or a character no repository path needs, and the refusal names it.
_PATH_RX = re.compile(r"[A-Za-z0-9._/][A-Za-z0-9._/-]*")
_KEYWORDS_RX = re.compile(r"[A-Za-z][A-Za-z ,]*")

#: The exit code the launcher gives an exception that escaped a guard. No
#: guard returns it: they exit 0, 1 or 2 (EX_SOFTWARE, sysexits.h).
CRASH_EXIT = 70

#: Every interpreter this driver starts, and the only place one is spelled.
#: `-I` is isolated mode: no '' (the cwd, which is the adopter's checkout and
#: so the pull request's tree) on sys.path, no PYTHONPATH, no user site. R24-1
#: started guards as `python3 -c`, which puts the cwd first on sys.path before
#: the first line runs, so a `traceback.py` at the root of the pull request
#: ran inside the adopter's job with its token (R24-22). A class test walks
#: every subprocess this module starts and refuses one not built here.
PYTHON = (sys.executable, "-I")


def _python(*args: str) -> list:
    """argv for an isolated interpreter running ``args``."""
    return [*PYTHON, *args]


#: The only other program this driver starts: git, to read the base
#: branch's copy of a baseline. `cat-file` applies no filter, textconv or
#: attribute from the pull request's tree, and no hook runs on it or fetch.
GIT = ("git", "-c", "core.hooksPath=/dev/null")


def _git(*args: str) -> list:
    """argv for git running ``args``."""
    return [*GIT, *args]


#: Runs one guard as `python3 <guard> <args>` would - same argv, the guard's
#: own directory first on sys.path, `__main__` - and owns the one decision
#: the output cannot be trusted with: an exception escaping the guard (or a
#: guard file that cannot be read) prints its traceback to stderr and exits
#: CRASH_EXIT. SystemExit is the guard's own verdict and passes through
#: untouched. Under -I sys.path[0] is a stdlib entry, so the guard's
#: directory is inserted before it, never written over it.
_LAUNCH = (
    "import os, runpy, sys, traceback\n"
    "script = sys.argv[1]\n"
    "sys.argv = sys.argv[1:]\n"
    "sys.path.insert(0, os.path.dirname(os.path.abspath(script)))\n"
    "try:\n"
    "    runpy.run_path(script, run_name='__main__')\n"
    "except SystemExit:\n"
    "    raise\n"
    "except BaseException:\n"
    "    sys.stdout.flush()\n"
    "    traceback.print_exc()\n"
    "    sys.stderr.flush()\n"
    f"    os._exit({CRASH_EXIT})\n"
)

#: Every ASCII punctuation character. Each one that opens a Markdown or GFM
#: construct is in here, so escaping all of them is complete by construction
#: rather than by a list someone has to keep current.
_MD_PUNCT = set("!\"#$%'()*+,-./:;=?@[\\]^_`{|}~")


class Refused(Exception):
    """An input this script will not act on. Exit 2, with the reason."""


def _say(msg: str) -> None:
    print(f"[sutradhar-action] {msg}", flush=True)


def _escape_data(s: str) -> str:
    """GitHub workflow-command data escaping (%, CR, LF)."""
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(s: str) -> str:
    """Workflow-command property escaping: data's, plus `:` and `,`."""
    return _escape_data(s).replace(":", "%3A").replace(",", "%2C")


def md_inert(s: str) -> str:
    """``s`` as Markdown that renders as exactly its own text, and nothing else.

    For adopter-derived text in GITHUB_STEP_SUMMARY, which GitHub renders as
    GFM with HTML. Complete by construction, not by list: `&`, `<` and `>`
    become character references, so no tag, entity or `<...>` autolink can
    open; every other ASCII punctuation character is backslash-escaped, which
    CommonMark defines for exactly that set and which renders it literally -
    and every inline construct (emphasis, code, link, image, strikethrough, a
    table's cell bar, a hard break) and every block marker opens with one of
    them. GFM's extended autolinks need `://`, `www.` or `@` as one run of
    text; an escape splits the run, so none forms. Line breaks become spaces,
    so the text cannot leave its table cell.
    """
    out = []
    for ch in " ".join(s.split()):
        if ch == "&":
            out.append("&amp;")
        elif ch == "<":
            out.append("&lt;")
        elif ch == ">":
            out.append("&gt;")
        elif ch in _MD_PUNCT:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def check_path(name: str, value: str) -> str:
    """Return ``value`` if it is a plain relative-or-absolute path, else raise.

    A leading `-` is refused as well as the metacharacters: a path of
    `--update-baseline` would reach the guard as a flag and rewrite the
    adopter's baseline instead of checking against it.
    """
    if _PATH_RX.fullmatch(value):
        return value
    bad = sorted({c for c in value if not re.fullmatch(r"[A-Za-z0-9._/-]", c)})
    if value.startswith("-"):
        why = "starts with '-', so a guard would read it as a flag"
    else:
        why = f"contains {' '.join(repr(c) for c in bad)}"
    raise Refused(
        f"input `{name}` value {value!r} {why}. A path here is letters, "
        f"digits, '.', '_', '/' and '-', not starting with '-'; nothing was "
        f"run."
    )


def read_config(environ: "dict[str, str]") -> dict:
    """Inputs from the environment, validated. Raises Refused."""
    raw = {k: environ.get(v, DEFAULTS[k]).strip() for k, v in ENV.items()}

    names = [g for g in re.split(r"[\s,]+", raw["guards"]) if g]
    if not names:
        raise Refused("input `guards` is empty; name at least one guard. "
                      "Nothing was run.")
    guards: list = []
    for g in names:
        if g in REFUSED_GUARDS:
            raise Refused(
                f"guard `{g}` is not offered: {REFUSED_GUARDS[g]} gates a "
                f"promise only the Sutradhar repository makes, and in your "
                f"tree it can only ever pass (R20-4). Nothing was run."
            )
        if g not in SCRIPTS:
            raise Refused(
                f"unknown guard `{g}`. Default: {', '.join(DEFAULT_GUARDS)}; "
                f"opt-in: {', '.join(OPT_IN_GUARDS)}. Nothing was run."
            )
        if g not in guards:
            guards.append(g)

    policy = raw["on-cannot-run"]
    if policy not in ("fail", "skip"):
        raise Refused(
            f"input `on-cannot-run` is {policy!r}; it is `fail` or `skip`. "
            f"Nothing was run."
        )

    paths = [check_path("paths", p) for p in raw["paths"].split()]
    if not paths:
        raise Refused("input `paths` is empty; name the directory that "
                      "holds your Python source. Nothing was run.")

    single = {}
    for key in ("workflows", "swallow-baseline", "conflated-degrade-baseline",
                "interpolation-allowlist", "design-dir", "tests-dir",
                "rounds-dir"):
        v = raw[key]
        if len(v.split()) > 1:
            raise Refused(f"input `{key}` names more than one path: {v!r}. "
                          f"Nothing was run.")
        single[key] = check_path(key, v) if v else ""

    # A baseline or allowlist the adopter NAMED must be there. A typo would
    # otherwise run the ratchet against an empty floor and nobody would know
    # which file had been meant.
    for key in ("swallow-baseline", "conflated-degrade-baseline",
                "interpolation-allowlist"):
        if single[key] and not Path(single[key]).is_file():
            raise Refused(f"input `{key}` names {single[key]}, which is not "
                          f"a file. Nothing was run.")

    vs_base = raw["baseline-vs-base"]
    if vs_base not in ("check", "off"):
        raise Refused(f"input `baseline-vs-base` is {vs_base!r}; it is "
                      f"`check` or `off`. Nothing was run.")

    kw = raw["interpolation-keywords"]
    if kw and not _KEYWORDS_RX.fullmatch(kw):
        raise Refused(f"input `interpolation-keywords` is {kw!r}; it is a "
                      f"comma-separated list of words such as `sql,cypher`. "
                      f"Nothing was run.")

    return {"guards": guards, "policy": policy, "paths": paths,
            "keywords": kw, "baseline-vs-base": vs_base, **single}


def plan(cfg: dict) -> list:
    """[(guard, argv-after-script, could-not-run sentence or None)]."""
    out = []
    for g in cfg["guards"]:
        pre = None
        if g == "swallow":
            args = list(cfg["paths"])
            if cfg["swallow-baseline"]:
                args += ["--baseline", cfg["swallow-baseline"]]
        elif g == "interpolation":
            args = list(cfg["paths"])
            if cfg["keywords"]:
                args += ["--keywords", cfg["keywords"].replace(" ", "")]
            if cfg["interpolation-allowlist"]:
                args += ["--allowlist", cfg["interpolation-allowlist"]]
        elif g == "conflated-degrade":
            args = list(cfg["paths"])
            if cfg["conflated-degrade-baseline"]:
                args += ["--baseline", cfg["conflated-degrade-baseline"]]
        elif g == "ci-step":
            args = [cfg["workflows"] or DEFAULTS["workflows"]]
        elif g == "budget":
            design, tests = cfg["design-dir"], cfg["tests-dir"]
            args = [design, "--tests", tests]
            # budget.py says "nothing to check" and exits 0 over a missing
            # notes directory - right for a hook that runs everywhere, wrong
            # for a guard the adopter asked for by name. Checked here.
            missing = [p for p in (design, tests) if not p or not Path(p).is_dir()]
            if missing:
                pre = (f"budget was asked for, and not a directory: "
                       f"{', '.join(repr(m) for m in missing)}; set "
                       f"`design-dir` and `tests-dir`. Nothing was checked.")
        elif g == "rounds":
            args = [cfg["rounds-dir"] or DEFAULTS["rounds-dir"], "--check"]
        else:  # read_config refuses unknown names; this is a seam, not a path
            raise Refused(f"no plan for guard {g!r}")
        out.append((g, args, pre))
    return out


def _base_sha(environ: "dict[str, str]") -> "tuple[str | None, str]":
    """(the base commit of this pull request, or None with the reason)."""
    if environ.get("GITHUB_EVENT_NAME") not in ("pull_request",
                                                "pull_request_target"):
        return None, ("this run is not for a pull request, so there is no "
                      "base branch to compare the baselines with")
    try:
        with open(environ["GITHUB_EVENT_PATH"], encoding="utf-8") as fh:
            sha = json.load(fh)["pull_request"]["base"]["sha"]
    except (KeyError, OSError, ValueError, TypeError) as exc:
        return None, (f"the pull request event names no readable base "
                      f"commit ({type(exc).__name__})")
    if not isinstance(sha, str) or not _SHA_RX.fullmatch(sha):
        return None, "the pull request event's base commit is not a hash"
    return sha, ""


def _git_ok(*args: str) -> bool:
    try:
        return subprocess.run(_git(*args), stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=120,
                              env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
                              ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def base_copy(guard: str, cfg: dict, sha: str, workdir: Path
              ) -> "tuple[str | None, str | None]":
    """(path of the base branch's copy of ``guard``'s baseline, or None;
    a could-not-run sentence, or None). (None, None): no baseline is in use,
    so there is nothing that could have grown."""
    key, default, empty = RATCHETS[guard]
    current = Path(cfg[key] or default)
    if not current.is_file():
        return None, None
    try:
        rel = current.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return None, (f"{guard}: the baseline {current} is outside the "
                      f"checkout, so the base branch has no copy of it to "
                      f"compare with; nothing was compared")
    if not _git_ok("cat-file", "-e", f"{sha}^{{commit}}"):
        _git_ok("fetch", "--no-tags", "--depth=1", "origin", sha)
        if not _git_ok("cat-file", "-e", f"{sha}^{{commit}}"):
            return None, (f"{guard}: the base commit {sha[:12]} is not in this "
                          f"checkout and could not be fetched, so the baseline "
                          f"was not compared with the base branch's copy")
    out = workdir / f"{guard}-base.json"
    if not _git_ok("cat-file", "-e", f"{sha}:{rel}"):
        # The base branch had no baseline: its floor was empty, and every
        # entry this one holds is new.
        out.write_text(empty + "\n", encoding="utf-8")
        return str(out), None
    try:
        blob = subprocess.run(_git("cat-file", "blob", f"{sha}:{rel}"),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, (f"{guard}: reading the base branch's {rel} failed "
                      f"({type(exc).__name__}); nothing was compared")
    if blob.returncode != 0:
        return None, (f"{guard}: git could not read the base branch's {rel} "
                      f"(exit {blob.returncode}); nothing was compared")
    out.write_bytes(blob.stdout)
    return str(out), None


def classify(code: int) -> str:
    """pass | finding | cannot-run | crashed, from the exit code alone.

    Takes no output on purpose: the output quotes the pull request, so a
    verdict read from it is one the pull request can write (R24-1). A crash
    is CRASH_EXIT from the launcher, or any code no guard returns.
    """
    return {0: "pass", 1: "finding", 2: "cannot-run"}.get(code, "crashed")


def _last_sentence(output: str) -> str:
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    return lines[-1] if lines else "(the guard printed nothing)"


def run(cfg: dict, environ: "dict[str, str]") -> int:
    with tempfile.TemporaryDirectory() as workdir:
        return _run(cfg, environ, Path(workdir))


def _run(cfg: dict, environ: "dict[str, str]", workdir: Path) -> int:
    results = []  # (guard, verdict, sentence)
    ratchets = [g for g in cfg["guards"] if g in RATCHETS]
    sha, vs_base_note = None, ""
    if ratchets and cfg["baseline-vs-base"] == "off":
        vs_base_note = "baseline-vs-base is `off`"
    elif ratchets:
        sha, vs_base_note = _base_sha(environ)
    if vs_base_note:
        _say(f"baselines not compared with a base branch: {vs_base_note}")
    for guard, args, pre in plan(cfg):
        if sha and guard in RATCHETS and pre is None:
            copy, why = base_copy(guard, cfg, sha, workdir)
            if why:
                _say(why)
                results.append((f"{guard} baseline vs base", "cannot-run", why))
            elif copy:
                if not cfg[RATCHETS[guard][0]]:
                    args = args + ["--baseline", RATCHETS[guard][1]]
                args = args + ["--base-baseline", copy]
        print(f"::group::sutradhar {guard}", flush=True)
        if pre is not None:
            print(pre, flush=True)
            verdict, sentence, output = "cannot-run", pre, pre
        else:
            script = str(GUARDS_DIR / SCRIPTS[guard])
            cmd = _python("-c", _LAUNCH, script, *args)
            _say("$ " + " ".join([script, *args]))
            proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True)
            # Captured apart, not merged: a guard writes its refusal to
            # stderr at once and its selfcheck line to a buffered stdout, so
            # a merged stream's last line is the selfcheck, and the
            # annotation quoted "selfcheck ok" as the reason a guard could
            # not run. The sentence is stderr's last line when there is one.
            output = proc.stdout + proc.stderr
            # The guard's output quotes the adopter's source (an f-string
            # expression, a path). Stop workflow commands around it, so a
            # line in the code under test cannot speak to the runner.
            token = secrets.token_hex(16)
            print(f"::stop-commands::{token}", flush=True)
            for stream in (proc.stdout, proc.stderr):
                if stream:
                    print(stream, end="" if stream.endswith("\n") else "\n",
                          flush=True)
            print(f"::{token}::", flush=True)
            verdict = classify(proc.returncode)
            sentence = (_last_sentence(proc.stderr) if proc.stderr.strip()
                        else _last_sentence(proc.stdout))
            _say(f"{guard}: exit {proc.returncode} -> {verdict}")
        print("::endgroup::", flush=True)
        results.append((guard, verdict, sentence))

    policy = cfg["policy"]
    lines = []
    for guard, verdict, sentence in results:
        if verdict == "pass":
            continue
        if verdict == "cannot-run" and policy == "skip":
            level, label = "warning", "skipped: could not run"
        elif verdict == "cannot-run":
            level, label = "error", "could not run (on-cannot-run: fail)"
        elif verdict == "crashed":
            level, label = "error", "crashed - the guard failed, not your code"
        else:
            level, label = "error", "finding"
        title = _escape_property(f"sutradhar {guard} - {label}")
        print(f"::{level} title={title}::"
              f"{_escape_data(sentence)}", flush=True)
        lines.append((guard, label, sentence))

    ran = [r for r in results if r[1] in ("pass", "finding")]
    bad = [r for r in results if r[1] in ("finding", "crashed")]
    blocked = [r for r in results if r[1] == "cannot-run"]

    if bad:
        code, headline = 1, f"{len(bad)} guard(s) red"
    elif blocked and policy == "fail":
        code, headline = 2, (f"{len(blocked)} guard(s) could not run, and "
                             f"on-cannot-run is `fail`")
    elif not ran:
        code, headline = 2, ("every selected guard was skipped: nothing was "
                             "checked, and that is not a pass (2.9)")
    else:
        code, headline = 0, (f"{len(ran)} guard(s) passed"
                             + (f", {len(blocked)} skipped (could not run)"
                                if blocked else ""))
    _say(headline)

    summary = environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        rows = ["### Sutradhar guards", "", f"**{headline}**", ""]
        if vs_base_note:
            # This script's own words, never the pull request's.
            rows += [f"Baselines were not compared with a base branch: "
                     f"{vs_base_note}.", ""]
        rows += ["| guard | verdict |", "| --- | --- |"]
        for guard, verdict, sentence in results:
            # The sentence is the guard's last line, which quotes the pull
            # request; it is escaped to inert text. Guard names and verdict
            # words are this script's own.
            label = {"cannot-run": f"could not run - {md_inert(sentence)}",
                     "crashed": f"crashed - {md_inert(sentence)}"}.get(
                         verdict, verdict)
            rows.append(f"| {guard} | {label} |")
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("\n".join(rows) + "\n")
    return code


def selfcheck() -> bool:
    """Each refusal and each verdict word, with a case it must get right."""
    problems = []

    def refused(env: dict) -> bool:
        try:
            read_config(env)
        except Refused:
            return True
        return False

    for bad in ("src; rm -rf /", "$(id)", "a`b`", "src|tee", "--update-baseline",
                "src\nfoo && bar"):
        if not refused({"SUTRADHAR_PATHS": bad}):
            problems.append(f"path {bad!r} was accepted")
    for ok in ("src", "app/core ./lib", "."):
        if refused({"SUTRADHAR_PATHS": ok}):
            problems.append(f"plain path {ok!r} was refused")
    if not refused({"SUTRADHAR_GUARDS": "swallow,framework_shape"}):
        problems.append("framework_shape was accepted as a guard")
    if not refused({"SUTRADHAR_GUARDS": "swalow"}):
        problems.append("a misspelled guard was accepted")
    if not refused({"SUTRADHAR_ON_CANNOT_RUN": "ignore"}):
        problems.append("on-cannot-run accepted a third value")
    if not refused({"SUTRADHAR_BASELINE_VS_BASE": "skip"}):
        problems.append("baseline-vs-base accepted a third value")
    cfg = read_config({})
    if cfg["guards"] != list(DEFAULT_GUARDS) or cfg["policy"] != "fail":
        problems.append(f"defaults drifted: {cfg['guards']} {cfg['policy']}")

    for code, want in ((0, "pass"), (1, "finding"), (2, "cannot-run"),
                       (CRASH_EXIT, "crashed"), (127, "crashed"),
                       (-9, "crashed")):
        got = classify(code)
        if got != want:
            problems.append(f"exit {code} classified {got!r}, not {want!r}")

    # The launcher, in a pair: an exception escaping a guard is a crash, and
    # a guard exiting 1 with a traceback-shaped line it printed is not.
    forged = ("print('Traceback (most recent call last) <img src=x>')\n"
              "raise SystemExit(1)\n")
    with tempfile.TemporaryDirectory() as d:
        for body, want in (("raise KeyError('k')\n", CRASH_EXIT), (forged, 1),
                           (None, CRASH_EXIT)):
            guard = Path(d) / "guard.py"
            if body is None:
                guard = Path(d) / "absent.py"
            else:
                guard.write_text(body)
            proc = subprocess.run(_python("-c", _LAUNCH, str(guard)),
                                  capture_output=True, text=True)
            if proc.returncode != want:
                problems.append(f"launcher gave {guard.name} exit "
                                f"{proc.returncode}, not {want}")

    raw = "x <img src=y> [a](https://e.example) **b** `c` | d ~e~ www.f.example"
    inert = md_inert(raw)
    for live in ("<img", "](", "**", "`c`", " | ", "~e~", "://", "www."):
        if live in inert:
            problems.append(f"md_inert left {live!r} live in {inert!r}")

    for p in problems:
        print(f"[sutradhar-action] SELFCHECK FAILED: {p}")
    if not problems:
        print("[sutradhar-action] selfcheck ok: metacharacter and flag-shaped "
              "paths refused, plain paths accepted, framework-only gates and "
              "unknown guards refused, defaults are the four source/CI guards "
              "with on-cannot-run fail, baseline-vs-base refuses a third "
              "value, an exception escaping a guard reads "
              "as crashed and a traceback-shaped line in its output does "
              "not, summary text escaped inert")
    return not problems


def main(argv: "list | None" = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--selfcheck"]:
        return 0 if selfcheck() else 1
    if argv:
        print(f"[sutradhar-action] takes no arguments (inputs arrive as "
              f"environment variables) or --selfcheck; got {argv}",
              file=sys.stderr)
        return 2
    if sys.version_info < (3, 9):
        print(f"[sutradhar-action] python3 is {sys.version.split()[0]}; the "
              f"guards need 3.9 or newer. Nothing was run.", file=sys.stderr)
        return 2
    try:
        cfg = read_config(dict(os.environ))
    except Refused as exc:
        print(f"::error title=sutradhar - input refused::"
              f"{_escape_data(str(exc))}", flush=True)
        print(f"[sutradhar-action] {exc}", file=sys.stderr)
        return 2
    return run(cfg, dict(os.environ))


if __name__ == "__main__":
    sys.exit(main())
