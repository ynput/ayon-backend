from typing import Any

from ayon_server.logging import logger

from .common import attrib_errors, get_model_set


def valid_attrib(
    entity_type: str,
    values: dict[str, Any] | None,
    label: str,
) -> dict[str, Any]:
    """Return the stored attribute values, which are valid.

    Attributes without a definition are dropped. Invalid values are dropped
    and logged (the fix-attributes command fixes them in the database).
    Values are returned as they are, not converted.

    `label` identifies the values in the log (e.g. "folder <id> in <project>").
    """
    if not values:
        return {}
    model_set = get_model_set(entity_type)
    if model_set is None:
        return dict(values)

    model = model_set.attrib_model
    defined = model.__pydantic_fields__
    result = {key: value for key, value in values.items() if key in defined}
    for key, message in attrib_errors(model, result).items():
        logger.debug(
            f"Ignoring invalid attribute {key}={str(result[key])[:70]} of {label}: "
            f"{message}. Run fix-attributes to fix the stored value."
        )
        del result[key]
    return result
