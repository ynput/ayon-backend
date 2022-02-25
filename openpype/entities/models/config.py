"""Entity model config."""

from openpype.utils import json_loads, json_dumps


def camelize(src: str) -> str:
    """Convert snake_case to camelCase."""
    components = src.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


class EntityModelConfig:
    """Entity model config."""

    allow_population_by_field_name = True
    alias_generator = camelize
    json_loads = json_loads
    json_dumps = json_dumps
