from typing import Any, Literal, NotRequired, TypedDict

SimpleFormFieldType = Literal["text", "checkbox", "label"]
SimpleFormHighlightType = Literal["info", "warning", "error"]


class SimpleFormField(TypedDict):
    type: SimpleFormFieldType
    name: str
    label: NotRequired[str]
    placeholder: NotRequired[Any]
    default: NotRequired[str]
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
        default: str | None = None,
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
            default=default,
            regex=regex,
            required=required,
            multiline=multiline,
        )

    def checkbox(
        self,
        name: str,
        label: str | None = None,
        default: bool = False,
    ) -> "SimpleForm":
        return self.add_field(
            type="checkbox",
            name=name,
            label=label,
            default=default,
        )

    # TODO: other field types
