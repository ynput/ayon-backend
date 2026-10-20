from pydantic import PydanticUserError, ValidationError
from pydantic_core import SchemaError

from ayon_server.attributes.models import AttributeData
from ayon_server.entities.models import AttribModelConfig
from ayon_server.entities.models.generator import (
    FieldDefinition,
    attribute_field,
    attribute_test_model,
)
from ayon_server.exceptions import BadRequestException
from ayon_server.logging import log_traceback


def validate_attribute_data(name: str, fdef: AttributeData) -> None:
    """Validate attribute data.

    Ensure that constraints defined in the attribute data are valid
    by attempting to create a Pydantic model from the attribute data,
    the same way the attribute models are created (generate_model).

    Pydantic model creation may fail when for example
    `gt` is used along with `max_length`. The validation logic is however
    deep inside the Pydantic library, and it's not always straightforward to
    understand why a particular combination of constraints is invalid.

    Ayon could end in a crash loop in the case of invalid attribute data,
    so this is a safety measure to prevent such crashes.

    Raises BadRequestException if the attribute data is invalid.
    """

    if not name.isidentifier():
        raise BadRequestException(f"Attribute name '{name}' is not a valid identifier.")

    definition = FieldDefinition(name=name, **fdef.model_dump())
    ftype, field = attribute_field(definition)

    try:
        model = attribute_test_model(definition, ftype, field, AttribModelConfig)
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
    except (ValueError, TypeError, PydanticUserError) as e:
        log_traceback(f"Unable to construct attribute '{name}'")
        raise BadRequestException(f"Unable to construct attribute '{name}': {e}") from e

    # Defaults are used when a value is not set, so they must be valid
    if fdef.default is not None:
        try:
            model(**{name: fdef.default})
        except ValidationError as e:
            raise BadRequestException(
                f"Default value of attribute '{name}' is not valid: "
                f"{e.errors()[0]['msg']}"
            ) from e
