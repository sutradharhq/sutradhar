"""Tests for swallow_lint - including the red cases.

Every guard here is itself mutation-verified: for each thing the detector
must catch there is a test that FAILS if the detector goes blind to it.
"""
import json
import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.swallow_lint import (
    VENDOR_DIRS,
    _is_vendor,
    check_source,
    main,
    selfcheck,
)


def test_flags_return_empty_dict():
    src = """
def f():
    try:
        risky()
    except Exception:
        return {}
"""
    assert len(check_source(src)) == 1


def test_flags_bare_except_pass():
    src = """
def f():
    try:
        risky()
    except:
        pass
"""
    assert len(check_source(src)) == 1


def test_flags_tuple_handler_containing_exception():
    src = """
def f():
    try:
        risky()
    except (ValueError, Exception):
        return None
"""
    assert len(check_source(src)) == 1


def test_flags_continue_in_loop():
    src = """
def f(items):
    for i in items:
        try:
            risky(i)
        except Exception:
            continue
"""
    assert len(check_source(src)) == 1


def test_logged_swallow_is_clean():
    src = """
def f():
    try:
        risky()
    except Exception as exc:
        log.warning(f"degraded: {exc}")
        return {}
"""
    assert check_source(src) == []


def test_reraise_is_clean():
    src = """
def f():
    try:
        risky()
    except Exception:
        cleanup()
        raise
"""
    assert check_source(src) == []


def test_narrow_handler_is_clean():
    # A narrow catch that returns empty is a judgment call, not a swallow of
    # the world - the guard only polices broad handlers.
    src = """
def f():
    try:
        risky()
    except KeyError:
        return {}
"""
    assert check_source(src) == []


def test_custom_degrade_call_is_clean():
    src = """
def f():
    try:
        risky()
    except Exception:
        mark_degraded("f")
        return {}
"""
    assert check_source(src, extra_calls={"mark_degraded"}) == []


def test_handler_doing_real_work_is_clean():
    src = """
def f():
    try:
        risky()
    except Exception:
        result = fallback_computation()
        return result
"""
    assert check_source(src) == []


def test_selfcheck_passes():
    assert selfcheck()


def test_baseline_ratchet_flow(tmp_path, monkeypatch):
    """End to end: baseline freezes today, a new swallow beyond it fails."""
    monkeypatch.chdir(tmp_path)
    mod = tmp_path / "m.py"
    mod.write_text(
        "def f():\n    try:\n        g()\n    except Exception:\n        return {}\n"
    )
    baseline = tmp_path / "swallow_baseline.json"

    assert main([str(mod), "--update-baseline", "--baseline", str(baseline)]) == 0
    assert json.loads(baseline.read_text()) == {"m.py": 1}

    # At the baseline: green.
    assert main([str(mod), "--baseline", str(baseline)]) == 0

    # One MORE swallow: red. This is the mutation case for the ratchet.
    mod.write_text(
        mod.read_text()
        + "def h():\n    try:\n        g()\n    except Exception:\n        return []\n"
    )
    assert main([str(mod), "--baseline", str(baseline)]) == 1


# ── vendor trees: the guard must not be buried by findings nobody can fix ────
# Field report from an adopting repo: pointed at the project root, the walk
# descended into `.venv` and returned ~80 third-party swallows around the one
# real finding in `app/`. The guard was switched off that afternoon - not
# because it was wrong, but because its signal was unreadable. A guard whose
# output nobody reads has stopped guarding (2.1).


def _plant_vendor_tree(root: Path) -> Path:
    """One real swallow in app/, three inside a virtualenv."""
    swallow = "def f():\n    try:\n        g()\n    except Exception:\n        return {}\n"
    (root / "app").mkdir(parents=True)
    (root / "app" / "real.py").write_text(swallow)
    vendor = root / ".venv" / "lib" / "python3.11" / "site-packages" / "pkg"
    vendor.mkdir(parents=True)
    for i in range(3):
        (vendor / f"v{i}.py").write_text(swallow)
    return root / "app" / "real.py"


def test_the_walk_skips_vendor_trees_and_still_finds_the_real_one(tmp_path, capsys):
    _plant_vendor_tree(tmp_path)
    rc = main([str(tmp_path), "--baseline", str(tmp_path / "none.json")])
    out = capsys.readouterr().out
    assert rc == 1, "the real swallow in app/ must still fail the gate"

    # The findings block - everything after the "NEW silent swallow(s)"
    # header - must name the real file and no vendor one. Asserting against
    # the whole of stdout would pass vacuously off the skip notice, which
    # legitimately contains vendor directory names.
    findings = out.split("NEW silent swallow(s)", 1)[1]
    assert "app/real.py" in findings
    assert "site-packages" not in findings, findings
    assert "v0.py" not in findings, findings


def test_the_skip_is_reported_never_silent(tmp_path, capsys):
    """2.4 applied to the guard itself: an exclusion the operator cannot see
    is 'OK' printed over a tree nothing read. Deleting the notice must fail
    this test even though the scan result is unchanged."""
    _plant_vendor_tree(tmp_path)
    main([str(tmp_path), "--baseline", str(tmp_path / "none.json")])
    out = capsys.readouterr().out
    assert "skipped 3 file(s)" in out, out
    assert "--include-vendor" in out, "the notice must name the way to override it"


def test_include_vendor_scans_everything(tmp_path, capsys):
    """The override is real, not decoration: with it, all four are found."""
    _plant_vendor_tree(tmp_path)
    rc = main([
        str(tmp_path), "--include-vendor", "--baseline", str(tmp_path / "none.json")
    ])
    out = capsys.readouterr().out
    assert rc == 1
    assert out.count("v0.py") >= 1 and out.count("v1.py") >= 1 and out.count("v2.py") >= 1
    assert "skipped" not in out


def test_an_explicitly_named_vendor_file_is_still_scanned(tmp_path):
    """Only the WALK excludes. Asking for a vendor path by name and getting a
    silent pass would be the same lie in the other direction."""
    _plant_vendor_tree(tmp_path)
    target = tmp_path / ".venv" / "lib" / "python3.11" / "site-packages" / "pkg" / "v0.py"
    assert main([str(target), "--baseline", str(tmp_path / "none.json")]) == 1


def test_is_vendor_judges_relative_to_the_named_root(tmp_path):
    """The asymmetry in one assertion: the same file is vendor when reached by
    walking the project, and first-party when the venv itself is the root."""
    f = tmp_path / ".venv" / "pkg" / "x.py"
    f.parent.mkdir(parents=True)
    f.write_text("")
    assert _is_vendor(f, tmp_path) is True
    assert _is_vendor(f, tmp_path / ".venv") is False


# ── an empty scan is not a pass (R21-2) ──────────────────────────────────────
# `OK (0 files, ...)` and exit 0 was the answer for paths holding no Python,
# so a CI step aimed at the wrong directory reported green on every run and
# had read nothing. Exit 2 is this toolkit's "the check could not run".


def test_a_directory_with_no_python_is_refused_and_named(tmp_path, capsys):
    (tmp_path / "README.md").write_text("docs only\n")
    rc = main([str(tmp_path), "--baseline", str(tmp_path / "none.json")])
    said = capsys.readouterr()
    assert rc == 2, said
    assert "nothing was scanned" in said.err and str(tmp_path) in said.err
    assert "holds no .py file" in said.err
    assert "OK" not in said.out + said.err


def test_no_argument_and_no_src_names_the_default_it_assumed(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main([]) == 2
    err = capsys.readouterr().err
    assert "src (does not exist)" in err and "src/ was assumed" in err


def test_a_floor_is_not_recorded_over_nothing(tmp_path):
    """A baseline written over zero files is a floor of nothing, and the next
    run would gate against it as if it meant something."""
    base = tmp_path / "b.json"
    assert main([str(tmp_path), "--update-baseline", "--baseline", str(base)]) == 2
    assert not base.exists()


def test_a_tree_holding_only_vendor_files_says_how_to_scan_them(tmp_path, capsys):
    vendor = tmp_path / ".venv" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "dep.py").write_text("x = 1\n")
    assert main([str(tmp_path), "--baseline", str(tmp_path / "none.json")]) == 2
    assert "--include-vendor" in capsys.readouterr().err


def test_vendor_list_excludes_dirs_that_are_often_real_source():
    """A too-greedy exclusion silently stops scanning the adopter's code -
    the failure mode this whole change is trying to avoid, inverted. `build`,
    `dist` and `env` are real package names in real projects."""
    for risky in ("build", "dist", "env", "src", "app", "lib", "test", "tests"):
        assert risky not in VENDOR_DIRS, risky


def test_a_file_and_a_symlink_to_it_are_read_once(tmp_path, monkeypatch,
                                                   capsys):
    """R24-23, kept consistent with conflated_degrade_lint: the swallow is
    one finding and the tree is one file, not two.

    Mutation: `if target in seen: continue` -> `if False: continue` in
    _read_once - "2 files", red.
    """
    from sutradhar_guards.swallow_lint import main
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1\n")
    (src / "link.py").symlink_to("a.py")
    monkeypatch.chdir(tmp_path)
    assert main(["src", "--baseline", "none.json"]) == 0
    assert "OK (1 files" in capsys.readouterr().out


def test_a_symlink_out_of_the_scanned_paths_is_skipped_and_said(
        tmp_path, monkeypatch, capsys):
    """R24-23's outside-root rule, pinned here as well as in
    conflated_degrade_lint: a link to a swallow outside every scanned
    directory is skipped and the count printed; the same file inside the
    scanned root is still reported (the pair).

    Mutation (the line that runs, in _read_once): `if is_link and not
    any(...)` -> `if False and not any(...)` - the far swallow is read
    through the link and fails the clean tree, red.
    """
    from sutradhar_guards.swallow_lint import main
    bad = ("def f(s):\n    try:\n        return s.read()\n"
           "    except Exception:\n        pass\n")
    far = tmp_path / "elsewhere"
    far.mkdir()
    (far / "far.py").write_text(bad)
    src = tmp_path / "src"
    src.mkdir()
    (src / "ok.py").write_text("x = 1\n")
    (src / "out.py").symlink_to(far / "far.py")
    monkeypatch.chdir(tmp_path)
    assert main(["src", "--baseline", "none.json"]) == 0
    assert "skipped 1 symlinked file(s)" in capsys.readouterr().out
    (src / "out.py").unlink()
    (src / "inside.py").write_text(bad)
    assert main(["src", "--baseline", "none.json"]) == 1
    assert "src/inside.py" in capsys.readouterr().out


# ── R24-27..29: every file the walk does not judge is named ─────────────────
#
# A byte-order mark, a NUL byte, or syntax newer than the interpreter made
# the file unparsable and the lint returned no findings for it - clean.
# Each case below runs through main() from inside the tree, as CI runs it.

_R27_BAD = "def f(s):\n    try:\n        return s.read()\n    except Exception:\n        pass\n"


def _r27(tmp_path, monkeypatch, capsys, files: dict) -> tuple:
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        p = src / name
        if isinstance(body, bytes):
            p.write_bytes(body)
        else:
            p.write_text(body)
    monkeypatch.chdir(tmp_path)
    code = __import__("sutradhar_guards.swallow_lint", fromlist=["main"]).main(["src", "--baseline", "none.json"])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_r27_a_bom_prefixed_defect_is_found_as_the_plain_one_is(
        tmp_path, monkeypatch, capsys):
    """The pair: the BOM twin's finding is the plain twin's finding.

    Mutation (the line that runs, in read_source): `encoding="utf-8-sig"`
    -> `encoding="utf-8"` - the BOM file is NOT JUDGED, exit 2, red.
    """
    code, out, _ = _r27(tmp_path / "a", monkeypatch, capsys,
                        {"m.py": b"\xef\xbb\xbf" + _R27_BAD.encode()})
    assert code == 1, out
    assert "src/m.py:4" in out, out
    code, out, _ = _r27(tmp_path / "b", monkeypatch, capsys, {"m.py": _R27_BAD})
    assert code == 1 and "src/m.py:4" in out, out


@pytest.mark.parametrize("body", [b"def (:\n", b"x = 'a\x00b'\n"],
                         ids=["syntax-error", "nul-byte"])
def test_r27_an_unparsable_file_is_named_and_exits_two(
        tmp_path, monkeypatch, capsys, body):
    """Mutation (the line that runs, in _parse): `raise NotJudged(...)` ->
    `return ast.parse("")` (an empty tree: the old `return []`) - exit 0,
    red.
    """
    code, out, err = _r27(tmp_path, monkeypatch, capsys,
                          {"bad.py": body, "ok.py": "x = 1\n"})
    assert code == 2, out + err
    assert "NOT JUDGED" in out and "src/bad.py: does not parse" in out, out
    assert "could not judge 1 file(s) (src/bad.py)" in err, err


def test_r27_an_unparsable_file_beside_a_finding_is_exit_one_and_still_named(
        tmp_path, monkeypatch, capsys):
    """A finding outranks a file not judged: under the Action's skip a 2 is
    a pass, so the unparsable neighbour would have hidden the finding.

    Mutation (the line that runs, in _verdict): `return 1 if found else 2
    if unjudged else 0` -> `return 2 if unjudged else 1 if found else 0` -
    exit 2, red.
    """
    code, out, _ = _r27(tmp_path, monkeypatch, capsys,
                        {"bad.py": b"def (:\n", "real.py": _R27_BAD})
    assert code == 1, out
    assert "src/m.py:4".replace("m.py", "real.py") in out, out
    assert "src/bad.py: does not parse" in out, out


def test_r28_a_directory_named_like_a_module_is_not_read(
        tmp_path, monkeypatch, capsys):
    """rglob yielded a directory named `fixtures.py`, read_text raised
    IsADirectoryError, and the guard crashed. Now it is a directory.

    Mutation: none on a single line - the walk (os.walk) never lists a
    directory among files; the regression it pins is a return to rglob.
    """
    (tmp_path / "src" / "fixtures.py").mkdir(parents=True)
    code, out, err = _r27(tmp_path, monkeypatch, capsys, {"ok.py": "x = 1\n"})
    assert code == 0, out + err


def test_r28_a_symlink_loop_is_named_not_a_crash(tmp_path, monkeypatch, capsys):
    """Mutation (the line that runs, in _walk): `target =
    f.resolve(strict=True)` -> `target = f.resolve()` - a loop resolves to
    itself on this Python or raises; either way it is no longer named, red.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "loop.py").symlink_to("loop.py")
    code, out, err = _r27(tmp_path, monkeypatch, capsys, {"ok.py": "x = 1\n"})
    assert code == 2, out + err
    assert "src/loop.py: is a symlink that does not resolve" in out, out


def test_r29_a_symlinked_directory_is_said_not_silent(
        tmp_path, monkeypatch, capsys):
    """Mutation (the line that runs, in _walk): `linked_dirs.append(p)` ->
    `pass` - nothing said, red.
    """
    far = tmp_path / "far"
    far.mkdir()
    (far / "m.py").write_text(_R27_BAD)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "linked").symlink_to(far)
    code, out, _ = _r27(tmp_path, monkeypatch, capsys, {"ok.py": "x = 1\n"})
    assert code == 0, out
    assert "did not descend 1 symlinked director(ies): src/linked" in out, out


def test_r28_a_fifo_named_like_a_module_is_named_not_read(tmp_path):
    """A FIFO named `pipe.py` is listed among a directory's files, and
    reading it blocks forever: the guard would hang the job. Run in a
    subprocess so a regression is a timeout, not a hung suite.

    Mutation (the line that runs, in _walk): `elif not f.is_file():` ->
    `elif False:` - the read blocks, TimeoutExpired, red.
    """
    import os
    import subprocess
    src = tmp_path / "src"
    src.mkdir()
    (src / "ok.py").write_text("x = 1\n")
    os.mkfifo(src / "pipe.py")
    guard = Path(__file__).resolve().parents[1] / "sutradhar_guards" / "swallow_lint.py"
    r = subprocess.run([sys.executable, str(guard), *["src", "--baseline", "none.json"]], cwd=tmp_path,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "src/pipe.py: is not a regular file" in r.stdout, r.stdout


def test_r27_update_baseline_is_refused_over_an_unjudged_file(tmp_path,
                                                             monkeypatch,
                                                             capsys):
    """A floor recorded without a file it could not read would re-flag that
    file's swallows as new the day it parses. Refused: exit 2, the baseline
    bytes untouched, the file named. Pair: the same walk with nothing
    unjudged writes the floor.

    Mutation (the line that runs, in main): `if update and unjudged:` ->
    `if False and unjudged:` - the floor is written over the partial walk,
    red.
    """
    from sutradhar_guards.swallow_lint import main
    src = tmp_path / "src"
    src.mkdir()
    (src / "real.py").write_text(_R27_BAD)
    (src / "bad.py").write_bytes(b"def (:\n")
    base = tmp_path / "b.json"
    base.write_text('{"old": 1}\n')
    monkeypatch.chdir(tmp_path)
    assert main(["src", "--update-baseline", "--baseline", "b.json"]) == 2
    out = capsys.readouterr()
    assert base.read_bytes() == b'{"old": 1}\n'
    assert "src/bad.py: does not parse" in out.out, out.out
    assert "baseline NOT written" in out.err, out.err
    (src / "bad.py").unlink()
    assert main(["src", "--update-baseline", "--baseline", "b.json"]) == 0
    assert json.loads(base.read_text()) == {"src/real.py": 1}
