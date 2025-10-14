from typing import Annotated, Any, Literal

from pydantic import validator

from ayon_server.enum.enum_item import EnumItem
from ayon_server.types import (
    ATTRIBUTE_NAME_REGEX,
    AttributeType,
    Field,
    OPModel,
    ProjectLevelEntityType,
    TopLevelEntityType,
)


class AttributeData(OPModel):
    type: Annotated[
        AttributeType,
        Field(
            title="Type",
            description="Type of attribute value",
            example="string",
        ),
    ] = "string"

    title: Annotated[
        str | None,
        Field(
            title="Title",
            description="Nice, human readable title of the attribute",
            example="My attribute",
        ),
    ] = None

    description: Annotated[
        str | None,
        Field(
            title="Field description",
            example="Value of my attribute",
        ),
    ] = None

    example: Annotated[
        Any,
        Field(
            title="Field example",
            description="Example value of the field.",
            example="value1",
        ),
    ] = None

    default: Annotated[
        Any,
        Field(
            title="Field default value",
            description="Default value for the attribute. Do not set for list types.",
        ),
    ] = None

    gt: Annotated[int | float | None, Field(title="Greater than")] = None
    ge: Annotated[int | float | None, Field(title="Greater or equal")] = None
    lt: Annotated[int | float | None, Field(title="Less")] = None
    le: Annotated[int | float | None, Field(title="Less or equal")] = None

    min_length: Annotated[int | None, Field(title="Minimum length")] = None

    max_length: Annotated[int | None, Field(title="Maximum length")] = None

    min_items: Annotated[
        int | None,
        Field(
            title="Minimum items",
            description="Minimum number of items in list type.",
        ),
    ] = None

    max_items: Annotated[
        int | None,
        Field(
            title="Maximum items",
            description="Only for list types. Maximum number of items in the list.",
        ),
    ] = None

    regex: Annotated[
        str | None,
        Field(
            title="Field regex",
            description="Only for string types. The value must match this regex.",
            example="^[a-zA-Z0-9_]+$",
        ),
    ] = None

    enum: Annotated[
        list[EnumItem] | None,
        Field(
            title="Field enum",
            description="List of enum items used for displaying select widgets",
            example=[
                {"value": "value1", "label": "Value 1"},
                {"value": "value2", "label": "Value 2"},
                {"value": "value3", "label": "Value 3"},
            ],
        ),
    ] = None

    enum_resolver: Annotated[
        str | None,
        Field(
            title="Enum resolver",
            description="Name of the function that provides enum values dynamically.",
            example="folder_types",
        ),
    ] = None

    enum_resolver_settings: Annotated[
        dict[str, Any] | None,
        Field(
            title="Enum resolver settings",
            description="Settings passed to the enum resolver function.",
            example={"someSetting": "someValue"},
        ),
    ] = None

    inherit: Annotated[
        bool,
        Field(
            title="Inherit",
            description="Inherit the attribute value from the parent entity.",
        ),
    ] = True

    @validator("enum")
    def validate_enum(cls, value: list[EnumItem] | None) -> list[EnumItem] | None:
        if value == []:
            return None
        return value


class AttributeNameModel(OPModel):
    name: Annotated[
        str,
        Field(
            title="Attribute name",
            regex=ATTRIBUTE_NAME_REGEX,
            example="my_attribute",
        ),
    ]


class AttributePutModel(OPModel):
    position: Annotated[
        int,
        Field(
            title="Positon",
            description="Default order",
            example=12,
        ),
    ]
    scope: Annotated[
        list[ProjectLevelEntityType | TopLevelEntityType | Literal["list"]],
        Field(
            default_factory=list,
            title="Scope",
            description="List of entity types the attribute is available on",
            example=["folder", "task"],
        ),
    ]
    data: AttributeData


class AttributePatchModel(OPModel):
    position: Annotated[
        int | None,
        Field(
            title="Position",
            description="Default order",
            example=12,
        ),
    ] = None
    scope: Annotated[
        list[ProjectLevelEntityType | TopLevelEntityType | Literal["list"]] | None,
        Field(
            title="Scope",
            description="List of entity types the attribute is available on",
            example=["folder", "task"],
        ),
    ] = None
    data: AttributeData | None = None


class AttributeModel(AttributePutModel, AttributeNameModel):
    builtin: Annotated[
        bool,
        Field(
            title="Builtin",
            description="Is attribute builtin. Built-in attributes cannot be removed.",
        ),
    ] = False
