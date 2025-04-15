from typing import Any, Literal, NotRequired, TypedDict

SimpleFormFieldType = Literal["text", "checkbox", "label"]
SimpleFormHighlightType = Literal["info", "warning", "error"]


class SimpleFormField(TypedDict):
    type: SimpleFormFieldType
    name: str
    label: NotRequired[str]
    placeholder: NotRequired[Any]
    value: NotRequired[str]
    regex: NotRequired[str]
    required: NotRequired[bool]
    multiline: NotRequired[bool]
    highlight: NotRequired[SimpleFormHighlightType]


class FormSelectOption(TypedDict):
    value: str
    label: str
    icon: NotRequired[str]
    color: NotRequired[str]


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
        else:
            raise ValueError("Option must be a string or a dictionary.")

    return result


class SimpleForm(list[SimpleFormField]):
    def __init__(self):
        super().__init__()

    def add_field(self, **kwargs) -> "SimpleForm":
        """Add a field to the form."""
        self.append({k: v for k, v in kwargs.items() if v is not None})  # type: ignore
        return self

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
        return self.add_field(
            type="label",
            name=f"label-{len(self)}",
            text=text,
            highlight=highlight,
        )

    def text_input(
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
        return self.add_field(
            type="text",
            name=name,
            label=label,
            placeholder=placeholder,
            value=value,
            regex=regex,
            multiline=multiline,
            syntax=syntax,
        )

    def boolean(
        self,
        name: str,
        label: str | None = None,
        value: bool = False,
    ) -> "SimpleForm":
        """Add a checkbox or switch field to the form."""
        return self.add_field(
            type="boolean",
            name=name,
            label=label,
            value=value,
        )

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
        return self.add_field(
            type="select",
            name=name,
            label=label,
            value=value,
            options=normalize_options(options),
        )

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
        return self.add_field(
            type="multiselect",
            name=name,
            label=label,
            value=value,
            options=normalize_options(options),
        )

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
        return self.add_field(
            type="hidden",
            name=name,
            value=value,
        )

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
        return self.add_field(
            type="integer",
            name=name,
            label=label,
            placeholder=placeholder,
            value=value,
            min=min,
            max=max,
        )

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
        return self.add_field(
            type="float",
            name=name,
            label=label,
            placeholder=placeholder,
            value=value,
            min=min,
            max=max,
        )
