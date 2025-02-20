import string
from typing import Literal, overload

import unidecode

default_slug_whitelist = string.ascii_letters + string.digits
slug_separator_whitelist = " ,./\\;:!|*^#@~+-_="


def indent(text: str, length: int = 4) -> str:
    """Indent a multi-line text."""
    return (
        "\n".join([f"{length*' '}{s.rstrip()}" for s in text.split("\n")]) + "\n"
        if text.endswith("\n")
        else ""
    )


@overload
def slugify(
    input_string: str,
    *,
    separator: str = "-",
    lower: bool = True,
    make_set: Literal[False] = False,
    min_length: int = 1,
    slug_whitelist: str = default_slug_whitelist,
    split_chars: str = slug_separator_whitelist,
) -> str: ...


@overload
def slugify(
    input_string: str,
    *,
    separator: str = "-",
    lower: bool = True,
    make_set: Literal[True] = True,
    min_length: int = 1,
    slug_whitelist: str = default_slug_whitelist,
    split_chars: str = slug_separator_whitelist,
) -> set[str]: ...


def slugify(
    input_string: str,
    *,
    separator: str = "-",
    lower: bool = True,
    make_set: bool = False,
    min_length: int = 1,
    slug_whitelist: str = default_slug_whitelist,
    split_chars: str = slug_separator_whitelist,
) -> str | set[str]:
    """Slugify a text string.

    This function removes transliterates input string to ASCII,
    removes special characters and use join resulting elements
    using specified separator.

    Args:
        input_string (str):
            Input string to slugify

        separator (str):
            A string used to separate returned elements (default: "-")

        lower (bool):
            Convert to lower-case (default: True)

        make_set (bool):
            Return "set" object instead of string

        min_length (int):
            Minimal length of an element (word)

        slug_whitelist (str):
            Characters allowed in the output
            (default: ascii letters, digits and the separator)

        split_chars (str):
            Set of characters used for word splitting (there is a sane default)

    """
    input_string = unidecode.unidecode(input_string)
    if lower:
        input_string = input_string.lower()
    input_string = "".join(
        [ch if ch not in split_chars else " " for ch in input_string]
    )
    input_string = "".join(
        [ch if ch in slug_whitelist + " " else "" for ch in input_string]
    )
    elements = [
        elm.strip() for elm in input_string.split(" ") if len(elm.strip()) >= min_length
    ]
    return set(elements) if make_set else separator.join(elements)
