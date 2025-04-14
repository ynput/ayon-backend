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
        required: bool = False,
        multiline: bool = False,
    ) -> "SimpleForm":
        return self.add_field(
            type="text",
            name=name,
            label=label,
            placeholder=placeholder,
            value=value,
            regex=regex,
            required=required,
            multiline=multiline,
        )

    def checkbox(
        self,
        name: str,
        label: str | None = None,
        value: bool = False,
    ) -> "SimpleForm":
        return self.add_field(
            type="checkbox",
            name=name,
            label=label,
            value=value,
        )

    def select(
        self,
        name: str,
        label: str | None = None,
        value: str | None = None,
        options: list[str] | None = None,
    ) -> "SimpleForm":
        return self.add_field(
            type="select",
            name=name,
            label=label,
            value=value,
            options=options,
        )

    def hidden(
        self,
        name: str,
        value: str | None = None,
    ) -> "SimpleForm":
        return self.add_field(
            type="hidden",
            name=name,
            value=value,
        )

    # TODO: other field types
