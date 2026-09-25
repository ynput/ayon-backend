from typing import Any

from ayon_server.logging import logger

from .common import get_model_set, validate_values


def valid_attrib(
    entity_type: str,
    values: dict[str, Any] | None,
    label: str,
    *,
    raw: bool = False,
) -> dict[str, Any]:
    """Return the valid stored attribute values.

    Attributes without a definition are dropped. Invalid values are dropped
    and logged (the fix-attributes command fixes them in the database).

    Values are converted to the attribute types (e.g. datetimes), the same
    way REST and GraphQL return them. With `raw`, they are returned as they
    are stored (e.g. to store them again).

    `label` identifies the values in the log (e.g. "folder <id> in <project>").
    """
    if not values:
        return {}
    model_set = get_model_set(entity_type)
    if model_set is None:
        return dict(values)

    model = model_set.attrib_model
    defined = model.__pydantic_fields__
    stored = {key: value for key, value in values.items() if key in defined}
    validated, errors = validate_values(model, stored)
    for key, message in errors.items():
        logger.debug(
            f"Ignoring invalid attribute {key}={str(stored[key])[:70]} of {label}: "
            f"{message}. Run fix-attributes to fix the stored value."
        )
    if raw:
        return {key: value for key, value in stored.items() if key not in errors}
    return validated
