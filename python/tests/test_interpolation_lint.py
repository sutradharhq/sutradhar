import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.interpolation_lint import (
    KEYWORD_PRESETS,
    check_source,
    selfcheck,
)

SQL = KEYWORD_PRESETS["sql"]
SPARQL = KEYWORD_PRESETS["sparql"]


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
