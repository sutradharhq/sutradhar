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
