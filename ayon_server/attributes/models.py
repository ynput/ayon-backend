from typing import Annotated, Any, Literal

from ayon_server.types import (
    ATTRIBUTE_NAME_REGEX,
    AttributeEnumItem,
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
            ...,
            title="Type",
            description="Type of attribute value",
            example="string",
        ),
    ]

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
        list[AttributeEnumItem] | None,
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

    inherit: Annotated[
        bool,
        Field(
            title="Inherit",
            description="Inherit the attribute value from the parent entity.",
        ),
    ] = True


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
    builtin: Annotated[
        bool,
        Field(
            title="Builtin",
            description="Is attribute builtin. Built-in attributes cannot be removed.",
        ),
    ] = False
    data: AttributeData


class AttributeModel(AttributePutModel, AttributeNameModel):
    pass
