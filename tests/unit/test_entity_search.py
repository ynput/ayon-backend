from ayon_server.entity_search.search import like_pattern, prefix_lexeme


def test_like_pattern_escapes_wildcards():
    assert like_pattern("comp") == "%comp%"
    assert like_pattern("sh010_comp") == r"%sh010\_comp%"
    assert like_pattern(r"100%\x") == r"%100\%\\x%"


def test_prefix_lexeme_is_quoted():
    assert prefix_lexeme("render") == "'render':*"
    assert prefix_lexeme("it's") == "'it''s':*"
    assert prefix_lexeme("a & !b") == "'a & !b':*"
