from ayon_server.entity_search.search import (
    like_pattern,
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
