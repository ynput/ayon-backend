from typing import Any

from .common import attrib_errors, get_model_set


def invalid_attrib(entity_type: str, values: dict[str, Any]) -> dict[str, str]:
    """Return {attribute name: error message} of invalid attribute values.

    Values are checked against the current attribute definitions of the
    entity type. Attributes without a definition are not reported (they
    are ignored by the attribute models). This, together with
    `valid_attrib`, decides whether a stored value is valid.
    """
    model_set = get_model_set(entity_type)
    if model_set is None or not values:
        return {}
    return attrib_errors(model_set.attrib_model, values)
