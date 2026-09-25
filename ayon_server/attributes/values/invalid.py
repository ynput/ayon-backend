from typing import Any

from pydantic import ValidationError

from .common import get_model_set


def invalid_attrib(entity_type: str, values: dict[str, Any]) -> dict[str, str]:
    """Return {attribute name: error message} of invalid attribute values.

    Values are checked against the current attribute definitions of the
    entity type. Attributes without a definition are not reported (they
    are ignored when the values are read). Missing values of required
    attributes are not reported either.
    """
    model_set = get_model_set(entity_type)
    if model_set is None or not values:
        return {}
    try:
        model_set.attrib_model.__pydantic_validator__.validate_python(values)
    except ValidationError as e:
        return {
            str(error["loc"][0]): error["msg"]
            for error in e.errors()
            if error["loc"] and str(error["loc"][0]) in values
        }
    return {}
