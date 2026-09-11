import re
from base64 import b64encode
from typing import Any, Literal, NotRequired, Self, TypedDict

from pydantic import StrictBool, StrictFloat, StrictInt, StrictStr

# EnumItem is only accepted here as convenience input (e.g. passing through
# an item a resolver already produced) - options are coalesced down into the
# leaner FormOptionItem below rather than stored as full EnumItem, so a
# static option list isn't forced to carry a fixed 9-key envelope
# (disabled, fulltext, ...) for every entry. Imported from ayon_server.models
# (rather than ayon_server.enum, its usual home) because ayon_server.enum
# depends on ayon_server.forms, and importing it from there would cycle.
from ayon_server.models.enum_item import EnumItem
from ayon_server.models.icon_model import IconModel
from ayon_server.sqlfilter import QueryFilter
from ayon_server.types import SimpleValue

SimpleFormFieldType = Literal[
    "text",
    "boolean",
    "select",
    "multiselect",
    "hidden",
    "integer",
    "float",
    "label",
    "file",
]

SimpleFormHighlightType = Literal[
    "info",
    "warning",
    "error",
]


class FormOptionItem(TypedDict):
    """A single `select`/`multiselect` option.

    Mirrors (a subset of) `EnumItem`'s fields - same names, camelCase to
    match the rest of this file - but is a plain TypedDict so an option
    only carries the keys it actually sets; `value` is the only required
    one. `normalize_options()` builds this from a string, a dict already
    in this shape, or a full `EnumItem` (e.g. one handed back by a
    resolver) - it does not keep the input as-is.

    `icon` accepts either a material-symbol name (`str`) or an `IconModel`
    (`{"type": "url", "url": "..."}`) for image/URL-based icons - a plain
    dict in that shape works too and is passed through as-is.
    """

    value: SimpleValue
    label: NotRequired[str]
    description: NotRequired[str]
    group: NotRequired[str]
    icon: NotRequired[str | IconModel]
    color: NotRequired[str]
    shortName: NotRequired[str]
    disabled: NotRequired[bool]
    disabledMessage: NotRequired[str]
    hidden: NotRequired[bool]
    badges: NotRequired[list[str]]


# Alias kept for backwards compatibility - this TypedDict used to be called
# FormSelectOption.
FormSelectOption = FormOptionItem


class FormFileData(TypedDict):
    filename: str
    payload: str  # base64 encoded
    download: NotRequired[bool]


ValueType = (
    StrictStr
    | StrictInt
    | StrictFloat
    | StrictBool
    | list[StrictStr]
    | list[StrictInt]
    | list[StrictFloat]
    | FormFileData
)


class FormFieldPatch(TypedDict, total=False):
    """Properties a :class:`FormFieldRule` may override on a field.

    Kept separate from `SimpleFormField` (rather than reusing it wholesale)
    because a rule must never be able to change a field's `type`/`name`, or
    attach further `rules`/`enumResolverParams` to it - that would reopen
    the reference cycles the "earlier fields only" restriction exists to
    prevent.
    """

    value: ValueType | None
    label: str
    placeholder: Any
    options: list[FormOptionItem]
    readOnly: bool
    disabled: bool
    hidden: bool
    highlight: SimpleFormHighlightType


class FormFieldRule(TypedDict):
    """A single conditional rule attached to a field.

    `when` uses the same condition model as `ayon_server.sqlfilter`
    (`QueryCondition`/`QueryFilter`), evaluated by the frontend against the
    current values of earlier fields in the same form rather than against
    SQL rows. When it matches, `set` is applied on top of the field's
    static definition.
    """

    when: QueryFilter
    set: FormFieldPatch


_TEMPLATE_VAR_PATTERN = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")

_PATCH_KEYS = frozenset(FormFieldPatch.__annotations__)


def _template_vars(value: Any) -> set[str]:
    """Collect `{{fieldName}}` references out of a (possibly nested) value."""
    if isinstance(value, str):
        return set(_TEMPLATE_VAR_PATTERN.findall(value))
    if isinstance(value, (dict, list, tuple)):
        items = value.values() if isinstance(value, dict) else value
        result: set[str] = set()
        for v in items:
            result |= _template_vars(v)
        return result
    return set()


def _condition_field_names(f: QueryFilter) -> set[str]:
    """Collect field names referenced by a rule's `when` filter.

    Unlike sqlfilter's own `filter_columns`, the key is not split or
    snake_cased: a condition's `key` here is the literal `name` of another
    field in the same form, which may itself legitimately contain dots
    (e.g. `attrib.fps`).
    """
    result: set[str] = set()
    for condition in f.conditions:
        if isinstance(condition, QueryFilter):
            result |= _condition_field_names(condition)
        else:
            result.add(condition.key)
    return result


_OPTION_KEYS = frozenset(FormOptionItem.__annotations__)


def _option_from_enum_item(item: EnumItem) -> FormOptionItem:
    """Coalesce an EnumItem down to only the keys it actually sets."""
    option: FormOptionItem = {"value": item.value}
    if item.label and item.label != str(item.value):
        option["label"] = item.label
    if item.description:
        option["description"] = item.description
    if item.group:
        option["group"] = item.group
    if item.icon is not None:
        option["icon"] = item.icon
    if item.color:
        option["color"] = item.color
    if item.short_name:
        option["shortName"] = item.short_name
    if item.disabled:
        option["disabled"] = item.disabled
    if item.disabled_message:
        option["disabledMessage"] = item.disabled_message
    if item.hidden:
        option["hidden"] = item.hidden
    if item.badges:
        option["badges"] = item.badges
    return option


def normalize_options(
    options: list[str] | list[FormOptionItem] | list[EnumItem],
) -> list[FormOptionItem]:
    """Normalize options to a list of (sparse) FormOptionItem."""
    if not options:
        return []

    result: list[FormOptionItem] = []
    for option in options:
        if isinstance(option, str):
            result.append({"value": option})
        elif isinstance(option, EnumItem):
            result.append(_option_from_enum_item(option))
        elif isinstance(option, dict):
            if "value" not in option:
                raise ValueError("Option must contain a 'value' key.")
            unknown_keys = set(option) - _OPTION_KEYS
            if unknown_keys:
                raise ValueError(f"Unsupported option key(s): {sorted(unknown_keys)}")
            result.append(dict(option))  # type: ignore[arg-type]
        else:
            raise ValueError("Option must be a string, a dict or an EnumItem.")

    return result


class SimpleFormField(TypedDict):
    type: SimpleFormFieldType
    name: str
    label: NotRequired[str]
    placeholder: NotRequired[Any]
    value: NotRequired[ValueType]
    regex: NotRequired[str]
    multiline: NotRequired[bool]
    syntax: NotRequired[str]
    options: NotRequired[list[FormOptionItem]]
    highlight: NotRequired[SimpleFormHighlightType]
    min: NotRequired[int | float]
    max: NotRequired[int | float]
    valid_extensions: NotRequired[list[str]]
    readOnly: NotRequired[bool]
    disabled: NotRequired[bool]
    hidden: NotRequired[bool]
    enumResolver: NotRequired[str]
    enumResolverParams: NotRequired[dict[str, Any]]
    rules: NotRequired[list[FormFieldRule]]


class SimpleForm(list[SimpleFormField]):
    def __init__(self) -> None:
        super().__init__()

    @property
    def _known_names(self) -> set[str]:
        return {field["name"] for field in self}

    def _check_forward_refs(self, name: str, referenced: set[str]) -> None:
        """Ensure `referenced` field names were all added before `name`.

        Rules and templates may only look at fields that already exist
        earlier in the form - this is what keeps evaluation acyclic on
        the frontend (a single left-to-right pass, no dependency graph).
        """
        if not referenced:
            return
        if name in referenced:
            raise ValueError(f"Field '{name}' cannot reference itself.")
        unknown = referenced - self._known_names
        if unknown:
            raise ValueError(
                f"Field '{name}' references unknown or not-yet-defined "
                f"field(s) {sorted(unknown)}. Rules and templates may only "
                "reference fields added earlier in the same form."
            )

    def _validate_rules(
        self,
        name: str,
        rules: list[FormFieldRule],
    ) -> list[FormFieldRule]:
        normalized: list[FormFieldRule] = []
        referenced: set[str] = set()

        for rule in rules:
            when = rule["when"]
            if not isinstance(when, QueryFilter):
                when = QueryFilter.parse_obj(when)

            patch = rule["set"]
            unknown_patch_keys = set(patch) - _PATCH_KEYS
            if unknown_patch_keys:
                raise ValueError(
                    f"Field '{name}' has a rule with unsupported 'set' "
                    f"key(s): {sorted(unknown_patch_keys)}"
                )

            referenced |= _condition_field_names(when)
            normalized.append({"when": when, "set": patch})

        self._check_forward_refs(name, referenced)
        return normalized

    def _add_field(
        self,
        type_: SimpleFormFieldType,
        name: str,
        *,
        rules: list[FormFieldRule] | None = None,
        enumResolverParams: dict[str, Any] | None = None,
        **props: Any,
    ) -> Self:
        field: SimpleFormField = {"type": type_, "name": name}
        for key, value in props.items():
            if value is not None:
                field[key] = value  # type: ignore[literal-required]

        if enumResolverParams is not None:
            self._check_forward_refs(name, _template_vars(enumResolverParams))
            field["enumResolverParams"] = enumResolverParams

        if rules:
            field["rules"] = self._validate_rules(name, rules)

        self.append(field)
        return self

    def label(
        self,
        text: str,
        *,
        highlight: Literal["info", "warning", "error"] | None = None,
        rules: list[FormFieldRule] | None = None,
    ) -> Self:
        """Add a label to the form.

        Label is non-interactive and is used to display information to the user.
        It can be used to group fields or to display information about the form.
        """
        return self._add_field(
            "label",
            f"label-{len(self)}",
            value=text,
            highlight=highlight,
            rules=rules,
        )

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
        rules: list[FormFieldRule] | None = None,
    ) -> Self:
        """Add a text input field to the form.

        The text input field is used to get a string value from the user.
        It can be used to get a single line of text or a multiline text.

        The `regex` parameter can be used to validate the input.
        the `placeholder` parameter can be used to display a hint to the user.
        The `syntax` parameter can be used to highlight the input.
        Syntax highlighting is available only for multiline text inputs.
        """
        return self._add_field(
            "text",
            name,
            label=label,
            value=value,
            placeholder=placeholder,
            regex=regex,
            multiline=multiline or None,
            syntax=syntax,
            rules=rules,
        )

    def boolean(
        self,
        name: str,
        label: str | None = None,
        value: bool = False,
        *,
        rules: list[FormFieldRule] | None = None,
    ) -> Self:
        """Add a checkbox or switch field to the form."""
        return self._add_field(
            "boolean",
            name,
            label=label,
            value=value,
            rules=rules,
        )

    def select(
        self,
        name: str,
        options: list[str] | list[FormSelectOption] | list[EnumItem] | None = None,
        label: str | None = None,
        value: str | None = None,
        *,
        enumResolver: str | None = None,
        enumResolverParams: dict[str, Any] | None = None,
        rules: list[FormFieldRule] | None = None,
    ) -> Self:
        """Add a select field (dropdown) to the form.

        The select field is used to get a single value from the user.
        Option must be provided either as a list of strings or as a
        list of {"value": "value", "label": "label"} dictionaries -
        or, instead of a static list, an `enumResolver` name may be given
        so the frontend fetches live options from `/api/enum`.
        `enumResolverParams` are passed to the resolver and may reference
        earlier fields' values with `{{fieldName}}` templates.
        """
        if options is None and enumResolver is None:
            raise ValueError(
                f"Field '{name}': either 'options' or 'enumResolver' is required."
            )
        return self._add_field(
            "select",
            name,
            label=label,
            value=value,
            options=normalize_options(options) if options is not None else None,
            enumResolver=enumResolver,
            enumResolverParams=enumResolverParams,
            rules=rules,
        )

    def multiselect(
        self,
        name: str,
        options: list[str] | list[FormSelectOption] | list[EnumItem] | None = None,
        label: str | None = None,
        value: list[str] | None = None,
        *,
        enumResolver: str | None = None,
        enumResolverParams: dict[str, Any] | None = None,
        rules: list[FormFieldRule] | None = None,
    ) -> Self:
        """Add a multiselect field (dropdown) to the form.

        The multiselect field is used to get multiple values from the user.
        Option must be provided either as a list of strings or as a
        list of {"value": "value", "label": "label"} dictionaries -
        or, instead of a static list, an `enumResolver` name may be given
        so the frontend fetches live options from `/api/enum`.
        `enumResolverParams` are passed to the resolver and may reference
        earlier fields' values with `{{fieldName}}` templates.

        Value must be provided as a list of strings.
        """
        if options is None and enumResolver is None:
            raise ValueError(
                f"Field '{name}': either 'options' or 'enumResolver' is required."
            )
        return self._add_field(
            "multiselect",
            name,
            label=label,
            value=value,
            options=normalize_options(options) if options is not None else None,
            enumResolver=enumResolver,
            enumResolverParams=enumResolverParams,
            rules=rules,
        )

    def hidden(
        self,
        name: str,
        value: Any = None,
        *,
        rules: list[FormFieldRule] | None = None,
    ) -> Self:
        """Add a hidden field to the form.

        Hidden fields are used to keep an arbitrary value in the context
        of the form. They are not displayed to the user and are not
        interactive.
        """
        return self._add_field("hidden", name, value=value, rules=rules)

    def file(
        self,
        name: str,
        label: str | None = None,
        value: bytes | None = None,
        filename: str | None = None,
        valid_extensions: list[str] | None = None,
        *,
        rules: list[FormFieldRule] | None = None,
    ) -> Self:
        """Add file input / file download field to the form.

        When `value` is provided, the field will be used to
        download a file with the given filename.

        When `value` is not provided, the field will be used to
        upload a file. In this case, `valid_extensions` can be provided
        to restrict the allowed file types.
        """
        file_value: FormFileData | None = None
        if value is not None:
            if not filename:
                raise ValueError("Filename must be provided when value is set.")
            file_value = {
                "payload": b64encode(value).decode("utf-8"),
                "filename": filename,
                "download": True,
            }

        return self._add_field(
            "file",
            name,
            label=label,
            value=file_value,
            # only meaningful for uploads, i.e. when value is not set
            valid_extensions=valid_extensions if file_value is None else None,
            rules=rules,
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
        rules: list[FormFieldRule] | None = None,
    ) -> Self:
        """Add an integer input field to the form.

        The integer input field is used to get an integer value from the user.
        It can be used to get a single line of text or a multiline text.

        The `placeholder` parameter can be used to display a hint to the user.
        """
        return self._add_field(
            "integer",
            name,
            label=label,
            value=value,
            placeholder=placeholder,
            min=min,
            max=max,
            rules=rules,
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
        rules: list[FormFieldRule] | None = None,
    ) -> Self:
        """Add a float input field to the form.

        The float input field is used to get a float value from the user.
        It can be used to get a single line of text or a multiline text.

        The `placeholder` parameter can be used to display a hint to the user.
        """
        return self._add_field(
            "float",
            name,
            label=label,
            value=value,
            placeholder=placeholder,
            min=min,
            max=max,
            rules=rules,
        )
