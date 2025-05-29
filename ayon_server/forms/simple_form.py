from typing import Any, Literal, NotRequired, TypedDict

from pydantic import StrictBool, StrictFloat, StrictInt, StrictStr

SimpleFormFieldType = Literal[
    "text",
    "boolean",
    "select",
    "multiselect",
    "hidden",
    "integer",
    "float",
    "label",
]

SimpleFormHighlightType = Literal[
    "info",
    "warning",
    "error",
]


class FormSelectOption(TypedDict):
    value: str
    label: str
    icon: NotRequired[str]
    color: NotRequired[str]
    badges: NotRequired[list[str]]


ValueType = (
    StrictStr
    | StrictInt
    | StrictFloat
    | StrictBool
    | list[StrictStr]
    | list[StrictInt]
    | list[StrictFloat]
)


class SimpleFormField(TypedDict):
    type: SimpleFormFieldType
    name: str
    label: NotRequired[str]
    placeholder: NotRequired[Any]
    value: NotRequired[ValueType]
    regex: NotRequired[str]
    multiline: NotRequired[bool]
    syntax: NotRequired[str]
    options: NotRequired[list[FormSelectOption]]
    highlight: NotRequired[SimpleFormHighlightType]
    min: NotRequired[int | float]
    max: NotRequired[int | float]


def normalize_options(
    options: list[str] | list[FormSelectOption],
) -> list[FormSelectOption]:
    """Normalize options to a list of dictionaries."""
    if not options:
        return []

    result: list[FormSelectOption] = []
    for option in options:
        if isinstance(option, str):
            result.append({"value": option, "label": option})
        elif isinstance(option, dict):
            if "value" not in option or "label" not in option:
                raise ValueError("Option must contain 'value' and 'label' keys.")
            result.append({"value": option["value"], "label": option["label"]})
            if "icon" in option:
                result[-1]["icon"] = option["icon"]
            if "color" in option:
                result[-1]["color"] = option["color"]
            if "badges" in option:
                if not isinstance(option["badges"], list):
                    raise ValueError("Badges must be a list.")
                result[-1]["badges"] = option["badges"]
        else:
            raise ValueError("Option must be a string or a dictionary.")

    return result


class SimpleForm(list[SimpleFormField]):
    def __init__(self):
        super().__init__()

    def label(
        self,
        text: str,
        *,
        highlight: Literal["info", "warning", "error"] | None = None,
    ) -> "SimpleForm":
        """Add a label to the form.

        Label is non-interactive and is used to display information to the user.
        It can be used to group fields or to display information about the form.
        """
        field: SimpleFormField = {
            "type": "label",
            "name": f"label-{len(self)}",
            "value": text,
        }
        if highlight:
            field["highlight"] = highlight
        self.append(field)
        return self

    def text(
        self,
        name: str,
        label: str | None = None,
        value: str | None = None,
        *,
        placeholder: str | None = None,
        regex: str | None = None,
        multiline: bool = False,
        syntax: str | None = None,
    ) -> "SimpleForm":
        """Add a text input field to the form.

        The text input field is used to get a string value from the user.
        It can be used to get a single line of text or a multiline text.

        The `regex` parameter can be used to validate the input.
        the `placeholder` parameter can be used to display a hint to the user.
        The `syntax` parameter can be used to highlight the input.
        Syntax highlighting is available only for multiline text inputs.
        """
        field: SimpleFormField = {"type": "text", "name": name}
        if label is not None:
            field["label"] = label
        if placeholder is not None:
            field["placeholder"] = placeholder
        if value is not None:
            field["value"] = value
        if regex is not None:
            field["regex"] = regex
        if multiline:
            field["multiline"] = multiline
        if syntax is not None:
            field["syntax"] = syntax
        self.append(field)
        return self

    def boolean(
        self,
        name: str,
        label: str | None = None,
        value: bool = False,
    ) -> "SimpleForm":
        """Add a checkbox or switch field to the form."""
        field: SimpleFormField = {
            "type": "boolean",
            "name": name,
            "value": value,
        }
        if label is not None:
            field["label"] = label
        self.append(field)
        return self

    def select(
        self,
        name: str,
        options: list[str] | list[FormSelectOption],
        label: str | None = None,
        value: str | None = None,
    ) -> "SimpleForm":
        """Add a select field (dropdown) to the form.

        The select field is used to get a single value from the user.
        Option must be provided either as a list of strings or as a
        list of {"value": "value", "label": "label"} dictionaries.
        """
        field: SimpleFormField = {
            "type": "select",
            "name": name,
            "options": normalize_options(options),
        }
        if label is not None:
            field["label"] = label
        if value is not None:
            field["value"] = value
        self.append(field)
        return self

    def multiselect(
        self,
        name: str,
        options: list[str] | list[FormSelectOption],
        label: str | None = None,
        value: list[str] | None = None,
    ) -> "SimpleForm":
        """Add a multiselect field (dropdown) to the form.

        The multiselect field is used to get multiple values from the user.
        Option must be provided either as a list of strings or as a
        list of {"value": "value", "label": "label"} dictionaries.

        Value must be provided as a list of strings.
        """
        field: SimpleFormField = {
            "type": "multiselect",
            "name": name,
            "options": normalize_options(options),
        }
        if label is not None:
            field["label"] = label
        if value is not None:
            field["value"] = value
        self.append(field)
        return self

    def hidden(
        self,
        name: str,
        value: Any = None,
    ) -> "SimpleForm":
        """Add a hidden field to the form.

        Hidden fields are used to keep an arbitrary value in the context
        of the form. They are not displayed to the user and are not
        interactive.
        """
        field: SimpleFormField = {
            "type": "hidden",
            "name": name,
        }
        if value is not None:
            field["value"] = value
        self.append(field)
        return self

    def integer(
        self,
        name: str,
        label: str | None = None,
        value: int | None = None,
        *,
        placeholder: str | None = None,
        min: int | None = None,
        max: int | None = None,
    ) -> "SimpleForm":
        """Add an integer input field to the form.

        The integer input field is used to get an integer value from the user.
        It can be used to get a single line of text or a multiline text.

        The `placeholder` parameter can be used to display a hint to the user.
        """
        field: SimpleFormField = {
            "type": "integer",
            "name": name,
        }
        if label is not None:
            field["label"] = label
        if placeholder is not None:
            field["placeholder"] = placeholder
        if value is not None:
            field["value"] = value
        if min is not None:
            field["min"] = min
        if max is not None:
            field["max"] = max
        self.append(field)
        return self

    def float(
        self,
        name: str,
        label: str | None = None,
        value: float | None = None,
        *,
        placeholder: str | None = None,
        min: float | None = None,
        max: float | None = None,
    ) -> "SimpleForm":
        """Add a float input field to the form.

        The float input field is used to get a float value from the user.
        It can be used to get a single line of text or a multiline text.

        The `placeholder` parameter can be used to display a hint to the user.
        """
        field: SimpleFormField = {
            "type": "float",
            "name": name,
        }
        if label is not None:
            field["label"] = label
        if placeholder is not None:
            field["placeholder"] = placeholder
        if value is not None:
            field["value"] = value
        if min is not None:
            field["min"] = min
        if max is not None:
            field["max"] = max
        self.append(field)
        return self
