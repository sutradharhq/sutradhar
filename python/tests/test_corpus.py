import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards import corpus
from sutradhar_guards.corpus import (
    CAUGHT,
    FALSE_POSITIVE,
    INVALID,
    MISSED,
    CoverageError,
    CorpusError,
    coverage,
    load_cases,
    score,
)


def _manifest(case_id, guard="swallow_lint", rule="2.7", scar="distribution",
              expected="caught", defective="", clean="", extra="",
              scar_argument="synthetic case for the corpus machinery tests"):
    head = (
        "---\n"
        f"case: {case_id}\n"
        f"guard: {guard}\n"
        f"rule: {rule}\n"
        f"scar: {scar}\n"
    )
    if scar == "distribution":
        head += f"scar_argument: {scar_argument}\n"
    head += f"expected: {expected}\n{extra}---\n"
    return (
        head
        + "\n## defective\n\n```python path=app/units.py\n"
        + defective
        + "```\n\n## clean\n\n```python path=app/units.py\n"
        + clean
        + "```\n"
    )


SWALLOW = (
    "def latest_total(store):\n"
    "    try:\n"
    "        return store.fetch()\n"
    "    except Exception:\n"
    "        return {}\n"
)
PLAIN = (
    "def latest_total(store):\n"
    "    return store.fetch()\n"
)


def _write(root: Path, name: str, text: str) -> None:
    (root / "cases").mkdir(parents=True, exist_ok=True)
    (root / "cases" / name).write_text(text, encoding="utf-8")


def _run(argv: list) -> tuple:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = corpus.main(argv)
    return code, out.getvalue() + err.getvalue()


def _json_of(said: str) -> dict:
    last = [line for line in said.splitlines() if line.startswith("{")][-1]
    return json.loads(last)


def test_a_case_whose_defect_is_not_flagged_is_missed_not_caught(tmp_path):
    """Mutation: in score(), `if defective_rc in spec.catch_codes:` changed
    to `if True:` flips this case to CAUGHT and the exit to 0."""
    _write(tmp_path, "quiet.md",
           _manifest("quiet", defective=PLAIN, clean=PLAIN))
    code, said = _run([str(tmp_path), "--json"])
    assert code == 1
    assert _json_of(said)["cases"] == {"quiet": MISSED}


def test_a_guard_that_flags_the_clean_twin_is_a_false_positive_not_a_catch(
        tmp_path):
    """Mutation: scoring the defective twin first (catch before clean)
    reports this as CAUGHT; the clean side must be judged first."""
    _write(tmp_path, "loud.md",
           _manifest("loud", defective=SWALLOW, clean=SWALLOW))
    code, said = _run([str(tmp_path), "--json"])
    assert code == 1
    assert _json_of(said)["cases"] == {"loud": FALSE_POSITIVE}


def test_an_exit_2_from_a_guard_is_invalid_and_never_a_catch(tmp_path):
    """Mutation: treating any nonzero exit as a catch scores the defective
    twin below as CAUGHT. Exit 2 is out-of-partition (could not run), so
    the verdict is INVALID and the run exits 2, never 0 or 1.

    The defective twin names a metrics file that does not exist, which the
    real obsgate refuses with exit 3 (INCONCLUSIVE, party-attributed); the
    clean twin is satisfied and silent. Unit pins below cover the other
    out-of-partition codes a runner can return (timeout, spawn failure,
    signal)."""
    floor = '{"surfaces": [{"name": "units", "pattern": "units_up"}]}'
    metrics = 'units_up{device="a"} 1\n'
    text = (
        "---\ncase: unwitnessed\nguard: obsgate\nrule: 6.6\n"
        "scar: distribution\nscar_argument: synthetic case for the exit "
        "partition test\nexpected: caught\n---\n"
        "\n## defective\n\n```text path=floor.json\n" + floor + "\n```\n"
        "\n## clean\n\n```text path=floor.json\n" + floor + "\n```\n"
        "```text path=metrics.txt\n" + metrics + "```\n"
    )
    _write(tmp_path, "unwitnessed.md", text)
    code, said = _run([str(tmp_path), "--json"])
    assert code == 2
    assert _json_of(said)["cases"] == {"unwitnessed": INVALID}
    spec = corpus.GUARDS["obsgate"]
    fake = corpus.Case(id="x", guard="obsgate", rule="6.6", scars=(),
                       distribution=True, expected="caught", fixture=None,
                       options=(), defective=(), clean=(), helpers=(),
                       source="x")
    for rc in (2, 3, 124, 125, -9):
        assert score(fake, rc, 0, spec) == INVALID
        assert score(fake, 1, rc, spec) == INVALID


def test_the_denominator_comes_from_the_manifest_set_not_a_loop_counter(
        tmp_path):
    """Mutation: a `step += 1` loop counter as the denominator still prints
    "2 of 2" here, and prints "1 of 1" after the deletion in the next test -
    the pin is that the totals name the manifest set, so only the
    deletion-sensitive assertion below can tell them apart."""
    _write(tmp_path, "a.md", _manifest("a", defective=SWALLOW, clean=PLAIN))
    _write(tmp_path, "b.md", _manifest("b", defective=SWALLOW, clean=PLAIN))
    code, said = _run([str(tmp_path), "--json"])
    assert code == 0
    totals = _json_of(said)["totals"]
    assert totals == {"caught": 2, "expected_caught": 2, "open": 0,
                      "invalid": 0}


def test_deleting_a_case_file_fails_against_the_declared_count(tmp_path):
    """R24-2. This test used to be named `..._changes_the_total_and_fails`
    and asserted only that the total dropped, with exit 0: the corpus
    printed "1 of 1" and passed, the R22-1 shape one level down. Now the
    pair: two cases declared and on disk pass; delete one and the same run
    exits 1 naming the shortfall; lower the declaration in the same change
    and it passes again - the floor moves, and only visibly.

    Mutation (the line that runs, in _run_all): `elif count_problem:` ->
    `elif False:` - the deletion exits 0, red.
    """
    _write(tmp_path, "a.md", _manifest("a", defective=SWALLOW, clean=PLAIN))
    _write(tmp_path, "b.md", _manifest("b", defective=SWALLOW, clean=PLAIN))
    (tmp_path / "case_count.json").write_text('{"cases": 2}')
    code, said = _run([str(tmp_path), "--json"])
    assert code == 0, said
    assert "case count holds: 2 of 2" in said
    (tmp_path / "cases" / "b.md").unlink()
    code, said = _run([str(tmp_path), "--json"])
    assert code == 1, said
    assert "1 case file(s) on disk, 2 declared" in said and "1 short" in said
    assert _json_of(said)["exit"] == 1
    (tmp_path / "case_count.json").write_text('{"cases": 1}')
    code, said = _run([str(tmp_path)])
    assert code == 0, said


def test_adding_a_case_without_raising_the_declared_count_fails(tmp_path):
    """The other direction: a floor left below new cases would let the next
    deletion pass unseen, so a count above the declaration fails too.

    Mutation (the line that runs, in case_count_problem): `if on_disk >
    declared:` -> `if False:` - exit 0, red.
    """
    _write(tmp_path, "a.md", _manifest("a", defective=SWALLOW, clean=PLAIN))
    _write(tmp_path, "b.md", _manifest("b", defective=SWALLOW, clean=PLAIN))
    (tmp_path / "case_count.json").write_text('{"cases": 1}')
    code, said = _run([str(tmp_path)])
    assert code == 1, said
    assert "1 over" in said


def test_require_case_count_refuses_a_corpus_with_no_declaration(tmp_path):
    """Deleting `case_count.json` together with a case must not be a way
    round the floor in this repository's CI, which passes the flag. Without
    the flag the run says the total is not asserted (the pair).

    Mutation (the line that runs, in _run_all): `if declared is None and
    require_count:` -> `if False:` - exit 0, red.
    """
    _write(tmp_path, "a.md", _manifest("a", defective=SWALLOW, clean=PLAIN))
    code, said = _run([str(tmp_path), "--require-case-count"])
    assert code == 2, said
    assert "case_count.json" in said
    code, said = _run([str(tmp_path)])
    assert code == 0, said
    assert "not asserted" in said


@pytest.mark.parametrize("text", ['{"cases": 0}', '{"cases": "2"}', "[2]",
                                  '{"cases": 2, "extra": 1}', "not json",
                                  '{"cases": true}'])
def test_an_unreadable_declared_count_is_refused_not_read_as_absent(
        tmp_path, text):
    """A broken floor read as no floor would pass every deletion (2.7).

    Mutation: load_case_count's shape-check `raise CorpusError(` ->
    `return None; raise CorpusError(` - the five shape cases exit 0, red
    ("not json" reaches the JSON-error raise above it and stays green).
    """
    _write(tmp_path, "a.md", _manifest("a", defective=SWALLOW, clean=PLAIN))
    (tmp_path / "case_count.json").write_text(text)
    code, said = _run([str(tmp_path)])
    assert code == 2, said
    assert "declared case count" in said


def test_this_repositorys_corpus_declares_exactly_its_case_files():
    """The real floor, read the way CI reads it."""
    root = Path(__file__).resolve().parents[2] / "corpus"
    declared = corpus.load_case_count(root / "case_count.json")
    on_disk = len(list((root / "cases").glob("*.md")))
    assert declared == on_disk, (declared, on_disk)


def test_a_case_citing_a_scar_no_round_record_contains_is_refused(tmp_path):
    """Mutation: skipping scar resolution when --rounds is given loads this
    case and scores it; the refusal must happen at load, exit 2."""
    rounds = tmp_path / "rounds"
    rounds.mkdir()
    (rounds / "round-009.md").write_text(
        "# Round 9\n\n| R9-9 | low | 2.7 | x | fixed | y |\n")
    doctrine = tmp_path / "DOCTRINE.md"
    doctrine.write_text("**2.7 exceptions\n")
    _write(tmp_path, "orphan.md",
           _manifest("orphan", rule="2.7", scar="R99-9",
                     defective=SWALLOW, clean=PLAIN))
    code, said = _run([str(tmp_path), "--doctrine", str(doctrine),
                       "--rounds", str(rounds)])
    assert code == 2
    assert "R99-9" in said


def test_a_manifest_naming_an_unknown_guard_is_refused_with_exit_2(tmp_path):
    """Mutation: defaulting an unknown guard to a bare subprocess call
    would run whatever argv the manifest smuggled in - the registry owns
    every invocation shape, so the load refuses."""
    _write(tmp_path, "strange.md",
           _manifest("strange", guard="definitely_not_a_guard",
                     defective=SWALLOW, clean=PLAIN))
    code, said = _run([str(tmp_path)])
    assert code == 2
    assert "unknown guard" in said


def test_a_manifest_cannot_name_a_command(tmp_path):
    """The security pin (D2): the fixed frontmatter key set is what keeps a
    manifest from becoming a script. Mutation: adding `command` to the
    accepted keys loads this manifest and runs its twins."""
    text = _manifest("sneaky", defective=SWALLOW, clean=PLAIN)
    text = text.replace("expected: caught",
                        "expected: caught\ncommand: do_not_run_this")
    _write(tmp_path, "sneaky.md", text)
    code, said = _run([str(tmp_path)])
    assert code == 2
    assert "never a command" in said


def test_an_open_case_that_is_now_caught_demands_a_manifest_flip(tmp_path):
    """Mutation: scoring open cases as findings-free reports exit 0, and a
    guard that learned the defect never gets its manifest flipped."""
    _write(tmp_path, "learned.md",
           _manifest("learned", expected="open",
                     defective=SWALLOW, clean=PLAIN))
    code, said = _run([str(tmp_path)])
    assert code == 1
    assert "flip" in said


def test_an_empty_corpus_directory_is_refused_with_exit_2(tmp_path):
    """Mutation: returning "0 of 0" with exit 0 reports a trustworthy total
    over nothing measured (the run-the-guards.sh scar, R22-1)."""
    (tmp_path / "cases").mkdir()
    code, said = _run([str(tmp_path)])
    assert code == 2
    assert "no case files" in said
    assert str(tmp_path / "cases") in said


def test_a_rule_that_loses_its_last_case_fails_the_coverage_floor():
    """Mutation: a floor that treats "no case and no entry" as covered
    never demands the sentence. Direct unit on coverage(): rule 2.8 has
    neither a case nor a banked reason, so the floor must refuse."""
    case = corpus.Case(id="x", guard="swallow_lint", rule="2.7", scars=(),
                       distribution=True, expected="caught", fixture=None,
                       options=(), defective=(), clean=(), helpers=(),
                       source="x")
    with pytest.raises(CoverageError, match="2.8"):
        coverage([case], {"2.7", "2.8"}, {}, {})


def test_a_banked_uncovered_rule_that_gained_a_case_must_be_removed():
    """The guard-the-guard half of the ratchet: a floor entry that quietly
    stopped being uncovered must leave, or the floor stops meaning
    anything. Mutation: ignoring stale entries keeps this green."""
    case = corpus.Case(id="x", guard="swallow_lint", rule="2.7", scars=(),
                       distribution=True, expected="caught", fixture=None,
                       options=(), defective=(), clean=(), helpers=(),
                       source="x")
    with pytest.raises(CoverageError, match="no longer uncovered"):
        coverage([case], {"2.7"}, {}, {"2.7": "not yet"})


def test_load_refuses_a_case_id_that_is_not_the_filename(tmp_path):
    (tmp_path / "cases").mkdir(parents=True, exist_ok=True)
    (tmp_path / "cases" / "right-name.md").write_text(
        _manifest("wrong-name", defective=SWALLOW, clean=PLAIN),
        encoding="utf-8")
    with pytest.raises(CorpusError, match="does not match the filename"):
        load_cases(tmp_path)


def test_every_registered_guard_builds_a_runnable_shape(tmp_path):
    """Mutation: changing a builder's arity (or a registry entry's kind)
    without updating its callers breaks every runner adapter at sweep
    time, long after the suite went green. This pins the contract:
    CLI builders return an argv starting at an existing guard file,
    runner builders return a script that parses."""
    import ast

    guards_home = Path(corpus.__file__).resolve().parent
    for name, spec in sorted(corpus.GUARDS.items()):
        if spec.kind == "cli":
            argv = spec.build(tmp_path, ())
            assert argv[1].endswith(f"{spec.module}.py")
            assert Path(argv[1]).is_file(), f"{name}: {argv[1]} is not a file"
            continue
        if spec.two_commit:
            with pytest.raises(corpus.CorpusError):
                spec.build(tmp_path, guards_home, (), None)
            script = spec.build(tmp_path, guards_home, (), "two_commit")
        else:
            script = spec.build(tmp_path, guards_home, (), None)
        ast.parse(script)
        assert spec.module in script, f"{name}: runner never names its guard"


# ── the sweep counts what it measured (R23-3, 2.9) ──────────────────────────

def _fake_guard(monkeypatch, exit_code: int) -> None:
    """Register a guard that exits `exit_code` on every twin it is shown."""
    spec = corpus._Spec(
        "fake", "cli",
        lambda tmp, options: [sys.executable, "-c",
                              f"raise SystemExit({exit_code})"],
        (1,), (0,),
    )
    monkeypatch.setitem(corpus.GUARDS, "fake", spec)


def _two_cases(tmp_path):
    _write(tmp_path, "a.md", _manifest("a", defective=SWALLOW, clean=PLAIN))
    _write(tmp_path, "b.md", _manifest("b", defective=SWALLOW, clean=PLAIN))


def test_a_sweep_that_could_read_no_twin_exits_two_not_zero(tmp_path,
                                                             monkeypatch):
    """A guard that exits 2 on every twin measured nothing, and a sweep that
    measured nothing has not passed. Mutation: in _run_sweep, `if
    unmeasurable or measured == 0:` changed to `if unmeasurable:` turns this
    red twice over - the embedded selfcheck's sweep pair fails (exit 1), and
    with the selfcheck stubbed out the sweep itself returns 0, silence it
    never measured read as a pass."""
    _two_cases(tmp_path)
    _fake_guard(monkeypatch, 2)
    code, said = _run([str(tmp_path), "--sweep", "fake", "--json"])
    assert code == 2, said
    assert "measured ZERO" in said
    report = _json_of(said)
    assert report["measured_silent"] == 0 and report["not_applicable"] == 2


def test_a_sweep_that_measured_its_twins_and_flagged_none_exits_zero(
        tmp_path, monkeypatch):
    """The pair: the zero-measured refusal must not refuse everything.
    Mutation: `elif rc in spec.clean_codes: silent += 1` changed to count
    into not_applicable turns this red (exit 2, silent 0)."""
    _two_cases(tmp_path)
    _fake_guard(monkeypatch, 0)
    code, said = _run([str(tmp_path), "--sweep", "fake", "--json"])
    assert code == 0, said
    assert "2 measured-silent, 0 not-applicable" in said
    assert _json_of(said)["measured_silent"] == 2


def test_not_applicable_twins_do_not_fail_a_sweep_that_measured_one(
        tmp_path, monkeypatch):
    """Most twins are not a given guard's cases; exit 2 on them is a real
    answer. One measured twin beside them is enough. Mutation: treating
    every exit 2 as SWEEP-INVALID exits 2 here."""
    _write(tmp_path, "a.md", _manifest("a", defective=SWALLOW, clean=PLAIN))
    _write(tmp_path, "b.md", _manifest("b", defective=SWALLOW,
                                       clean="# readable\n"))
    spec = corpus._Spec(
        "fake", "cli",
        lambda tmp, options: [
            sys.executable, "-c",
            "import pathlib,sys; "
            "t=(pathlib.Path('app')/'units.py').read_text(); "
            "sys.exit(0 if 'readable' in t else 2)"],
        (1,), (0,),
    )
    monkeypatch.setitem(corpus.GUARDS, "fake", spec)
    code, said = _run([str(tmp_path), "--sweep", "fake", "--json"])
    assert code == 0, said
    assert "1 measured-silent, 1 not-applicable, 0 flagged" in said


def test_the_byte_order_mark_case_really_materializes_the_mark(tmp_path):
    """R24-27's case is only a case if both twins start with EF BB BF on
    disk; an editor that strips the invisible U+FEFF would quietly turn it
    into an ordinary swallow case. Pinned on the materialized bytes."""
    root = Path(__file__).resolve().parents[2] / "corpus"
    case = [c for c in load_cases(root)
            if c.id == "swallow-behind-a-byte-order-mark"][0]
    for twin in ("defective", "clean"):
        out = corpus.materialize(case, tmp_path / twin, twin)
        data = (out / "app" / "reader.py").read_bytes()
        assert data.startswith(b"\xef\xbb\xbf"), (twin, data[:8])


# ── --sweep-all: every registry guard over every clean twin (R25-4) ─────────

def _registry(monkeypatch, **exit_codes) -> None:
    """Replace the registry with fake guards exiting the given codes, and stub
    the embedded selfcheck, which needs the real swallow and ci_step guards.
    The cases name `swallow_lint`, so a silent fake keeps that name loadable."""
    monkeypatch.setattr(corpus, "selfcheck", lambda: True)
    exit_codes = {"swallow_lint": 0, **exit_codes}
    monkeypatch.setattr(corpus, "GUARDS", {
        name: corpus._Spec(
            name, "cli",
            (lambda rc: lambda tmp, options: [
                sys.executable, "-c", f"raise SystemExit({rc})"])(rc),
            (1,), (0,))
        for name, rc in exit_codes.items()})


def test_sweep_all_passes_only_when_every_guard_measured_silence(
        tmp_path, monkeypatch):
    """Mutation: `code = 2 if unmeasured else 1 if flagged else 0` changed
    to `code = 0` leaves this green and turns the next two red."""
    _two_cases(tmp_path)
    _registry(monkeypatch, quiet_a=0, quiet_b=0)
    code, said = _run([str(tmp_path), "--sweep-all", "--json"])
    assert code == 0, said
    assert "3 guard(s) over 2 clean twin(s) - 3 silent, 0 flagged" in said
    assert _json_of(said)["sweep_all"] == {
        "quiet_a": 0, "quiet_b": 0, "swallow_lint": 0}


def test_sweep_all_names_the_guard_that_flagged_another_cases_clean_twin(
        tmp_path, monkeypatch):
    """The blind spot itself: per-case scoring never runs a guard over a
    case that is not its own, so only a sweep sees this."""
    _two_cases(tmp_path)
    _registry(monkeypatch, quiet=0, noisy=1)
    code, said = _run([str(tmp_path), "--sweep-all", "--json"])
    assert code == 1, said
    assert "SWEEP-ALL-FLAGGED noisy" in said
    assert _json_of(said)["flagged"] == ["noisy"]


def test_sweep_all_with_a_guard_that_measured_nothing_is_not_a_pass(
        tmp_path, monkeypatch):
    """2 outranks 1, as in a single sweep: a guard that read no twin has not
    been swept, whatever the others found."""
    _two_cases(tmp_path)
    _registry(monkeypatch, noisy=1, blind=2)
    code, said = _run([str(tmp_path), "--sweep-all", "--json"])
    assert code == 2, said
    assert "SWEEP-ALL-UNMEASURED blind" in said


def test_sweep_all_reads_the_registry_not_a_list_of_its_own(
        tmp_path, monkeypatch):
    """A guard added to GUARDS is swept with no other edit - the reason this
    is one flag and not one CI step per guard. Mutation: `names =
    sorted(GUARDS)` replaced with the fifteen names spelled out turns this
    red (the added guard is never run)."""
    _two_cases(tmp_path)
    monkeypatch.setattr(corpus, "selfcheck", lambda: True)
    monkeypatch.setitem(corpus.GUARDS, "added_later", corpus._Spec(
        "added_later", "cli",
        lambda tmp, options: [sys.executable, "-c", "raise SystemExit(1)"],
        (1,), (0,)))
    code, said = _run([str(tmp_path), "--sweep-all", "--json"])
    assert "added_later" in _json_of(said)["sweep_all"], said
    assert "SWEEP-ALL-FLAGGED added_later" in said


def test_sweep_all_refuses_to_combine_with_sweep_or_case(tmp_path):
    _two_cases(tmp_path)
    for extra in (["--sweep", "swallow_lint"], ["--case", "a"]):
        code, said = _run([str(tmp_path), "--sweep-all"] + extra)
        assert code == 2 and "does not combine" in said, (extra, said)


def test_ci_sweeps_every_guard_over_the_corpus():
    """R25-4 is closed only while CI runs the flag: read the step out of the
    workflow. Mutation: deleting the step turns this red."""
    wf = (Path(__file__).resolve().parents[2] / ".github" / "workflows"
          / "selftest.yml").read_text(encoding="utf-8")
    runs = [line.split("run:", 1)[1].strip() for line in wf.splitlines()
            if line.strip().startswith("run:")]
    assert any("python/sutradhar_guards/corpus.py corpus/" in r
               and "--sweep-all" in r for r in runs), runs


# ── the verify adapter's fixture, under a hook's GIT_DIR ────────────────────

def test_verify_twin_under_a_hook_git_dir_leaves_that_repo_untouched(tmp_path, monkeypatch):
    """A sweep started from a git hook inherits GIT_DIR, and the adapter's
    `cwd=_TMP` does not override it: before the fix its `git init` and two
    commits landed in the hook's repository (verify_guard's selfcheck did
    the same to an adopter's repository on 2026-10-26)."""
    import os
    import subprocess
    clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    host = tmp_path / "host"
    subprocess.run(["git", "init", "-q", "-b", "main", str(host)], check=True,
                   capture_output=True, env=clean)
    subprocess.run(["git", "-C", str(host), "-c", "user.name=t",
                    "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
                    "commit", "-q", "--allow-empty", "-m", "host"],
                   check=True, capture_output=True, env=clean)

    def state():
        def git(*args):
            return subprocess.run(["git", f"--git-dir={host / '.git'}", *args],
                                  capture_output=True, text=True, check=True,
                                  env=clean).stdout
        return (git("config", "--get", "core.bare"),
                git("for-each-ref", "--format=%(refname) %(objectname)"),
                (host / ".git" / "config").read_bytes())

    cases = [c for c in corpus.load_cases(Path(corpus.__file__).resolve().parents[2] / "corpus")
             if c.fixture == "two_commit"]
    assert cases, "no two_commit case in the corpus: nothing below would run"
    case = cases[0]
    twin = tmp_path / "twin" / "defective"
    corpus.materialize(case, twin, "defective")
    before = state()
    monkeypatch.setenv("GIT_DIR", str(host / ".git"))
    spec = corpus.GUARDS[case.guard]
    rc = corpus.run_twin(spec, twin, case.options, case.fixture)
    monkeypatch.delenv("GIT_DIR")
    assert state() == before
    assert rc in spec.catch_codes + spec.clean_codes, (
        f"the twin did not run to a verdict (exit {rc})")
