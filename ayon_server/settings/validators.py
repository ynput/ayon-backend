import re
from collections.abc import Iterable
from typing import Any

import unidecode

from ayon_server.exceptions import BadRequestException


def normalize_name(
    name: str,
    allowed_chars: str | None = None,
    replacement: str | None = None,
    escape_unicode: bool = True,
    strip: bool = True,
) -> str:
    """Normalize string value.

    Args:
        name (str): Source value from user/default settings.
        allowed_chars (Optional[str]): String with allowed characters.
            Pass '.' or '*' to allow any characters. Default 'a-zA-Z0-9-_ '.
            Regex special characters must be escaped to make them work. e.g.
            to allow dash ('-') an escaped '\\-' must be passed.
        replacement (Optional[str]): Replacement of characters that do not match
            allowed characters. By default, is used empty string ''.
        escape_unicode (Optional[bool]): Escape unicode characters from string.
            Default 'True'.
        strip (Optional[bool]): String is stripped so there are not any
            trailing white characters.

    Returns:
        str: Normalized name.

    Raises:
        BadRequestException: Result is an empty string.
    """

    if allowed_chars is None:
        allowed_chars = "a-zA-Z0-9-_ "

    if replacement is None:
        replacement = ""

    if strip:
        name = name.strip()

    if escape_unicode:
        name = unidecode.unidecode(name)

    if allowed_chars not in ("*", "."):
        allower_chars_regex = f"[^{allowed_chars}]"
        name = re.sub(allower_chars_regex, replacement, name)

    if not name:
        raise BadRequestException("Name must not be empty")
    return name


def ensure_unique_names(objects: Iterable[Any], field_name: str | None = None) -> None:
    """Ensure a list of objects have unique 'name' property.

    In settings, we use lists instead of dictionaries (for various reasons).
    'name' property is considered the primary key for the items.
    """
    suf = ""
    if field_name:
        suf = f" in '{field_name}'"
    names = []
    for obj in objects:
        if not hasattr(obj, "name"):
            raise BadRequestException(f"Object without name provided{suf}")
        if obj.name not in names:
            names.append(obj.name)
        else:
            raise BadRequestException(f"Duplicate name '{obj.name}'{suf}")
