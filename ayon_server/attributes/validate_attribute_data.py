from pydantic import Field, create_model

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
    for k in (
        "gt",
        "ge",
        "lt",
        "le",
        "min_length",
        "max_length",
        "regex",
        "min_items",
        "max_items",
    ):
        if getattr(fdef, k):
            field[k] = getattr(fdef, k)

    ftype = FIELD_TYPES[fdef.type]

    try:
        _ = create_model("test", test=(ftype, Field(**field)))  # type: ignore
    except ValueError as e:
        log_traceback(f"Unable to construct attribute '{name}'")
        raise BadRequestException(
            f"Unable to construct attribute '{name}' Check the logs for more details."
        ) from e
