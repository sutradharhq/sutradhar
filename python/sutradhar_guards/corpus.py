#!/usr/bin/env python3
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Scorer for the defect corpus: does each guard catch what it claims?

A case is a defective/clean twin pair in one markdown manifest. This tool
materializes each twin into a throwaway directory, runs the named guard the
way the guard is really invoked, and scores the verdict:

    CAUGHT          defective twin flagged, clean twin silent
    MISSED          defective twin not flagged
    FALSE_POSITIVE  clean twin flagged (whatever the defective twin did)
    INVALID         could not measure: out-of-partition exit, crash,
                    materialization failure

Exit 0 every `caught` case CAUGHT, zero FALSE_POSITIVE, zero INVALID, and
the case count on disk equal to the declared one.
Exit 1 a finding: a `caught` case MISSED, any FALSE_POSITIVE, an `open`
case that is now CAUGHT (demands a reviewed manifest flip), or a case count
that differs from `case_count.json` in either direction.
Exit 2 could not run: empty corpus, unparseable manifest, unknown guard,
unresolvable scar, or any INVALID case. A run with an unmeasurable case
cannot report a trustworthy total (2.9/6.7). Also exit 2: a full run with
`--require-case-count` over a corpus with no `case_count.json`.

The total is declared, not only counted (R24-2). A denominator read off the
disk shrinks with the disk: deleting a case file used to print "51 of 51"
and exit 0, the R22-1 defect one level down. `case_count.json` at the
corpus root holds `{"cases": N}`, and a full run fails unless exactly N
case files load - fewer (a deleted case) and more (a case added without
moving the number) alike. Symmetric and with no auto-update flag, the
dialect of `uncovered.json` beside it and of framework_shape's baseline: a
number that only moves in a reviewed diff is a floor, one a tool rewrites
is a counter. Without the file the run says the total is not asserted;
`--require-case-count` (this repository's CI) makes that an exit 2, so
deleting the declaration is not a way round it.

A manifest can never name a command. `corpus.py` owns every invocation
shape in a fixed registry; the manifest supplies only a guard NAME, file
paths, and validated enum options. A frontmatter key outside the fixed set
is refused - that is the pin that keeps a manifest from becoming a script.

Library-only guards run in a subprocess too, through a generated runner
script that imports the guard file by path and exits 1/0. No `python -c`,
no in-process import: this module is copy-in and may not import its
siblings, and a subprocess boundary is what turns a crashing guard into
an INVALID verdict instead of killing the run (6.11) - and it is the real
seam (2.3). A runner that raises exits 3, which is outside every guard's
partition and therefore INVALID, never a catch.

Usage:
    python corpus.py corpus/ --rounds docs/rounds/ --backflow docs/backflow.md
    python corpus.py corpus/ --require-case-count
    python corpus.py corpus/ --case swallow-outage-as-data
    python corpus.py corpus/ --sweep swallow_lint
    python corpus.py corpus/ --sweep-all
    python corpus.py --selfcheck

`--sweep-all` is `--sweep` for every guard in the registry, in one run
(R25-4): CI scored each case against its own guard and never swept, so a
guard flagging another case's clean twin stayed invisible until somebody
ran `--sweep` by hand - detectors flagged the byte-order-mark case's clean
twin for a release that way. Every guard must measure at least one twin; a
registry guard no clean twin exercises has not been swept.

Exit 0 clean, 1 a finding, 2 the check could not run: an unknown flag, an
empty corpus, a manifest that cannot be read exactly, or any INVALID case.
2 is not a pass.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

GUARD_HOME = Path(__file__).resolve().parent

#: One twin run gets two minutes. A guard that cannot answer about a
#: ten-line twin in that time is hung, and a hung run must be INVALID,
#: never a verdict on the case.
_TWIN_TIMEOUT_S = 120

#: Sentinels outside every guard's exit partition. A run that timed out or
#: could not start is unmeasurable, and these codes keep it reading that way.
_RC_TIMEOUT = 124
_RC_SPAWN_FAILED = 125


class CorpusError(Exception):
    """The corpus could not be read exactly. Never a verdict on a case."""


class CoverageError(Exception):
    """The per-rule coverage floor does not hold. A finding, not a crash."""


# ── cases ────────────────────────────────────────────────────────────────────

VALID_EXPECTED = ("caught", "open")
VALID_FIXTURES = ("two_commit",)
FRONTMATTER_KEYS = frozenset({
    "case", "guard", "rule", "scar", "scar_argument",
    "expected", "fixture", "options",
})

#: Helper files a twin may carry beside its scanned bodies. They are data
#: for the adapter, never input to a guard: every adapter contract names
#: which helpers it reads, and CLI guards never see them (`.json` is not a
#: scanned suffix for any lint-shaped guard in the registry).
HELPER_SUFFIX = ".json"


@dataclass(frozen=True)
class Fence:
    path: str
    lang: str
    body: str


@dataclass(frozen=True)
class Case:
    id: str
    guard: str
    rule: str
    scars: tuple
    distribution: bool
    expected: str
    fixture: str | None
    options: tuple
    defective: tuple
    clean: tuple
    helpers: tuple
    source: str


def _parse_frontmatter(text: str, source: str) -> dict:
    """Flat `key: value` scalars between leading `---` fences.

    Refuses what it cannot read exactly: no lists, no nesting, no duplicate
    keys. Local mini-parser, deliberately not shared: copy-in modules may
    not import each other, and each module owns the shape it refuses.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise CorpusError(
            f"{source}: no frontmatter fence - a case starts with `---`, "
            f"flat `key: value` scalars, then a closing `---`"
        )
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise CorpusError(f"{source}: frontmatter opened but never closed")
    out: dict[str, str] = {}
    for lineno, raw in enumerate(lines[1:end], start=2):
        line = raw.split("#", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line.strip())
        if not match:
            raise CorpusError(
                f"{source}: line {lineno} is not a flat `key: value` scalar: "
                f"{line.strip()!r}"
            )
        key, value = match.group(1), match.group(2).strip().strip('"').strip("'")
        if key in out:
            raise CorpusError(f"{source}: line {lineno}: {key!r} declared twice")
        out[key] = value
    return out, end


def _split_sections(text: str, source: str) -> tuple[dict[str, str], list[str]]:
    """({twin-name: section text}, helper fence texts).

    Twin sections are exactly `## defective` and `## clean`. Fenced blocks
    anywhere else - before the first twin, between twins, after the last -
    are helpers (witnessed sets, gate lists, route tables): data for the
    adapter, reviewed in the same file. Fences inside twin sections are
    never misread as helpers, and headings inside fences never split. An
    unclosed helper fence is refused, not silently dropped.
    """
    sections: dict[str, list[str]] = {}
    helpers: list[str] = []
    current: str | None = None
    in_fence = False
    buf: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.strip() in ("## defective", "## clean"):
            if buf is not None:
                raise CorpusError(
                    f"{source}: a helper fence opened before "
                    f"{line.strip()!r} never closes"
                )
            current = line.strip()[3:]
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
            continue
        if line.startswith("```"):
            if buf is None:
                buf = [line]
            else:
                buf.append(line)
                helpers.append("\n".join(buf))
                buf = None
        elif buf is not None:
            buf.append(line)
    if buf is not None:
        raise CorpusError(
            f"{source}: a helper fence at the end of the file never closes"
        )
    return ({k: "\n".join(v) for k, v in sections.items()}, helpers)


_FENCE_RE = re.compile(r"```(\w*)\s*(.*)$")


def _parse_fences(section: str, source: str, twin: str) -> tuple[Fence, ...]:
    """Every fenced block in a twin section. Each carries `path=` - the file
    it materializes to. A block with no path is refused: two blocks with no
    path would collide silently, and a default nobody named is a default
    nobody reviewed."""
    fences: list[Fence] = []
    lines = section.splitlines()
    i = 0
    while i < len(lines):
        match = _FENCE_RE.match(lines[i])
        if not match:
            i += 1
            continue
        lang, info = match.group(1), match.group(2)
        path = None
        for token in info.split():
            if token.startswith("path="):
                path = token[len("path="):]
        if not path:
            raise CorpusError(
                f"{source}: {twin} twin has a fenced block with no `path=` - "
                f"every block declares the file it materializes to"
            )
        body_lines: list[str] = []
        i += 1
        while i < len(lines) and not lines[i].startswith("```"):
            body_lines.append(lines[i])
            i += 1
        if i >= len(lines):
            raise CorpusError(
                f"{source}: {twin} twin has a fenced block that never closes"
            )
        i += 1
        fences.append(Fence(path=path, lang=lang, body="\n".join(body_lines) + "\n"))
    if not fences:
        raise CorpusError(
            f"{source}: {twin} twin has no fenced code block - a twin with "
            f"nothing to materialize cannot be measured"
        )
    return tuple(fences)


def _check_path(path: str, source: str) -> None:
    """A materialization path that escapes its directory is a refusal, not
    a verdict: writing outside the throwaway dir would touch the real tree."""
    pure = Path(path)
    if pure.is_absolute() or ".." in pure.parts:
        raise CorpusError(
            f"{source}: path {path!r} escapes the case directory - "
            f"materialization paths stay inside the throwaway dir"
        )


_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*$")
_RULE_RE = re.compile(r"\d+\.\d+$")
_SCAR_RE = re.compile(r"(?:R\d+-\d+|B-\d+)$")


def parse_case(text: str, source: str, name: str,
               known_rules: set | None = None,
               known_scars: set | None = None) -> Case:
    """Parse one manifest, refusing what it cannot read exactly.

    `known_rules` / `known_scars` of None skip that validation (the
    selfcheck proves the machinery on synthetic cases that cite no real
    archive; every real run passes the archive). An empty set validates
    strictly - nothing resolves against nothing.
    """
    if not _ID_RE.match(name):
        raise CorpusError(
            f"{source}: case id {name!r} is not [a-z0-9-] - the id is the "
            f"filename stem and `--case` matches it exactly"
        )
    front, end = _parse_frontmatter(text, source)
    unknown = set(front) - FRONTMATTER_KEYS
    if unknown:
        raise CorpusError(
            f"{source}: unknown frontmatter key(s) {sorted(unknown)} - a "
            f"manifest supplies a guard name, file paths, and validated "
            f"enum options, never a command"
        )
    for key in ("case", "guard", "rule", "scar", "expected"):
        if key not in front or not front[key]:
            raise CorpusError(f"{source}: frontmatter needs `{key}:`")
    if front["case"] != name:
        raise CorpusError(
            f"{source}: `case: {front['case']}` does not match the filename "
            f"stem {name!r} - the id is the file"
        )
    guard = front["guard"]
    if guard not in GUARDS:
        raise CorpusError(
            f"{source}: unknown guard {guard!r} - the registry in corpus.py "
            f"owns every invocation shape; known: {sorted(GUARDS)}"
        )
    spec = GUARDS[guard]
    rule = front["rule"]
    if rule != "-" and not _RULE_RE.match(rule):
        raise CorpusError(
            f"{source}: `rule: {rule}` is neither a doctrine id nor `-` "
            f"(repo-specific promise, contributing to no rule's coverage)"
        )
    if known_rules is not None and rule != "-" and rule not in known_rules:
        raise CorpusError(
            f"{source}: rule {rule} is in no doctrine file given - a "
            f"mistyped rule id silently loses the attribution 8.1 depends on"
        )
    expected = front["expected"]
    if expected not in VALID_EXPECTED:
        raise CorpusError(
            f"{source}: `expected: {expected}` - only `caught` (a guard must "
            f"flag this) or `open` (no guard does yet)"
        )
    fixture = front.get("fixture") or None
    if fixture is not None and fixture not in VALID_FIXTURES:
        raise CorpusError(
            f"{source}: `fixture: {fixture}` - only `two_commit` (a case "
            f"needing real git history) exists"
        )
    if spec.two_commit and fixture != "two_commit":
        raise CorpusError(
            f"{source}: guard {guard} needs real git history - this case "
            f"must carry `fixture: two_commit`"
        )
    if not spec.two_commit and fixture is not None:
        raise CorpusError(
            f"{source}: guard {guard} scores plain twins - `fixture:` is "
            f"only for guards that need git history"
        )
    options: tuple = ()
    if front.get("options"):
        options = tuple(o.strip() for o in front["options"].split(",") if o.strip())
        bad = [o for o in options if o not in spec.options]
        if bad:
            raise CorpusError(
                f"{source}: option(s) {bad} are not valid for guard {guard} "
                f"(valid: {sorted(spec.options) or 'none'})"
            )
    scar_raw = front["scar"]
    distribution = scar_raw == "distribution"
    scars: tuple = ()
    if distribution:
        if not front.get("scar_argument", "").strip():
            raise CorpusError(
                f"{source}: `scar: distribution` needs `scar_argument:` in "
                f"one sentence - a mechanism entering on argument alone and "
                f"never saying so is not legitimate"
            )
    else:
        scars = tuple(s.strip() for s in scar_raw.split(",") if s.strip())
        if not scars or any(not _SCAR_RE.match(s) for s in scars):
            raise CorpusError(
                f"{source}: `scar: {scar_raw}` - comma-separated R<n>-<m> / "
                f"B-<n> ids that resolve, or the literal `distribution`"
            )
        if known_scars is not None:
            missing = [s for s in scars if s not in known_scars]
            if missing:
                raise CorpusError(
                    f"{source}: scar(s) {missing} resolve against no round "
                    f"record or backflow row given - an uncited case is refused"
                )
    body = "\n".join(text.splitlines()[end + 1:])
    sections, helper_raw = _split_sections(body, source)
    if "defective" not in sections or "clean" not in sections:
        raise CorpusError(
            f"{source}: a case has exactly `## defective` and `## clean` "
            f"sections - found: {sorted(sections) or 'none'}"
        )
    defective = _parse_fences(sections["defective"], source, "defective")
    clean = _parse_fences(sections["clean"], source, "clean")
    helpers = tuple(
        Fence(path=_fence_path(h, source), lang="", body=_fence_body(h))
        for h in helper_raw
    )
    for fence in defective + clean + helpers:
        _check_path(fence.path, source)
    for twin, fences in (("defective", defective), ("clean", clean)):
        paths = [f.path for f in fences]
        if len(set(paths)) != len(paths):
            raise CorpusError(
                f"{source}: {twin} twin declares a path twice - twins "
                f"materialize to files, and two bodies cannot share one"
            )
    return Case(
        id=name, guard=guard, rule=rule, scars=scars,
        distribution=distribution, expected=expected, fixture=fixture,
        options=options, defective=defective, clean=clean,
        helpers=helpers, source=source,
    )


def _fence_path(raw: str, source: str) -> str:
    first = raw.splitlines()[0]
    match = _FENCE_RE.match(first)
    info = match.group(2) if match else ""
    for token in info.split():
        if token.startswith("path="):
            return token[len("path="):]
    raise CorpusError(
        f"{source}: a helper fence has no `path=` - helpers are files too"
    )


def _fence_body(raw: str) -> str:
    lines = raw.splitlines()[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines) + "\n"


def load_cases(root: Path, known_rules: set | None = None,
               known_scars: set | None = None) -> list[Case]:
    """Every `cases/*.md` under root, sorted. Refuses the first manifest it
    cannot read exactly - a half-loaded corpus would score a subset and
    report a total over all of it."""
    cases_dir = root / "cases"
    if not cases_dir.is_dir():
        raise CorpusError(
            f"no cases directory at {cases_dir} - a corpus with no cases "
            f"has nothing to score"
        )
    files = sorted(cases_dir.glob("*.md"))
    if not files:
        raise CorpusError(
            f"no case files under {cases_dir} - an empty corpus cannot "
            f"report a total"
        )
    cases = [parse_case(p.read_text(encoding="utf-8"), str(p), p.stem,
                        known_rules, known_scars) for p in files]
    ids = [c.id for c in cases]
    if len(set(ids)) != len(ids):
        raise CorpusError("duplicate case ids - the id is the file, so this "
                          "means two files share a stem across suffixes")
    return cases


def materialize(case: Case, dest: Path, twin: str) -> Path:
    """Write one twin plus helpers into dest. Returns dest. Refuses paths
    that escape (checked at load; re-checked here because the check that
    matters is the one at the write)."""
    fences = case.defective if twin == "defective" else case.clean
    for fence in fences + case.helpers:
        target = dest / fence.path
        try:
            resolved = target.resolve()
            dest_resolved = dest.resolve()
        except OSError as exc:
            raise CorpusError(
                f"{case.source}: cannot resolve {fence.path}: {exc}"
            )
        if resolved != dest_resolved and dest_resolved not in resolved.parents:
            raise CorpusError(
                f"{case.source}: {fence.path!r} escapes the case directory"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(fence.body, encoding="utf-8")
    return dest


# ── the registry: every invocation shape, owned here ─────────────────────────
#
# A manifest names a guard; it never names a command, a module path, or an
# argument. Each entry fixes the argv (CLI guards) or the runner source
# (library guards), the exit partition, the valid options enum, and whether
# the case must carry `fixture: two_commit`. An option the registry does
# not list is refused at load, which is what keeps a manifest from smuggling
# behavior past review in a string the runner would honor.

@dataclass(frozen=True)
class _Spec:
    module: str
    kind: str  # "cli" | "runner"
    build: object  # cli: (tmp, options) -> argv
    # runner: (tmp, guard_home, options, fixture) -> script source.
    # The fixture tells the adapter whether this twin is its case: a
    # two-commit twin under any other guard would read as a finding
    # (any script that exits 0 "verifies" vacuously), so the verify
    # adapter refuses non-fixture twins instead of scoring them.
    catch_codes: tuple
    clean_codes: tuple
    options: frozenset = frozenset()
    two_commit: bool = False


def _py(module: str) -> list[str]:
    return [sys.executable, str(GUARD_HOME / f"{module}.py")]


def _argv_swallow(tmp: Path, options: tuple) -> list[str]:
    # No --baseline: a missing baseline file reads as an empty floor, so any
    # swallow is new (exit 1) and a clean twin is silent (exit 0).
    return _py("swallow_lint") + [str(tmp)]


def _argv_conflated(tmp: Path, options: tuple) -> list[str]:
    # Same ratchet shape as swallow_lint: the default baseline beside the
    # scanned tree is absent in a throwaway dir, which reads as an empty
    # floor - any conflation is new (exit 1).
    return _py("conflated_degrade_lint") + [str(tmp)]


def _argv_interpolation(tmp: Path, options: tuple) -> list[str]:
    argv = _py("interpolation_lint") + [str(tmp), "--keywords", "sql"]
    if "strict" in options:
        argv.append("--strict")
    return argv


def _argv_budget(tmp: Path, options: tuple) -> list[str]:
    # The whole throwaway dir is both the design root and the test root: a
    # declared budget no test file mentions is exit 1, a mentioned one is 0.
    # The note's own frontmatter id is unquoted, so it cannot self-enforce -
    # the clean twin must quote the id in a test file, visibly.
    return _py("budget") + [str(tmp), "--tests", str(tmp)]


def _argv_obsgate(tmp: Path, options: tuple) -> list[str]:
    return _py("obsgate") + ["check", "--metrics", str(tmp / "metrics.txt"),
                             "--floor", str(tmp / "floor.json")]


def _argv_rounds(tmp: Path, options: tuple) -> list[str]:
    argv = _py("rounds") + [str(tmp / "rounds"), "--check"]
    if "designs" in options:
        argv += ["--designs", str(tmp / "design")]
    if "backflow" in options:
        argv += ["--backflow", str(tmp / "backflow.md")]
    return argv


def _argv_framework_shape(tmp: Path, options: tuple) -> list[str]:
    # Twins live under docs/ - the one surface dir a throwaway tree can
    # honestly populate. The baseline beside the tree is absent, which reads
    # as an empty floor: any domain literal is new (exit 1).
    return _py("framework_shape") + [str(tmp)]


def _argv_framework_only(tmp: Path, options: tuple) -> list[str]:
    # Twins live under guards/; the surface holds nothing else, so a
    # non-stdlib import is the only thing that can fail.
    return _py("framework_only") + [str(tmp), "--guards", "guards"]


def _argv_ci_step(tmp: Path, options: tuple) -> list[str]:
    return _py("ci_step_lint") + [str(tmp / "workflows")]


_RUNNER_HEAD = """\
import importlib.util
import json
import os
import sys

_GUARD = {guard_file}
_TMP = {tmp_dir}
_OPTIONS = {options_json}

def _load():
    spec = importlib.util.spec_from_file_location("corpus_guard", _GUARD)
    mod = importlib.util.module_from_spec(spec)
    # Registered before exec: dataclasses resolves string annotations
    # through the module namespace, and an unregistered module has none.
    sys.modules["corpus_guard"] = mod
    spec.loader.exec_module(mod)
    return mod

def _body(mod):
{{BODY}}

try:
    _guard = _load()
    _flagged = bool(_body(_guard))
except Exception as exc:
    print("adapter crashed: {{}}: {{}}".format(type(exc).__name__, exc))
    raise SystemExit(3)

raise SystemExit(1 if _flagged else 0)
"""


def _runner(source_body: str, tmp: Path, guard_home: Path, module: str,
            options: tuple, fixture: str | None) -> str:
    guard_file = json.dumps(str(guard_home / f"{module}.py"))
    head = _RUNNER_HEAD.format(guard_file=guard_file,
                               tmp_dir=json.dumps(str(tmp)),
                               options_json=json.dumps(sorted(options)))
    indented = "\n".join(("    " + line) if line.strip() else line
                         for line in source_body.splitlines())
    return head.replace("{BODY}", indented)


def _run_detectors(tmp: Path, guard_home: Path, options: tuple,
                   fixture: str | None) -> str:
    return _runner("""\
import pathlib
hits = []
for path in sorted(pathlib.Path(_TMP).rglob("*.py")):
    src = path.read_text(encoding="utf-8-sig", errors="replace")
    hits += _guard.find_order_by_without_limit(src, path=str(path))
hits += _guard.find_unresolved_relative_imports(_TMP)
hits += _guard.find_test_only_helpers(_TMP)
print("detectors: {} violation(s)".format(len(hits)))
for hit in hits[:10]:
    print("  {}".format(hit.message if hasattr(hit, "message") else hit))
return bool(hits)
""", tmp, guard_home, "detectors", options, fixture)


def _run_claim_check(tmp: Path, guard_home: Path, options: tuple,
                     fixture: str | None) -> str:
    return _runner("""\
import pathlib
texts = []
for path in sorted(pathlib.Path(_TMP).rglob("*")):
    if path.is_file() and path.suffix != ".json":
        texts.append(path.read_text(encoding="utf-8", errors="replace"))
wit_path = pathlib.Path(_TMP) / "witnessed.json"
if not wit_path.is_file():
    print("claim_check adapter: no witnessed.json helper - the witnessed "
          "set is manifest data, and a case without one cannot be measured")
    raise SystemExit(3)
witnessed = json.loads(wit_path.read_text(encoding="utf-8"))
ungrounded = _guard.ground_claims("\\n".join(texts), witnessed)
print("claim_check: {} ungrounded claim(s)".format(len(ungrounded)))
return bool(ungrounded)
""", tmp, guard_home, "claim_check", options, fixture)


def _run_envgate(tmp: Path, guard_home: Path, options: tuple,
                 fixture: str | None) -> str:
    return _runner("""\
import pathlib
gates_path = pathlib.Path(_TMP) / "gates.json"
if not gates_path.is_file():
    print("envgate adapter: no gates.json helper - gates are manifest "
          "data, and a case without them cannot be measured")
    raise SystemExit(3)
gates = [_guard.EnvGate(**g)
         for g in json.loads(gates_path.read_text(encoding="utf-8"))]
missing = _guard.audit_skip_gates(
    gates, [".github/workflows/*.yml"], root=_TMP)
print("envgate: {} gate(s) set by nothing: {}".format(len(missing), missing))
return bool(missing)
""", tmp, guard_home, "envgate", options, fixture)


def _run_golden(tmp: Path, guard_home: Path, options: tuple,
                   fixture: str | None) -> str:
    return _runner("""\
import pathlib
# options=rebaseline replays an intentional re-baseline: the UPDATE mode
# is on, and the reason comes from the manifest (reason.txt) or from
# nowhere - an unreasoned re-baseline is how a golden file stops meaning
# anything, and the gate refuses it. Without the option both variables
# are scrubbed so ambient CI config cannot flip a case.
for key in ("GOLDEN_UPDATE", "GOLDEN_REASON"):
    os.environ.pop(key, None)
if "rebaseline" in _OPTIONS:
    os.environ["GOLDEN_UPDATE"] = "1"
    reason_path = pathlib.Path(_TMP) / "reason.txt"
    if reason_path.is_file():
        os.environ["GOLDEN_REASON"] = reason_path.read_text(
            encoding="utf-8").strip()
data_path = pathlib.Path(_TMP) / "data.json"
golden_path = pathlib.Path(_TMP) / "golden.json"
if not data_path.is_file() or not golden_path.is_file():
    print("golden adapter: need data.json (the twin) and golden.json "
          "(the frozen baseline) - a case missing either cannot be measured")
    raise SystemExit(3)
computed = json.loads(data_path.read_text(encoding="utf-8"))
try:
    _guard.GoldenGate(golden_path).check(computed)
except _guard.GoldenError as exc:
    print(str(exc))
    return True
print("golden: computed data within the frozen tolerance")
return False
""", tmp, guard_home, "golden", options, fixture)


def _run_dead_route(tmp: Path, guard_home: Path, options: tuple,
                    fixture: str | None) -> str:
    return _runner("""\
import pathlib
routes_path = pathlib.Path(_TMP) / "routes.json"
if not routes_path.is_file():
    print("dead_route adapter: no routes.json helper - the route table is "
          "manifest data, and a case without one cannot be measured")
    raise SystemExit(3)
routes = set(json.loads(routes_path.read_text(encoding="utf-8"))["routes"])
dead = _guard.find_dead_routes(_TMP, routes)
weak = _guard.find_unfailable_assertions(_TMP)
print("dead_route: {} dead route(s), {} unfailable assertion(s)".format(
    len(dead), len(weak)))
return bool(dead or weak)
""", tmp, guard_home, "dead_route_lint", options, fixture)


def _run_verify(tmp: Path, guard_home: Path, options: tuple,
                   fixture: str | None) -> str:
    if fixture != "two_commit":
        raise CorpusError(
            "verify_guard scores two-commit fixtures only - a plain "
            "twin is not its case")
    return _runner("""\
import pathlib
import shlex
import shutil
import subprocess
if shutil.which("git") is None:
    print("verify adapter: git is not on PATH - a two-commit fixture "
          "cannot be built, and the case cannot be measured")
    raise SystemExit(3)
twins = sorted(pathlib.Path(_TMP).rglob("*.py"))
if len(twins) != 1:
    print("verify adapter: a two-commit twin is exactly one guard file, "
          "found {}".format(len(twins)))
    raise SystemExit(3)
guard_rel = twins[0].relative_to(pathlib.Path(_TMP)).as_posix()

# The guard's own scrubbed env: a sweep run from a git hook inherits its
# GIT_DIR, and `cwd=_TMP` does not override it - the fixture would be built
# in the hook's repository instead.
def git(*args):
    subprocess.run(
        ["git", "-c", "user.name=sutradhar-corpus",
         "-c", "user.email=corpus@sutradhar.invalid",
         "-c", "commit.gpgsign=false", *args],
        cwd=_TMP, capture_output=True, text=True, check=True,
        env=_guard.git_env())

(root := pathlib.Path(_TMP)).joinpath("calc.py").write_text(_guard.FIXTURE_BUG)
git("init", "-q")
git("add", "calc.py")
git("commit", "-q", "-m", "buggy parent")
(root / "calc.py").write_text(_guard.FIXTURE_FIX)
git("add", "calc.py", guard_rel)
git("commit", "-q", "-m", "fix with a guard in the same commit")
cmd = shlex.join([sys.executable, guard_rel])
res = _guard.verify(pathlib.Path(_TMP), "HEAD", guard_cmd=cmd)
print("verify: {} ({})".format(res.verdict, res.reason))
raise SystemExit(res.exit_code)
""", tmp, guard_home, "verify_guard", options, fixture)


GUARDS: dict[str, _Spec] = {
    "swallow_lint": _Spec("swallow_lint", "cli", _argv_swallow, (1,), (0,)),
    "conflated_degrade_lint": _Spec("conflated_degrade_lint", "cli",
                                    _argv_conflated, (1,), (0,)),
    "interpolation_lint": _Spec("interpolation_lint", "cli",
                                _argv_interpolation, (1,), (0,),
                                frozenset({"strict"})),
    "detectors": _Spec("detectors", "runner", _run_detectors, (1,), (0,)),
    "claim_check": _Spec("claim_check", "runner", _run_claim_check, (1,), (0,)),
    "envgate": _Spec("envgate", "runner", _run_envgate, (1,), (0,)),
    "golden": _Spec("golden", "runner", _run_golden, (1,), (0,),
                    frozenset({"rebaseline"})),
    "budget": _Spec("budget", "cli", _argv_budget, (1,), (0,)),
    "obsgate": _Spec("obsgate", "cli", _argv_obsgate, (1,), (0,)),
    "rounds": _Spec("rounds", "cli", _argv_rounds, (1,), (0,),
                    frozenset({"designs", "backflow"})),
    "framework_shape": _Spec("framework_shape", "cli", _argv_framework_shape,
                             (1,), (0,)),
    "framework_only": _Spec("framework_only", "cli", _argv_framework_only,
                            (1,), (0,)),
    "dead_route_lint": _Spec("dead_route_lint", "runner", _run_dead_route,
                             (1,), (0,)),
    "verify_guard": _Spec("verify_guard", "runner", _run_verify, (1,), (0,),
                          frozenset(), True),
    "ci_step_lint": _Spec("ci_step_lint", "cli", _argv_ci_step, (1,), (0,)),
}


def run_twin(spec: _Spec, tmp: Path, options: tuple,
             fixture: str | None = None,
             timeout: int = _TWIN_TIMEOUT_S) -> int:
    """Run one twin, returning the guard's exit code.

    A timeout is 124, a spawn failure 125 - both outside every partition,
    so an unmeasurable run reads INVALID, never a catch and never a pass.
    """
    if spec.kind == "cli":
        argv = spec.build(tmp, options)
        cwd = tmp
    else:
        try:
            script = spec.build(tmp, GUARD_HOME, options, fixture)
        except CorpusError as exc:
            # Not this adapter's case (a verify twin without a fixture can
            # only arrive via --sweep, which loads no fixture): exit 3 reads
            # INVALID in scoring and silent in a sweep, both honestly.
            print(f"[corpus] twin refused: {exc}")
            return 3
        runner_dir = tmp.parent / "runner"
        runner_dir.mkdir(parents=True, exist_ok=True)
        script_path = runner_dir / f"run_{spec.module}.py"
        script_path.write_text(script, encoding="utf-8")
        argv = [sys.executable, str(script_path)]
        cwd = tmp
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _RC_TIMEOUT
    except OSError:
        return _RC_SPAWN_FAILED
    return proc.returncode


# ── scoring ──────────────────────────────────────────────────────────────────

CAUGHT, MISSED, FALSE_POSITIVE, INVALID = (
    "CAUGHT", "MISSED", "FALSE_POSITIVE", "INVALID")


def score(case: Case, defective_rc: int, clean_rc: int, spec: _Spec) -> str:
    """The verdict from the two exit codes. Order matters, and the order is
    the doctrine: a flagged clean twin is a finding of a different kind
    (FALSE_POSITIVE takes precedence over whatever the defective twin did),
    and an unmeasurable side is INVALID even when the other side caught -
    a verdict needs both twins to have answered."""
    if clean_rc in spec.catch_codes:
        return FALSE_POSITIVE
    if clean_rc not in spec.clean_codes:
        return INVALID
    if defective_rc in spec.catch_codes:
        return CAUGHT
    if defective_rc in spec.clean_codes:
        return MISSED
    return INVALID


# ── archive inputs: doctrine rules, scars, coverage ──────────────────────────
#
# Reimplemented shallowly on purpose. rounds.py owns the semantic
# validation; this module needs presence ("does any round record contain
# this id") so a mistyped scar fails here instead of passing silently. The
# shapes mirror rounds.py (`**2.7 ` rule lines, `R<n>-<m>` finding cells,
# `B-<n>` register ids) so the two readers cannot drift apart unnoticed.

_DOCTRINE_RULE_RE = re.compile(r"^\*\*(\d+\.\d+)\s", re.MULTILINE)
_FINDING_ID_RE = re.compile(r"\bR\d+-\d+\b")
_BACKFLOW_ID_RE = re.compile(r"\bB-\d+\b")


def doctrine_rule_ids(doctrine: Path) -> set[str]:
    return set(_DOCTRINE_RULE_RE.findall(
        doctrine.read_text(encoding="utf-8", errors="replace")))


def known_scars(rounds_dir: Path | None,
               backflow_path: Path | None) -> set[str]:
    """Every finding id any round record contains, plus every backflow id."""
    found: set[str] = set()
    if rounds_dir is not None and rounds_dir.is_dir():
        for path in sorted(rounds_dir.glob("*.md")):
            found |= set(_FINDING_ID_RE.findall(
                path.read_text(encoding="utf-8", errors="replace")))
    if backflow_path is not None and backflow_path.is_file():
        found |= set(_BACKFLOW_ID_RE.findall(
            backflow_path.read_text(encoding="utf-8", errors="replace")))
    return found


def parse_exclusions(path: Path) -> dict[str, str]:
    """`EXCLUSIONS.md`: lines `- <rule>: <one-line reason>`, prose ignored.

    An exclusion without a reason is refused - a banked row that cannot say
    why is an ignore-list row (the framework_shape baseline rule).
    """
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1):
        match = re.match(r"-\s*(\d+\.\d+)\s*:\s*(.+)$", line.strip())
        if not match:
            continue
        rule, reason = match.group(1), match.group(2).strip()
        if not reason:
            raise CorpusError(
                f"{path}:{lineno}: exclusion of rule {rule} carries no "
                f"reason - write the sentence or delete the row"
            )
        out[rule] = reason
    return out


def load_floor(path: Path) -> dict[str, str]:
    """`uncovered.json`: `{rule: why-not-yet}`. The framework_shape baseline
    dialect, symmetric and with no auto-update flag: banking is an act of
    writing a sentence, and removing a banked entry is too."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CorpusError(
            f"cannot read the uncovered floor {path}: "
            f"{type(exc).__name__}: {exc}"
        )
    if not isinstance(data, dict):
        raise CorpusError(
            f"the uncovered floor {path} is a {type(data).__name__}, not an "
            f"object of rule -> reason"
        )
    bad = [k for k, v in data.items()
           if not isinstance(v, str) or not v.strip()]
    if bad:
        raise CorpusError(
            f"uncovered floor entr(ies) carry no reason: "
            f"{', '.join(sorted(bad)[:6])}"
        )
    return data


CASE_COUNT_FILE = "case_count.json"


def load_case_count(path: Path) -> int | None:
    """`case_count.json`: `{"cases": N}`, N a positive integer and the only
    key. None when the file is absent - the caller decides whether absence
    is allowed; a file that is present and unreadable is never read as
    absent (2.7: that would turn a broken floor into no floor)."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CorpusError(
            f"cannot read the declared case count {path}: "
            f"{type(exc).__name__}: {exc}"
        )
    n = data.get("cases") if isinstance(data, dict) else None
    if (not isinstance(data, dict) or set(data) != {"cases"}
            or isinstance(n, bool) or not isinstance(n, int) or n < 1):
        raise CorpusError(
            f"the declared case count {path} is {data!r}; it is exactly "
            f'{{"cases": N}} with N a positive integer'
        )
    return n


def case_count_problem(on_disk: int, declared: int, path: Path) -> str | None:
    """The sentence for a count that does not hold, or None. Both directions
    fail: fewer is a deleted case; more is a floor left stale beneath new
    cases, which would let the next deletion pass unseen."""
    if on_disk < declared:
        return (f"{on_disk} case file(s) on disk, {declared} declared in "
                f"{path}: {declared - on_disk} short. Restore the case, or "
                f"lower `cases` in the same reviewed diff that deletes it.")
    if on_disk > declared:
        return (f"{on_disk} case file(s) on disk, {declared} declared in "
                f"{path}: {on_disk - declared} over. Raise `cases` in the "
                f"diff that adds the case(s), so the floor stands under them.")
    return None


def coverage(cases: list[Case], rule_ids: set[str], exclusions: dict[str, str],
             floor: dict[str, str]) -> dict:
    """Partition every doctrine rule into covered / excluded / uncovered.

    Only `expected: caught` cases cover: an open case names a gap no guard
    holds yet, and counting it as covered would read the gap as closed.
    Raises CoverageError when a rule is uncovered but absent from the floor
    (write the sentence or write the case), when a floor entry now has a
    case or an exclusion (remove it so the floor drops), when an exclusion
    names a rule with a case (remove it - the rule is held), or when either
    file names a rule the doctrine does not have (a stale row that can no
    longer mean what it says). Cases citing `-` guard repo-specific
    promises and contribute to no rule's coverage.
    """
    cited = {c.rule for c in cases if c.rule != "-"}
    unknown = cited - rule_ids
    if unknown:
        raise CoverageError(
            f"case(s) cite rule(s) not in the doctrine: {sorted(unknown)}"
        )
    unknown_excluded = sorted(r for r in exclusions if r not in rule_ids)
    if unknown_excluded:
        raise CoverageError(
            f"exclusion(s) name rule(s) not in the doctrine: "
            f"{', '.join(unknown_excluded)}"
        )
    unknown_banked = sorted(r for r in floor if r not in rule_ids)
    if unknown_banked:
        raise CoverageError(
            f"floor entr(ies) name rule(s) not in the doctrine: "
            f"{', '.join(unknown_banked)}"
        )
    covered = {c.rule for c in cases
               if c.rule != "-" and c.expected == "caught"}
    excluded = {r for r in exclusions if r in rule_ids}
    held_but_excluded = sorted(r for r in excluded if r in covered)
    if held_but_excluded:
        raise CoverageError(
            f"excluded rule(s) now have a case holding them: "
            f"{', '.join(held_but_excluded)}. Remove the exclusion - an "
            f"exclusion for a covered rule hides the coverage."
        )
    uncovered = set(rule_ids) - covered - excluded
    missing = sorted(r for r in uncovered if r not in floor)
    if missing:
        raise CoverageError(
            f"{len(missing)} rule(s) have no case and no banked reason: "
            f"{', '.join(missing)}. Write a case, exclude with a reason in "
            f"EXCLUSIONS.md, or bank the reason in uncovered.json - an "
            f"uncovered rule with no sentence is a decision nobody made."
        )
    stale = sorted(r for r in floor if r in covered or r in excluded)
    if stale:
        raise CoverageError(
            f"floor entr(ies) no longer uncovered: {', '.join(stale)}. "
            f"Remove them so the floor drops - a ratchet is not an ignore-list."
        )
    return {"covered": sorted(covered), "excluded": sorted(excluded),
            "uncovered": sorted(uncovered)}


# ── report ───────────────────────────────────────────────────────────────────

def report(results: list[tuple[Case, str]], cov: dict | None) -> str:
    """Human report. The denominator is the manifest set: `<caught> of
    <expected-caught>` counts cases discovered on disk, never a loop
    counter (R22-1). The open-case count prints on every run, so "all
    green" can never read as "nothing left to do" (D6)."""
    lines = []
    for case, verdict in results:
        lines.append(f"[corpus] {verdict} {case.id} "
                     f"({case.guard}, rule {case.rule})")
    caught_cases = [c for c, v in results if c.expected == "caught"]
    n_caught = sum(1 for c, v in results
                   if c.expected == "caught" and v == CAUGHT)
    n_open = sum(1 for c, _ in results if c.expected == "open")
    n_invalid = sum(1 for _, v in results if v == INVALID)
    lines.append(f"[corpus] {n_caught} of {len(caught_cases)} caught-case(s) "
                 f"CAUGHT, {n_open} open, {n_invalid} invalid")
    if cov is not None:
        lines.append(f"[corpus] coverage: {len(cov['covered'])} covered, "
                     f"{len(cov['excluded'])} excluded, "
                     f"{len(cov['uncovered'])} uncovered-and-banked")
    if caught_cases and n_caught == len(caught_cases) and n_invalid == 0:
        lines.append("[corpus] INVESTIGATE: perfect score - a clean sweep is "
                     "investigated as contamination before it is trusted "
                     "(4.2). Cases are authored from scar prose, never from "
                     "guard output; if this sweep is real, say what changed.")
    return "\n".join(lines)


def verdict_json(results: list[tuple[Case, str]], cov: dict | None,
                 exit_code: int) -> str:
    """Machine verdict, printed as the last line beginning `{` (the
    `json_verdict` convention `mcp_server` already parses)."""
    return json.dumps({
        "cases": {c.id: v for c, v in results},
        "totals": {
            "caught": sum(1 for c, v in results
                          if c.expected == "caught" and v == CAUGHT),
            "expected_caught": sum(1 for c, _ in results
                                   if c.expected == "caught"),
            "open": sum(1 for c, _ in results if c.expected == "open"),
            "invalid": sum(1 for _, v in results if v == INVALID),
        },
        "coverage": cov,
        "exit": exit_code,
    }, sort_keys=True)


# ── selfcheck: the scorer must be shown to score ─────────────────────────────

_IN_SELFCHECK = False

_SELFCHECK_CAUGHT = """\
---
case: selfcheck-must-catch
guard: swallow_lint
rule: 2.7
scar: R9-9
expected: caught
---

## defective

```python path=app/units.py
def latest_total(store):
    try:
        return store.fetch()
    except Exception:
        return {}
```

## clean

```python path=app/units.py
def latest_total(store):
    return store.fetch()
```
"""

_SELFCHECK_MISSED = """\
---
case: selfcheck-must-miss
guard: swallow_lint
rule: 2.7
scar: R9-9
expected: caught
---

## defective

```python path=app/units.py
def latest_total(store):
    return store.fetch()
```

## clean

```python path=app/units.py
def latest_total(store):
    return store.fetch()
```
"""

_SELFCHECK_FP = """\
---
case: selfcheck-must-flag-fp
guard: swallow_lint
rule: 2.7
scar: R9-9
expected: caught
---

## defective

```python path=app/units.py
def latest_total(store):
    try:
        return store.fetch()
    except Exception:
        return {}
```

## clean

```python path=app/units.py
def latest_total(store):
    try:
        return store.fetch()
    except Exception:
        return {}
```
"""

_SELFCHECK_BAD = """\
---
case: selfcheck-bad
guard: swallow_lint
---

## defective

```python path=app/units.py
x = 1
```
"""


def selfcheck() -> bool:
    """The pair, per 6.7: a synthetic corpus holding one case that MUST score
    CAUGHT, one that MUST score MISSED, one that MUST score FALSE_POSITIVE,
    and one malformed manifest that MUST be refused - plus the CLI pair, an
    empty directory refused with 2 and saying so, and a minimal valid corpus
    passing with 0 (otherwise the refusal could be refusing everything)."""
    global _IN_SELFCHECK
    if _IN_SELFCHECK:
        return True
    _IN_SELFCHECK = True
    try:
        return _selfcheck_body()
    finally:
        _IN_SELFCHECK = False


def _selfcheck_body() -> bool:
    import contextlib
    import io

    problems: list[str] = []

    def run(argv: list[str]) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue() + err.getvalue()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cases = root / "cases"
        cases.mkdir()
        (cases / "selfcheck-must-catch.md").write_text(_SELFCHECK_CAUGHT)
        (cases / "selfcheck-must-miss.md").write_text(_SELFCHECK_MISSED)
        (cases / "selfcheck-must-flag-fp.md").write_text(_SELFCHECK_FP)
        doctrine = root / "DOCTRINE.md"
        doctrine.write_text("**2.7 exceptions\n")
        syn_rounds = root / "rounds"
        syn_rounds.mkdir()
        (syn_rounds / "round-009.md").write_text(
            "# Round 9 - synthetic\n\n"
            "## Findings\n\n"
            "| id | severity | rule | found-by | status | summary |\n"
            "|---|---|---|---|---|---|\n"
            "| R9-9 | low | 2.7 | synthetic selfcheck | fixed | "
            "placeholder the selfcheck corpus cites |\n"
        )

        loaded = load_cases(root)
        by_id = {c.id: c for c in loaded}
        for want_id in ("selfcheck-must-catch", "selfcheck-must-miss",
                        "selfcheck-must-flag-fp"):
            if want_id not in by_id:
                problems.append(f"selfcheck corpus lost case {want_id}")
        if problems:
            return _fail(problems)

        spec = GUARDS["swallow_lint"]
        verdicts = {}
        for cid in ("selfcheck-must-catch", "selfcheck-must-miss",
                    "selfcheck-must-flag-fp"):
            case = by_id[cid]
            with tempfile.TemporaryDirectory() as twin_td:
                twin = Path(twin_td)
                materialize(case, twin / "d", "defective")
                materialize(case, twin / "c", "clean")
                d_rc = run_twin(spec, twin / "d", case.options, None)
                c_rc = run_twin(spec, twin / "c", case.options, None)
            verdicts[cid] = score(case, d_rc, c_rc, spec)
        for cid, want in (("selfcheck-must-catch", CAUGHT),
                          ("selfcheck-must-miss", MISSED),
                          ("selfcheck-must-flag-fp", FALSE_POSITIVE)):
            if verdicts[cid] != want:
                problems.append(
                    f"synthetic case {cid} scored {verdicts[cid]}, must "
                    f"score {want} - the scorer cannot tell its verdicts apart"
                )

        bad_dir = root / "bad"
        (bad_dir / "cases").mkdir(parents=True)
        (bad_dir / "cases" / "bad.md").write_text(_SELFCHECK_BAD)
        try:
            load_cases(bad_dir)
            problems.append("a manifest missing rule/scar/expected loaded "
                            "without refusal")
        except CorpusError:
            pass

        empty = root / "empty"
        (empty / "cases").mkdir(parents=True)
        rc, said = run([str(empty)])
        if rc != 2 or "no case files" not in said:
            problems.append(
                f"an empty corpus exited {rc}, not 2 naming the empty cases "
                f"dir: {said!r}"
            )

        one = root / "one"
        (one / "cases").mkdir(parents=True)
        (one / "cases" / "only.md").write_text(
            _SELFCHECK_CAUGHT.replace("selfcheck-must-catch", "only"))
        (one / CASE_COUNT_FILE).write_text('{"cases": 1}')
        rc, said = run([str(one), "--doctrine", str(doctrine),
                        "--rounds", str(syn_rounds), "--require-case-count"])
        if rc != 0:
            problems.append(
                f"a minimal valid corpus exited {rc}, not 0 - the empty "
                f"refusal above could be refusing everything: {said!r}"
            )

        # The declared-count pair (R24-2): the same corpus declaring two
        # cases while one is on disk - a deleted case - exits 1 naming the
        # shortfall; and with no declaration, --require-case-count exits 2.
        (one / CASE_COUNT_FILE).write_text('{"cases": 2}')
        rc, said = run([str(one), "--doctrine", str(doctrine),
                        "--rounds", str(syn_rounds)])
        if rc != 1 or "1 short" not in said:
            problems.append(
                f"a corpus one case short of its declared count exited {rc}, "
                f"not 1 naming the shortfall: {said!r}"
            )
        (one / CASE_COUNT_FILE).unlink()
        rc, said = run([str(one), "--doctrine", str(doctrine),
                        "--rounds", str(syn_rounds), "--require-case-count"])
        if rc != 2 or CASE_COUNT_FILE not in said:
            problems.append(
                f"--require-case-count over a corpus with no declaration "
                f"exited {rc}, not 2: {said!r}"
            )
        (one / CASE_COUNT_FILE).write_text('{"cases": 1}')

        # The sweep pair (R23-3): a guard that reads the one clean twin and
        # passes it sweeps 0; a guard that can read none of them (no
        # workflow in a python twin) sweeps 2, never 0.
        archive = ["--doctrine", str(doctrine), "--rounds", str(syn_rounds)]
        rc, said = run([str(one), "--sweep", "swallow_lint"] + archive)
        if rc != 0 or "1 measured-silent" not in said:
            problems.append(
                f"a sweep that measured one silent twin exited {rc}, not 0 "
                f"with its count: {said!r}"
            )
        rc, said = run([str(one), "--sweep", "ci_step_lint"] + archive)
        if rc != 2 or "measured ZERO" not in said:
            problems.append(
                f"a sweep that could read no twin exited {rc}, not 2 - "
                f"silence it never measured read as a pass: {said!r}"
            )

        # The sweep-all pair (R25-4), over a registry narrowed to the
        # guards this one-case corpus can feed: swallow alone measures its
        # twin and passes; with ci_step_lint beside it, the guard that
        # measured nothing makes the whole run 2, never a quiet 0.
        with contextlib.redirect_stdout(io.StringIO()):
            rc_ok = _run_sweep_all(load_cases(one), False, ("swallow_lint",))
            rc_zero = _run_sweep_all(load_cases(one), False,
                                     ("swallow_lint", "ci_step_lint"))
        if rc_ok != 0:
            problems.append(f"a sweep-all whose one guard measured a silent "
                            f"twin exited {rc_ok}, not 0")
        if rc_zero != 2:
            problems.append(f"a sweep-all with one guard that measured no "
                            f"twin exited {rc_zero}, not 2")

    for problem in problems:
        print(f"[corpus] SELFCHECK FAILED: {problem}")
    if not problems:
        print("[corpus] selfcheck ok: synthetic CAUGHT/MISSED/FALSE_POSITIVE "
              "cases scored their verdicts, a malformed manifest refused, an "
              "empty corpus refused with exit 2, a minimal valid corpus passed, "
              "one short of its declared case count failed, a required "
              "declaration that was missing exited 2, "
              "a sweep that measured a twin passed and one that measured none "
              "exited 2, a sweep-all passed only when every guard measured")
    return not problems


def _fail(problems: list[str]) -> bool:
    for problem in problems:
        print(f"[corpus] SELFCHECK FAILED: {problem}")
    return False


# ── CLI ──────────────────────────────────────────────────────────────────────

_KNOWN_FLAGS = {"--case", "--sweep", "--sweep-all", "--doctrine", "--rounds",
                "--backflow", "--json", "--require-case-count", "--selfcheck",
                "--help", "-h"}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or "--selfcheck" in argv:
        return 0 if selfcheck() else 1
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    as_json = "--json" in argv
    require_count = "--require-case-count" in argv
    sweep_all = "--sweep-all" in argv
    case_id: str | None = None
    sweep: str | None = None
    doctrine = "DOCTRINE.md"
    rounds_dir: str | None = "docs/rounds"
    backflow_path: str | None = "docs/backflow.md"
    positional: list[str] = []
    i = 0
    try:
        while i < len(argv):
            a = argv[i]
            if a == "--case":
                case_id = argv[i + 1]; i += 2
            elif a == "--sweep":
                sweep = argv[i + 1]; i += 2
            elif a == "--doctrine":
                doctrine = argv[i + 1]; i += 2
            elif a == "--rounds":
                rounds_dir = argv[i + 1]; i += 2
            elif a == "--backflow":
                backflow_path = argv[i + 1]; i += 2
            elif a.startswith("--"):
                if a not in _KNOWN_FLAGS:
                    print(f"[corpus] unknown flag: {a}", file=sys.stderr)
                    return 2
                i += 1
            else:
                positional.append(a); i += 1
    except IndexError:
        print(f"[corpus] flag {argv[i]!r} needs a value - nothing was "
              f"checked.", file=sys.stderr)
        return 2
    if len(positional) > 1:
        print("[corpus] name at most one corpus root; nothing was checked",
              file=sys.stderr)
        return 2
    root = Path(positional[0] if positional else "corpus")
    if sweep_all and (sweep is not None or case_id is not None):
        print("[corpus] --sweep-all already sweeps every guard; it does not "
              "combine with --sweep or --case. Nothing was checked.",
              file=sys.stderr)
        return 2

    if not selfcheck():
        return 1

    known_rules: set | None = None
    if Path(doctrine).is_file():
        known_rules = doctrine_rule_ids(Path(doctrine))
    else:
        print(f"[corpus] no doctrine file at {doctrine} - rule ids "
              f"checked for shape only, not against the archive")
    scars: set | None = None
    if rounds_dir is not None and Path(rounds_dir).is_dir():
        scars = known_scars(
            Path(rounds_dir),
            Path(backflow_path) if backflow_path else None)
    else:
        print(f"[corpus] no round records at {rounds_dir} - scar citations "
              f"checked for shape only, not against the archive")
    try:
        cases = load_cases(root, known_rules, scars)
    except CorpusError as exc:
        print(f"\n[corpus] {exc}\n")
        return 2

    if case_id is not None:
        return _run_one(cases, case_id, as_json)
    if sweep is not None:
        return _run_sweep(cases, sweep, as_json)
    if sweep_all:
        return _run_sweep_all(cases, as_json)
    return _run_all(cases, root, known_rules, as_json, require_count)


def _score_case(case: Case) -> tuple[str, int, int]:
    """Score one case through a throwaway twin pair. Returns
    (verdict, defective_rc, clean_rc)."""
    spec = GUARDS[case.guard]
    with tempfile.TemporaryDirectory(prefix="sutradhar-corpus-") as td:
        twin = Path(td)
        try:
            materialize(case, twin / "defective", "defective")
            materialize(case, twin / "clean", "clean")
        except CorpusError as exc:
            print(f"[corpus] INVALID {case.id}: {exc}")
            return INVALID, _RC_SPAWN_FAILED, _RC_SPAWN_FAILED
        d_rc = run_twin(spec, twin / "defective", case.options, case.fixture)
        c_rc = run_twin(spec, twin / "clean", case.options, case.fixture)
    return score(case, d_rc, c_rc, spec), d_rc, c_rc


def _run_one(cases: list[Case], case_id: str, as_json: bool) -> int:
    matches = [c for c in cases if c.id == case_id]
    if not matches:
        print(f"[corpus] no case {case_id!r} - known: "
              f"{', '.join(c.id for c in cases)}")
        return 2
    case = matches[0]
    verdict, _, _ = _score_case(case)
    print(f"[corpus] {verdict} {case.id} ({case.guard}, rule {case.rule})")
    code = {CAUGHT: 0, MISSED: 1, FALSE_POSITIVE: 1, INVALID: 2}[verdict]
    if as_json:
        print(json.dumps({"case": case.id, "verdict": verdict,
                          "exit": code}, sort_keys=True))
    return code


def _run_sweep(cases: list[Case], guard_name: str, as_json: bool) -> int:
    """One guard over EVERY clean twin in the corpus - that is what catches
    a guard that flags everything, and it is cross-case so it cannot live
    in per-case scoring (D7).

    Exit mapping differs from scoring on purpose: a sweep asks only "did
    it flag this twin". Exit 2 (nothing here it could read) and 3
    (inconclusive) are silence - most twins are not this guard's cases.
    Timeouts, spawn failures, and signals are infrastructure breaking, not
    silence, and stay INVALID: a hung guard must not read as a quiet one.
    (Case scoring keeps the strict partition: there, a 2/3 means the case
    meant to exercise the guard and the guard could not run.)

    Silence is counted, not assumed (R23-3, 2.9). Every twin lands in one
    of four counts, printed on every run: measured-silent (the guard read
    it and passed it), not-applicable (2/3), flagged, invalid. A sweep that
    measured ZERO twins - nothing silent, nothing flagged - has not passed:
    it exits 2, because "I read none of them" is not "none of them were
    flagged".
    """
    if guard_name not in GUARDS:
        print(f"[corpus] unknown guard {guard_name!r} - known: "
              f"{sorted(GUARDS)}")
        return 2
    spec = GUARDS[guard_name]
    flagged: list[str] = []
    unmeasurable: list[str] = []
    silent = not_applicable = 0
    with tempfile.TemporaryDirectory(prefix="sutradhar-corpus-") as td:
        for case in cases:
            twin = Path(td) / case.id
            try:
                materialize(case, twin, "clean")
            except CorpusError as exc:
                unmeasurable.append(f"{case.id} ({exc})")
                continue
            rc = run_twin(spec, twin, case.options, case.fixture)
            if rc in spec.catch_codes:
                flagged.append(case.id)
            elif rc in spec.clean_codes:
                silent += 1
            elif rc in (2, 3):
                not_applicable += 1
            else:
                unmeasurable.append(f"{case.id} (exit {rc})")
    for cid in flagged:
        print(f"[corpus] SWEEP-FLAGGED {cid} ({guard_name} flagged its "
              f"clean twin)")
    for item in unmeasurable:
        print(f"[corpus] SWEEP-INVALID {item}")
    measured = silent + len(flagged)
    print(f"[corpus] sweep {guard_name}: {len(cases)} clean twin(s) - "
          f"{silent} measured-silent, {not_applicable} not-applicable, "
          f"{len(flagged)} flagged, {len(unmeasurable)} invalid")
    if measured == 0 and not unmeasurable:
        print(f"[corpus] sweep {guard_name} measured ZERO twins - it read "
              f"none of them, which is not a pass (2.9)")
    if unmeasurable or measured == 0:
        code = 2
    else:
        code = 1 if flagged else 0
    if as_json:
        print(json.dumps({"guard": guard_name, "flagged": flagged,
                          "invalid": unmeasurable, "exit": code,
                          "measured_silent": silent,
                          "not_applicable": not_applicable},
                         sort_keys=True))
    return code


def _run_sweep_all(cases: list[Case], as_json: bool,
                   guards: tuple | None = None) -> int:
    """`_run_sweep` for every registry guard (R25-4). The exit follows the
    single sweep's own precedence, worst first: 2 if any guard could not
    be measured or measured zero twins, else 1 if any guard flagged a
    clean twin, else 0. `guards` narrows the registry for the selfcheck
    only; the CLI always sweeps all of it."""
    names = sorted(GUARDS) if guards is None else list(guards)
    codes = {name: _run_sweep(cases, name, as_json) for name in names}
    flagged = sorted(n for n, c in codes.items() if c == 1)
    unmeasured = sorted(n for n, c in codes.items() if c not in (0, 1))
    print(f"[corpus] sweep-all: {len(names)} guard(s) over {len(cases)} "
          f"clean twin(s) - {len(names) - len(flagged) - len(unmeasured)} "
          f"silent, {len(flagged)} flagged a clean twin, {len(unmeasured)} "
          f"could not be measured")
    for name in flagged:
        print(f"[corpus] SWEEP-ALL-FLAGGED {name}")
    for name in unmeasured:
        print(f"[corpus] SWEEP-ALL-UNMEASURED {name} (exit {codes[name]}): "
              f"not a pass (2.9)")
    code = 2 if unmeasured else 1 if flagged else 0
    if as_json:
        print(json.dumps({"sweep_all": codes, "flagged": flagged,
                          "unmeasured": unmeasured, "exit": code},
                         sort_keys=True))
    return code


def _run_all(cases: list[Case], root: Path, known_rules: set | None,
             as_json: bool, require_count: bool = False) -> int:
    count_path = root / CASE_COUNT_FILE
    try:
        declared = load_case_count(count_path)
    except CorpusError as exc:
        print(f"\n[corpus] {exc}\n")
        return 2
    if declared is None and require_count:
        print(f"[corpus] --require-case-count, and no {count_path}: the "
              f"total cannot be asserted, so nothing is reported as a pass. "
              f'Write {{"cases": {len(cases)}}} there in a reviewed diff.')
        return 2
    results = [(case, _score_case(case)[0]) for case in cases]
    cov: dict | None = None
    if known_rules is None:
        print("[corpus] no doctrine rule list - coverage partition skipped, "
              "not passed: without the rule list there is no floor to hold")
    else:
        try:
            cov = coverage(
                cases, known_rules,
                parse_exclusions(root / "EXCLUSIONS.md"),
                load_floor(root / "uncovered.json"),
            )
        except (CorpusError, CoverageError) as exc:
            print(f"\n[corpus] coverage floor does not hold:\n  {exc}\n")
            print(report(results, None))
            if as_json:
                print(verdict_json(results, None, 1))
            return 1
    print(report(results, cov))
    count_problem = None
    if declared is None:
        print(f"[corpus] no {count_path} - {len(cases)} case(s) counted, "
              f"the total not asserted against a declared number")
    else:
        count_problem = case_count_problem(len(cases), declared, count_path)
        if count_problem:
            print(f"[corpus] case count does not hold: {count_problem}")
        else:
            print(f"[corpus] case count holds: {len(cases)} of {declared} "
                  f"declared")
    invalid = sum(1 for _, v in results if v == INVALID)
    if invalid:
        code = 2
    elif count_problem:
        code = 1
    elif any(v == MISSED for c, v in results if c.expected == "caught"):
        code = 1
    elif any(v == FALSE_POSITIVE for _, v in results):
        code = 1
    elif any(v == CAUGHT for c, v in results if c.expected == "open"):
        print("[corpus] an open case is now CAUGHT - flip its manifest to "
              "`expected: caught` in a reviewed diff, or say why not")
        code = 1
    else:
        code = 0
    if as_json:
        print(verdict_json(results, cov, code))
    return code


if __name__ == "__main__":
    sys.exit(main())
