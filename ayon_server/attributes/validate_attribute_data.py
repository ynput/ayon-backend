from pydantic import Field, create_model
from pydantic_core import SchemaError

from ayon_server.attributes.models import AttributeData
from ayon_server.entities.models.generator import FIELD_TYPES
from ayon_server.exceptions import BadRequestException
from ayon_server.logging import log_traceback


def validate_attribute_data(name: str, fdef: AttributeData) -> None:
    """Validate attribute data.

    Ensure that constraints defined in the attribute data are valid
    by attempting to create a Pydantic model from the attribute data.

    Pydantic model creation may fail when for example
    `gt` is used along with `max_length`. The validation logic is however
    deep inside the Pydantic library, and it's not always straightforward to
    understand why a particular combination of constraints is invalid.

    Ayon could end in a crash loop in the case of invalid attribute data,
    so this is a safety measure to prevent such crashes.

    This function will raise a ValueError if the attribute data is invalid.
    """

    if not name.isidentifier():
        raise BadRequestException(f"Attribute name '{name}' is not a valid identifier.")

    field = {}
    for k in ("gt", "ge", "lt", "le", "min_length", "max_length"):
        # 0 is a valid limit
        if getattr(fdef, k) is not None:
            field[k] = getattr(fdef, k)

    # Pydantic 2 names of the Pydantic 1 validators
    if fdef.regex:
        field["pattern"] = fdef.regex
    if fdef.min_items is not None:
        field["min_length"] = fdef.min_items
    if fdef.max_items is not None:
        field["max_length"] = fdef.max_items

    ftype = FIELD_TYPES[fdef.type]

    try:
        _ = create_model("test", test=(ftype, Field(**field)))
    except SchemaError as e:
        if "pattern" not in field:
            log_traceback(f"Unable to construct attribute '{name}'")
            raise BadRequestException(
                f"Unable to construct attribute '{name}'. "
                "Check the logs for more details."
            ) from e
        raise BadRequestException(
            f"Regex of attribute '{name}' is not supported. "
            "Look-around and backreferences cannot be used."
        ) from e
    except ValueError as e:
        log_traceback(f"Unable to construct attribute '{name}'")
        raise BadRequestException(
            f"Unable to construct attribute '{name}' Check the logs for more details."
        ) from e
