from ayon_server.entity_search.search import (
    MAX_TERMS,
    build_search_cte,
    like_pattern,
    parse_query,
    prefix_lexeme,
    sql_string,
    sql_string_array,
)


def test_like_pattern_escapes_wildcards():
    assert like_pattern("comp") == "%comp%"
    assert like_pattern("sh010_comp") == r"%sh010\_comp%"
    assert like_pattern(r"100%\x") == r"%100\%\\x%"


def test_prefix_lexeme_is_quoted():
    assert prefix_lexeme("render") == "'render':*"
    assert prefix_lexeme("it's") == "'it''s':*"
    assert prefix_lexeme("a & !b") == "'a & !b':*"


def test_sql_string_escapes_quotes():
    assert sql_string("it's") == "'it''s'"
    assert sql_string("a\\b") == "'a\\b'"  # standard_conforming_strings
    assert sql_string("a\x00b") == "'ab'"
    assert sql_string_array(["a", "b'c"]) == "ARRAY['a', 'b''c']::text[]"


def test_parse_query():
    assert parse_query("sh010,sh020") == [["sh010"], ["sh020"]]
    assert parse_query("robot v002, sloth") == [["robot", "v002"], ["sloth"]]
    assert parse_query("bob's") == [["bob"]]
    assert parse_query("sh:*") == [["sh"]]
    assert parse_query("e , ,") == []
    assert parse_query("sh010_comp a/b.exr") == [["sh010_comp", "a/b.exr"]]
    assert sum(map(len, parse_query("a1 b2 c3 d4, e5 f6 g7 h8 i9"))) == MAX_TERMS


def test_groups_stay_inside_access_filters():
    cte = build_search_cte("p", "aa, bb", folder_access=["x%"])
    assert cte
    where = cte.split("WHERE", 1)[1]
    assert where.strip().startswith("((") and ") OR (" in where
