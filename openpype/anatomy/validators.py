from typing import Any, Iterable

from nxtools import slugify


def normalize_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("Name must not be empty")
    components = slugify(name).split("-")
    return components[0] + "".join(x.title() for x in components[1:])


def ensure_unique_names(objects: Iterable[Any]) -> None:
    names = []
    for obj in objects:
        if not hasattr(obj, "name"):
            raise ValueError("Object without name provided")
        if obj.name not in names:
            names.append(obj.name)
        else:
            raise ValueError(f"Duplicate name {obj.name}]")
