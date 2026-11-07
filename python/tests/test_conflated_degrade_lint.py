# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Tests for the conflated-degrade guard (R18-2).

`swallow_lint` catches an `except` that logs nothing. This catches the half
it structurally cannot see: the handler logs, and returns the same value a
legitimate "there is nothing here" path returns, so the caller cannot tell
them apart and every number downstream is computed over an unknown fraction
of reality under a green status.

The load-bearing cases here are the REFUSALS - the fixed shape passes, a
re-raise passes, and a same-named sibling does not steal the first one's
banked key - because a detector that flags everything is removed from CI
within a week and protects nothing after.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards import conflated_degrade_lint as cdl  # noqa: E402

CONFLATED = '''
def read_state(keys):
    if not keys:
        return {}
    try:
        return fetch(keys)
    except Exception as exc:
        log.warning("read failed: %s", exc)
        return {}
'''

DISTINGUISHABLE = '''
def read_state(keys):
    if not keys:
        return {}, True
    try:
        return fetch(keys), True
    except Exception as exc:
        log.warning("read failed: %s", exc)
        return {}, False
'''


# ── the detector discriminates ──────────────────────────────────────────────

def test_it_flags_the_conflation():
    found = cdl.find_conflated_degrades(CONFLATED, "a.py")
    assert [f.key for f in found] == ["a.py::read_state"]
    assert found[0].line == 2


def test_the_distinguishable_version_passes():
    """The point of the guard is not to ban the fail-safe value. `(value, ok)`
    keeps the same `{}` and adds the one bit the caller was missing."""
    assert cdl.find_conflated_degrades(DISTINGUISHABLE, "a.py") == []


def test_a_handler_that_reraises_is_ignored():
    src = '''
def read_state(keys):
    if not keys:
        return {}
    try:
        return fetch(keys)
    except Exception:
        raise
'''
    assert cdl.find_conflated_degrades(src, "a.py") == []


def test_a_handler_whose_value_no_normal_path_returns_is_ignored():
    """`{}` on failure and a real value otherwise is not a conflation - the
    caller can already tell. Flagging it would make the guard noise."""
    src = '''
def read_state(keys):
    try:
        return fetch(keys)
    except Exception:
        return {}
'''
    assert cdl.find_conflated_degrades(src, "a.py") == []


def test_different_falsy_values_do_not_conflate():
    """`{}` from the handler and `None` from the empty path ARE
    distinguishable, so the tags must not be collapsed into "falsy"."""
    src = '''
def read_state(keys):
    if not keys:
        return None
    try:
        return fetch(keys)
    except Exception:
        return {}
'''
    assert cdl.find_conflated_degrades(src, "a.py") == []


def test_a_method_carries_its_class_in_the_key():
    src = '''
class Store:
    def read(self):
        if not self.k:
            return []
        try:
            return fetch(self.k)
        except Exception:
            return []
'''
    assert [f.key for f in cdl.find_conflated_degrades(src, "a.py")] == [
        "a.py::Store.read"
    ]


def test_a_nested_def_carries_its_enclosing_function():
    src = '''
def outer():
    def inner(k):
        if not k:
            return 0
        try:
            return fetch(k)
        except Exception:
            return 0
    return inner
'''
    keys = [f.key for f in cdl.find_conflated_degrades(src, "a.py")]
    assert "a.py::outer.inner" in keys


def test_a_syntax_error_is_not_judged_rather_than_clean():
    """R24-27: this test pinned `[]` - the clean answer - for a file that
    does not parse, which is the false green itself."""
    with pytest.raises(cdl.NotJudged):
        cdl.find_conflated_degrades("def (:\n", "a.py")


# ── the key is an identity, not a position (R18-1) ──────────────────────────

def test_the_key_holds_no_line_number():
    found = cdl.find_conflated_degrades(CONFLATED, "a.py")
    assert ":2" not in found[0].key and found[0].key == "a.py::read_state"
    # ...and the line still reaches the reader.
    assert "a.py:2" in found[0].message


def test_lines_inserted_above_do_not_change_the_key():
    flat = cdl.find_conflated_degrades(CONFLATED, "a.py")
    shifted = cdl.find_conflated_degrades("# moved\n" * 7 + CONFLATED, "a.py")
    assert shifted[0].line != flat[0].line, "the fixture did not move"
    assert {f.key for f in shifted} == {f.key for f in flat}
    # Through the real seam: nothing new, nothing stale.
    new, fixed = cdl.compare(shifted, {f.key for f in flat})
    assert new == [] and fixed == []


def test_a_same_named_sibling_does_not_steal_the_first_key():
    """Adding a second `read` must leave the first one's banked entry alone:
    the set gains a member and loses none."""
    one = cdl.find_conflated_degrades(CONFLATED, "a.py")
    two = cdl.find_conflated_degrades(CONFLATED * 2, "a.py")
    assert [f.key for f in two] == ["a.py::read_state", "a.py::read_state#2"]
    assert {f.key for f in one} < {f.key for f in two}


def test_same_named_methods_on_different_classes_key_apart():
    src = '''
class A:
    def read(self):
        if not self.k:
            return {}
        try:
            return fetch(self.k)
        except Exception:
            return {}

class B:
    def read(self):
        if not self.k:
            return {}
        try:
            return fetch(self.k)
        except Exception:
            return {}
'''
    assert [f.key for f in cdl.find_conflated_degrades(src, "a.py")] == [
        "a.py::A.read", "a.py::B.read"
    ]


# ── the ratchet ─────────────────────────────────────────────────────────────

def test_compare_reports_a_new_conflation_and_a_separated_one():
    banked = {f.key for f in cdl.find_conflated_degrades(CONFLATED, "a.py")}
    two = cdl.find_conflated_degrades(CONFLATED + '''
def other_read(k):
    if not k:
        return None
    try:
        return fetch(k)
    except Exception:
        return None
''', "a.py")
    new, fixed = cdl.compare(two, banked)
    assert [f.key for f in new] == ["a.py::other_read"] and fixed == []

    # The guard-the-guard half: a banked entry that is no longer a finding
    # must be reported, or the floor silently stops meaning anything.
    new, fixed = cdl.compare(
        cdl.find_conflated_degrades(DISTINGUISHABLE, "a.py"), banked
    )
    assert new == [] and fixed == ["a.py::read_state"]


# ── the CLI, through the seam an adopter actually runs ──────────────────────

def _tree(tmp_path, body=CONFLATED, name="app.py"):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / name).write_text(body)
    return src


def test_the_cli_gates_records_and_holds(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = _tree(tmp_path)
    base = tmp_path / "b.json"

    assert cdl.main([str(src), "--baseline", str(base)]) == 1      # unbanked
    assert cdl.main([str(src), "--baseline", str(base),
                     "--update-baseline"]) == 0
    assert json.loads(base.read_text()) == ["src/app.py::read_state"]
    assert cdl.main([str(src), "--baseline", str(base)]) == 0      # at floor

    # An edit above the finding must not re-flag it. This is R18-1 asserted
    # end to end, on the guard that was ported with the fix.
    (src / "app.py").write_text('"""Added."""\nimport os\n' + CONFLATED)
    assert cdl.main([str(src), "--baseline", str(base)]) == 0


def test_the_cli_fails_when_a_banked_entry_is_fixed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = _tree(tmp_path)
    base = tmp_path / "b.json"
    cdl.main([str(src), "--baseline", str(base), "--update-baseline"])
    (src / "app.py").write_text(DISTINGUISHABLE)
    assert cdl.main([str(src), "--baseline", str(base)]) == 1


def test_an_unknown_flag_is_refused_with_two(tmp_path):
    assert cdl.main([str(tmp_path), "--selfchek"]) == 2


def test_no_path_is_refused_rather_than_assumed(tmp_path, capsys):
    """A default directory nobody named would report OK over a tree nothing
    read - the exact class of lie this guard exists to catch (2.4)."""
    assert cdl.main(["--baseline", str(tmp_path / "b.json")]) == 2
    assert "nothing was scanned" in capsys.readouterr().err


def test_a_named_directory_with_no_python_is_refused_too(tmp_path, capsys):
    """R21-2. The guard refused the default directory nobody named and then
    printed `OK (0 file(s), ...)` for a named one that held nothing - the
    same lie, one argument later."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "README.md").write_text("docs only\n")
    base = tmp_path / "b.json"
    rc = cdl.main([str(src), "--baseline", str(base)])
    said = capsys.readouterr()
    assert rc == 2, said
    assert "nothing was scanned" in said.err and str(src) in said.err
    assert "OK" not in said.out + said.err


def test_a_floor_is_not_recorded_over_nothing(tmp_path):
    base = tmp_path / "b.json"
    assert cdl.main([str(tmp_path), "--baseline", str(base),
                     "--update-baseline"]) == 2
    assert not base.exists()


def test_a_tree_holding_only_vendor_files_says_how_to_scan_them(tmp_path, capsys):
    vendor = tmp_path / ".venv" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "dep.py").write_text(CONFLATED)
    assert cdl.main([str(tmp_path), "--baseline", str(tmp_path / "b.json")]) == 2
    assert "--include-vendor" in capsys.readouterr().err


def test_a_blinded_detector_fails_the_cli(tmp_path, monkeypatch):
    """The wiring test: the path from "the detector went vacuous" to "CI goes
    red" is itself under test. A clean tree is green; the same clean tree
    with the detector blinded must go red, because the embedded selfcheck no
    longer finds its planted bad case."""
    monkeypatch.chdir(tmp_path)
    clean = _tree(tmp_path, body="x = 1\n")
    base = tmp_path / "b.json"
    assert cdl.main([str(clean), "--baseline", str(base)]) == 0
    monkeypatch.setattr(cdl, "find_conflated_degrades", lambda *a, **k: [])
    assert cdl.main([str(clean), "--baseline", str(base)]) == 1


def test_the_walk_skips_vendor_trees_and_says_so(tmp_path, monkeypatch, capsys):
    """B-2: ~80 third-party findings once buried the one real one and the
    guard was switched off that afternoon."""
    monkeypatch.chdir(tmp_path)
    src = _tree(tmp_path)
    vendor = src / ".venv" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "dep.py").write_text(CONFLATED)
    assert cdl.main([str(src), "--baseline", str(tmp_path / "b.json"),
                     "--update-baseline"]) == 0
    out = capsys.readouterr().out
    assert "skipped 1 file(s) under vendor" in out
    assert json.loads((tmp_path / "b.json").read_text()) == [
        "src/app.py::read_state"
    ]


def test_an_explicitly_named_vendor_path_is_still_scanned(tmp_path, monkeypatch):
    """Pointing the guard at a vendor tree on purpose must not print OK over
    a directory nothing read."""
    monkeypatch.chdir(tmp_path)
    vendor = tmp_path / ".venv" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "dep.py").write_text(CONFLATED)
    assert cdl.main([str(vendor), "--baseline", str(tmp_path / "b.json")]) == 1


def test_the_selfcheck_passes():
    assert cdl.selfcheck()


def test_the_selfcheck_names_what_it_exercised(capsys):
    """6.7: a silent exit 0 cannot be told from a check that never ran."""
    cdl.selfcheck()
    out = capsys.readouterr().out
    assert "conflated-degrade-lint" in out
    for claim in ("conflation caught", "re-raise passed", "keyed apart"):
        assert claim in out, out


@pytest.mark.parametrize("name,vacuous", [
    ("conflates", lambda *a, **k: False),
    ("functions_with_qualnames", lambda *a, **k: []),
])
def test_a_blinded_internal_reddens_the_selfcheck(monkeypatch, name, vacuous):
    """Mutation, committed: neither half of the detector may go vacuous
    without the selfcheck saying so."""
    monkeypatch.setattr(cdl, name, vacuous)
    assert not cdl.selfcheck()


# ── R24-23: a file reached twice through a symlink is read once ─────────────
#
# Keys resolve symlinks, so a link to a file holding a conflation produced
# the same key twice: "INSTRUMENT ERROR: duplicate key(s)", exit 2, and under
# the Action's `on-cannot-run: skip` a pass. Run from inside the tree, as the
# Action runs, because that is where the keys collide.

_CONFLATED = (
    "def read(store):\n"
    "    try:\n"
    "        return store.get()\n"
    "    except KeyError:\n"
    "        print('failed')\n"
    "        return {}\n"
    "    if not store:\n"
    "        return {}\n"
    "    return store.get()\n"
)


def _linked_tree(root: Path) -> Path:
    src = root / "src"
    src.mkdir()
    (src / "reader.py").write_text(_CONFLATED)
    (src / "link.py").symlink_to("reader.py")
    return src


def test_a_symlink_to_a_conflated_file_is_a_finding_not_could_not_run(
        tmp_path, monkeypatch, capsys):
    """The pair: the link and its target are one file, so the conflation is
    one finding at exit 1, the same verdict as the tree without the link.

    Mutation (the line that runs, in _read_once): `if target in seen:
    continue` -> `if False: continue` - duplicate key, exit 2, red.
    """
    _linked_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert cdl.main(["src", "--baseline", "none.json"]) == 1
    out = capsys.readouterr()
    assert "duplicate key" not in out.err, out.err
    assert out.out.count("src/reader.py:") == 1, out.out
    (tmp_path / "src" / "link.py").unlink()
    assert cdl.main(["src", "--baseline", "none.json"]) == 1


def test_a_symlink_out_of_the_scanned_paths_is_skipped_and_said(
        tmp_path, monkeypatch, capsys):
    """Skipped and counted, not followed: the scanned paths are the adopter's
    statement of what their source is. The target named directly is still
    read and still found (the pair).

    Mutation (the line that runs, in _read_once): `if is_link and not
    any(...)` -> `if False` - the far file is read through the link and its
    conflation fails the clean tree, red.
    """
    far = tmp_path / "elsewhere"
    far.mkdir()
    (far / "far.py").write_text(_CONFLATED)
    src = tmp_path / "src"
    src.mkdir()
    (src / "ok.py").write_text("x = 1\n")
    (src / "out.py").symlink_to(far / "far.py")
    monkeypatch.chdir(tmp_path)
    assert cdl.main(["src", "--baseline", "none.json"]) == 0
    assert "skipped 1 symlinked file(s)" in capsys.readouterr().out
    assert cdl.main(["elsewhere", "--baseline", "none.json"]) == 1


# ── R24-27..29: every file the walk does not judge is named ─────────────────
#
# A byte-order mark, a NUL byte, or syntax newer than the interpreter made
# the file unparsable and the lint returned no findings for it - clean.
# Each case below runs through main() from inside the tree, as CI runs it.

_R27_BAD = _CONFLATED


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
    code = cdl.main(["src", "--baseline", "none.json"])
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
    assert "src/m.py:1 read" in out, out
    code, out, _ = _r27(tmp_path / "b", monkeypatch, capsys, {"m.py": _R27_BAD})
    assert code == 1 and "src/m.py:1 read" in out, out


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
    assert "src/m.py:1 read".replace("m.py", "real.py") in out, out
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
    guard = Path(__file__).resolve().parents[1] / "sutradhar_guards" / "conflated_degrade_lint.py"
    r = subprocess.run([sys.executable, str(guard), *["src", "--baseline", "none.json"]], cwd=tmp_path,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "src/pipe.py: is not a regular file" in r.stdout, r.stdout


def test_r27_update_baseline_is_refused_over_an_unjudged_file(tmp_path,
                                                             monkeypatch,
                                                             capsys):
    """Refused: exit 2, the baseline bytes untouched, the file named. Pair:
    the same walk with nothing unjudged writes the floor.

    Mutation (the line that runs, in main): `if update and unjudged:` ->
    `if False and unjudged:` - the floor is written over the partial walk,
    red.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "m.py").write_text(_CONFLATED)
    (src / "bad.py").write_bytes(b"def (:\n")
    base = tmp_path / "b.json"
    base.write_text('["old::x"]\n')
    monkeypatch.chdir(tmp_path)
    assert cdl.main(["src", "--update-baseline", "--baseline", "b.json"]) == 2
    out = capsys.readouterr()
    assert base.read_bytes() == b'["old::x"]\n'
    assert "src/bad.py: does not parse" in out.out, out.out
    assert "baseline NOT written" in out.err, out.err
    (src / "bad.py").unlink()
    assert cdl.main(["src", "--update-baseline", "--baseline", "b.json"]) == 0
    assert json.loads(base.read_text()) == ["src/m.py::read"]


def test_r27_a_banked_entry_in_an_unjudged_file_is_not_called_fixed(
        tmp_path, monkeypatch, capsys):
    """Nobody may be told to delete a floor entry for a file that was never
    read: the banked conflation in an unparsable file stays banked, and the
    run is 2 (not judged), not 1 ("now distinguishable"). Pair: the same
    banked entry in a file that parses and no longer conflates IS stale.

    Mutation (the line that runs, in main): `fixed = [k for k in fixed if
    k.split("::", 1)[0] not in not_judged]` -> `fixed = [k for k in fixed
    if True]` - exit 1 with the entry reported fixed, red.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "m.py").write_bytes(b"def (:\n")
    (tmp_path / "b.json").write_text('["src/m.py::read"]\n')
    monkeypatch.chdir(tmp_path)
    assert cdl.main(["src", "--baseline", "b.json"]) == 2
    out = capsys.readouterr().out
    assert "now distinguishable" not in out, out
    assert "src/m.py: does not parse" in out, out
    (src / "m.py").write_text("def read(store):\n    return store.get()\n")
    assert cdl.main(["src", "--baseline", "b.json"]) == 1
    out = capsys.readouterr().out
    assert "now distinguishable" in out and "src/m.py::read" in out, out
