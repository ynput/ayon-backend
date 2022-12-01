from typing import Any, Iterable

from nxtools import slugify

from openpype.exceptions import BadRequestException


def normalize_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise BadRequestException("Name must not be empty")
    components = slugify(name).split("-")
    return f"{components[0]}{''.join(x.title() for x in components[1:])}"


def ensure_unique_names(objects: Iterable[Any]) -> None:
    """Ensure a list of objects have unique 'name' property.

    In settings, we use lists instead of dictionaries (for various reasons).
    'name' property is considered the primary key for the items.
    """
    names = []
    for obj in objects:
        if not hasattr(obj, "name"):
            raise BadRequestException("Object without name provided")
        if obj.name not in names:
            names.append(obj.name)
        else:
            raise BadRequestException(f"Duplicate name **{obj.name}**")
