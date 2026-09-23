"""Entity model config."""

from pydantic import ConfigDict


def camelize(src: str) -> str:
    """Convert snake_case to camelCase."""
    components = src.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


EntityModelConfig = ConfigDict(
    validate_by_name=True,
    validate_by_alias=True,
    alias_generator=camelize,
    # Pydantic 1 accepted numbers for string fields
    coerce_numbers_to_str=True,
)
