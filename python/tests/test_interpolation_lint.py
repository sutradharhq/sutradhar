import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.interpolation_lint import (
    KEYWORD_PRESETS,
    check_source,
    main,
    selfcheck,
)

SQL = KEYWORD_PRESETS["sql"]
SPARQL = KEYWORD_PRESETS["sparql"]


# ── an empty scan is not a pass (R21-2) ──────────────────────────────────────

def test_a_directory_with_no_python_is_refused_and_named(tmp_path, capsys):
    """`OK (0 files checked)` and exit 0 was a green injection check over a
    tree nobody read. Exit 2 is this toolkit's "the check could not run"."""
    (tmp_path / "README.md").write_text("docs only\n")
    rc = main([str(tmp_path), "--keywords", "sql"])
    said = capsys.readouterr()
    assert rc == 2, said
    assert "nothing was scanned" in said.err and str(tmp_path) in said.err
    assert "OK" not in said.out + said.err


def test_no_argument_and_no_src_names_the_default_it_assumed(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main([]) == 2
    err = capsys.readouterr().err
    assert "src (does not exist)" in err and "src/ was assumed" in err


def test_flags_bare_name_in_quoted_position():
    src = 'q = f\'SELECT * FROM t WHERE name = "{user_name}"\'\n'
    hits = check_source(src, SQL)
    assert len(hits) == 1
    assert hits[0][1] == "user_name"


def test_flags_attribute_in_quoted_position():
    src = 'q = f\'SELECT * FROM t WHERE name = "{req.name}"\'\n'
    assert len(check_source(src, SQL)) == 1


def test_escaped_call_at_site_is_clean():
    src = 'q = f\'SELECT * FROM t WHERE name = "{escape_literal(user_name)}"\'\n'
    assert check_source(src, SQL) == []


def test_custom_safe_call_is_clean():
    src = 'q = f\'SELECT * FROM t WHERE name = "{my_esc(user_name)}"\'\n'
    assert check_source(src, SQL, safe_calls={"my_esc"}) == []


def test_unquoted_position_ignored_by_default_flagged_in_strict():
    src = "q = f'SELECT * FROM t LIMIT {page_size}'\n"
    assert check_source(src, SQL) == []
    assert len(check_source(src, SQL, strict=True)) == 1


def test_numeric_suffix_heuristic_is_clean_even_in_quotes():
    src = 'q = f\'SELECT * FROM t WHERE n = "{row_count}"\'\n'
    assert check_source(src, SQL) == []


def test_int_cast_is_clean():
    src = 'q = f\'SELECT * FROM t WHERE n = "{int(page)}"\'\n'
    assert check_source(src, SQL) == []


def test_allowlist_name_is_clean():
    src = 'q = f\'SELECT * FROM t WHERE k = "{cursor_iso}"\'\n'
    assert len(check_source(src, SQL)) == 1
    assert check_source(src, SQL, allowlist={"cursor_iso"}) == []


def test_non_query_fstring_is_ignored():
    src = 'msg = f\'hello "{user_name}", welcome back\'\n'
    assert check_source(src, SQL) == []


def test_triple_quoted_sparql_block():
    src = (
        "q = f'''\n"
        "SELECT ?s WHERE {{\n"
        '  ?s es:tenant "{tenant}" .\n'
        "}}\n"
        "'''\n"
    )
    hits = check_source(src, SPARQL)
    assert len(hits) == 1
    assert hits[0][1] == "tenant"


def test_selfcheck_passes():
    assert selfcheck()


# ── the two older spellings (B-20, R16-5) ───────────────────────────────────
#
# `"... = '%s'" % name` was the SAME hole as the f-string two lines above it
# and passed clean for sixteen rounds, because the detector knew one dialect
# of the class and looked like it knew the class. The negative cases below
# carry as much weight as the positive ones: a lint that flags every `%` in
# a codebase is switched off in a week, and every hole it could have caught
# leaves with it (the B-2 scar, on a different guard).

def test_flags_percent_format_in_a_quoted_position():
    src = "q = \"SELECT * FROM t WHERE name = '%s'\" % user_name\n"
    hits = check_source(src, SQL)
    assert len(hits) == 1
    assert hits[0][1] == "user_name", "the report must name the argument"


def test_flags_str_format_in_a_quoted_position():
    src = "q = \"SELECT * FROM t WHERE name = '{}'\".format(user_name)\n"
    hits = check_source(src, SQL)
    assert len(hits) == 1
    assert hits[0][1] == "user_name"


def test_percent_with_a_tuple_names_the_right_argument():
    src = ("q = \"SELECT * FROM t WHERE a = '%s' AND b = '%s'\" "
           "% (first, second)\n")
    hits = check_source(src, SQL)
    assert [h[1] for h in hits] == ["first", "second"]


def test_a_literal_percent_does_not_shift_the_positional_arguments():
    """`%%` consumes no argument. Counting it would name the wrong variable
    in the report, and a finding that names the wrong thing sends the reader
    to the wrong line with total confidence (6.9)."""
    src = ("q = \"SELECT '%d%% of rows' FROM t WHERE name = '%s'\" "
           "% (share_pct, user_name)\n")
    hits = check_source(src, SQL)
    assert [h[1] for h in hits] == ["user_name"]


def test_percent_with_a_mapping_resolves_the_key():
    src = ("q = \"SELECT * FROM t WHERE name = '%(who)s'\" "
           "% {'who': user_name}\n")
    hits = check_source(src, SQL)
    assert len(hits) == 1 and hits[0][1] == "user_name"


def test_str_format_named_and_numbered_fields():
    named = "q = \"SELECT * FROM t WHERE n = '{who}'\".format(who=user_name)\n"
    assert [h[1] for h in check_source(named, SQL)] == ["user_name"]
    numbered = "q = \"SELECT * FROM t WHERE n = '{0}'\".format(user_name)\n"
    assert [h[1] for h in check_source(numbered, SQL)] == ["user_name"]


def test_str_format_attribute_and_index_fields_resolve_to_their_root():
    src = "q = \"SELECT * FROM t WHERE n = '{r.name}'\".format(r=req)\n"
    assert [h[1] for h in check_source(src, SQL)] == ["req"]


# ── the false-positive surface ──────────────────────────────────────────────

def test_percent_on_a_string_with_no_query_keyword_is_clean():
    assert check_source('msg = "%d%% done" % pct\n', SQL) == []
    assert check_source("msg = \"hello, '%s'\" % user_name\n", SQL) == []


def test_format_on_a_string_with_no_query_keyword_is_clean():
    assert check_source("msg = \"hi '{}'\".format(user_name)\n", SQL) == []


def test_a_format_call_on_something_that_is_not_a_literal_is_not_read():
    """A documented limitation, pinned so it stays a decision rather than a
    surprise: there is no string here to read query keywords out of."""
    assert check_source("q = QUERY.format(user_name)\n", SQL) == []
    assert check_source("q = QUERY % user_name\n", SQL) == []


def test_escaping_at_the_site_is_clean_in_both_spellings():
    pct = "q = \"SELECT * FROM t WHERE n = '%s'\" % escape_literal(name)\n"
    fmt = "q = \"SELECT * FROM t WHERE n = '{}'\".format(sql_quote(name))\n"
    assert check_source(pct, SQL) == []
    assert check_source(fmt, SQL) == []


def test_a_custom_safe_call_is_honoured_in_both_spellings():
    pct = "q = \"SELECT * FROM t WHERE n = '%s'\" % my_esc(name)\n"
    fmt = "q = \"SELECT * FROM t WHERE n = '{}'\".format(my_esc(name))\n"
    assert check_source(pct, SQL, safe_calls={"my_esc"}) == []
    assert check_source(fmt, SQL, safe_calls={"my_esc"}) == []


def test_the_numeric_suffix_and_allowlist_heuristics_apply_too():
    counted = "q = \"SELECT * FROM t WHERE n = '%s'\" % row_count\n"
    assert check_source(counted, SQL) == []
    vouched = "q = \"SELECT * FROM t WHERE k = '{}'\".format(cursor_iso)\n"
    assert len(check_source(vouched, SQL)) == 1
    assert check_source(vouched, SQL, allowlist={"cursor_iso"}) == []


def test_an_unquoted_position_is_ignored_by_default_in_both_spellings():
    pct = 'q = "SELECT * FROM t LIMIT %d" % page\n'
    fmt = 'q = "SELECT * FROM t LIMIT {}".format(page)\n'
    assert check_source(pct, SQL) == []
    assert check_source(fmt, SQL) == []
    assert len(check_source(pct, SQL, strict=True)) == 1
    assert len(check_source(fmt, SQL, strict=True)) == 1


def test_arguments_that_cannot_be_matched_are_judged_on_all_of_them():
    """"Cannot tell" must not resolve to "clean" - that is the shape 2.9 is
    about, in a detector rather than in a report."""
    unresolvable = "q = \"SELECT * FROM t WHERE n = '%s'\" % params\n"
    assert len(check_source(unresolvable, SQL)) == 1
    all_safe = ("q = \"SELECT * FROM t WHERE a = '{a}' AND b = '{b}'\""
                ".format(a=escape_literal(x), b=escape_literal(y))\n")
    assert check_source(all_safe, SQL) == []


def test_a_sparql_block_built_with_format_is_seen():
    src = (
        "q = '''\n"
        "SELECT ?s WHERE {{\n"
        "  ?s es:tenant \"{tenant}\" .\n"
        "}}\n"
        "'''.format(tenant=tenant)\n"
    )
    hits = check_source(src, SPARQL)
    assert len(hits) == 1 and hits[0][1] == "tenant"


def test_a_file_and_a_symlink_to_it_report_once(tmp_path, monkeypatch, capsys):
    """R24-23: the same interpolation reached through a link and its target
    was reported twice. One file, one finding; still exit 1.

    Mutation: `if target in seen: continue` -> `if False: continue` in
    _read_once - two report lines, red.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text(
        "def q(x):\n    return f\"SELECT * FROM t WHERE a = '{x}'\"\n")
    (src / "link.py").symlink_to("a.py")
    monkeypatch.chdir(tmp_path)
    assert main(["src"]) == 1
    out = capsys.readouterr().out
    assert "1 query interpolation risk(s)" in out, out
    assert "src/a.py:2" in out and "link.py" not in out, out


def test_a_symlink_out_of_the_scanned_paths_is_skipped_and_said(
        tmp_path, monkeypatch, capsys):
    """R24-23's outside-root rule, pinned here as well as in
    conflated_degrade_lint: a link to an interpolated query outside every
    scanned directory is skipped and the count printed; the same file
    inside the scanned root is still reported (the pair).

    Mutation (the line that runs, in _read_once): `if is_link and not
    any(...)` -> `if False and not any(...)` - the far query is read
    through the link and fails the clean tree, red.
    """
    bad = "def q(x):\n    return f\"SELECT * FROM t WHERE a = '{x}'\"\n"
    far = tmp_path / "elsewhere"
    far.mkdir()
    (far / "far.py").write_text(bad)
    src = tmp_path / "src"
    src.mkdir()
    (src / "ok.py").write_text("x = 1\n")
    (src / "out.py").symlink_to(far / "far.py")
    monkeypatch.chdir(tmp_path)
    assert main(["src"]) == 0
    assert "skipped 1 symlinked file(s)" in capsys.readouterr().out
    (src / "out.py").unlink()
    (src / "inside.py").write_text(bad)
    assert main(["src"]) == 1
    assert "src/inside.py:2" in capsys.readouterr().out


# ── R24-27..29: every file the walk does not judge is named ─────────────────
#
# A byte-order mark, a NUL byte, or syntax newer than the interpreter made
# the file unparsable and the lint returned no findings for it - clean.
# Each case below runs through main() from inside the tree, as CI runs it.

_R27_BAD = "def q(x):\n    return f\"SELECT * FROM t WHERE a = '{x}'\"\n"


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
    code = main(["src"])
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
    assert "src/m.py:2" in out, out
    code, out, _ = _r27(tmp_path / "b", monkeypatch, capsys, {"m.py": _R27_BAD})
    assert code == 1 and "src/m.py:2" in out, out


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
    assert "src/m.py:2".replace("m.py", "real.py") in out, out
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
    guard = Path(__file__).resolve().parents[1] / "sutradhar_guards" / "interpolation_lint.py"
    r = subprocess.run([sys.executable, str(guard), *["src"]], cwd=tmp_path,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "src/pipe.py: is not a regular file" in r.stdout, r.stdout
