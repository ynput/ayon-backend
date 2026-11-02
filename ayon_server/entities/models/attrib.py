"""Attribute validation of the entity models.

Attributes are configured at runtime, so the entity models type their
`attrib` field as a plain `AttribDict`. The values are validated using
the attribute model of the entity type, which is generated from the current
attribute definitions (and regenerated when they change).
"""

import contextlib
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from ayon_server.entities.core.attrib import attribute_library
from ayon_server.entities.models.generator import generate_model
from ayon_server.models.attrib_values import STORED_VALUES, AttribDict
from ayon_server.utils import as_utc

AttribModelConfig = ConfigDict(coerce_numbers_to_str=True)

# {entity type: (attribute library revision, attribute model)}
_attrib_models: dict[str, tuple[int, type[BaseModel]]] = {}


def get_attrib_model(entity_type: str) -> type[BaseModel]:
    """Return the attribute model of the entity type.

    The model is generated from the current attribute definitions and
    regenerated when the attribute library is reloaded. It is used for
    every validation of attribute values, so it should stay cheap.
    """
    revision = attribute_library.revision
    cached = _attrib_models.get(entity_type)
    if cached is None or cached[0] != revision:
        model = generate_model(
            f"{entity_type.capitalize()}AttribModel",
            attribute_library[entity_type],
            AttribModelConfig,
        )
        cached = _attrib_models[entity_type] = (revision, model)
    return cached[1]


def validate_attrib(entity_type: str, value: Any, context: Any = None) -> Any:
    """Validate attribute values of an entity.

    Returns the given attributes converted to their types. Attributes without
    a definition are dropped. Values loaded from the database (see
    `STORED_VALUES`) are not validated again, only datetimes (stored as ISO
    strings) are converted, so entities provide the same types as when
    they are created. Datetimes are timezone-aware (naive ones are UTC).

    Raises pydantic ValidationError when a value is not valid.
    """
    if isinstance(value, BaseModel):
        value = value.model_dump(exclude_unset=True)
    if not isinstance(value, dict):
        return value  # rejected by the field type
    if isinstance(context, dict) and context.get(STORED_VALUES):
        values = AttribDict(value)
        for name in values.keys() & attribute_library.datetime_attributes:
            if isinstance(values[name], str):
                with contextlib.suppress(ValueError):  # keep invalid values
                    values[name] = as_utc(datetime.fromisoformat(values[name]))
        return values

    model = get_attrib_model(entity_type)
    # Attribute models are flat, so the validated values can be used
    # directly (faster than model_dump)
    validated = model.__pydantic_validator__.validate_python(value).__dict__
    result = AttribDict({key: validated[key] for key in value if key in validated})
    for name in result.keys() & attribute_library.datetime_attributes:
        if isinstance(result[name], datetime):
            result[name] = as_utc(result[name])
    return result
