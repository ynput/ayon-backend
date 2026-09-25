from typing import Any

from ayon_server.models.attrib_values import AttribDict

from .common import get_model_set


def validate_attrib(
    entity_type: str,
    values: dict[str, Any],
    *,
    partial: bool = False,
) -> AttribDict:
    """Validate attribute values strictly (used when they are written).

    With `partial`, only the given attributes are validated and returned.
    Otherwise, the result contains all attributes (missing ones are None
    or defaults). Attributes without a definition are dropped.

    Raises pydantic ValidationError when a value is not valid.
    """
    model_set = get_model_set(entity_type)
    if model_set is None:
        raise ValueError(f"Unknown entity type: {entity_type}")
    return model_set.validate_attrib(values, partial=partial)
