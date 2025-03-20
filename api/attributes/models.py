from typing import Any

from ayon_server.types import (
    AttributeEnumItem,
    AttributeType,
    Field,
    OPModel,
    ProjectLevelEntityType,
    TopLevelEntityType,
)


class AttributeData(OPModel):
    type: AttributeType = Field(
        ...,
        title="Type",
        description="Type of attribute value",
        example="string",
    )
    title: str | None = Field(
        None,
        title="Title",
        description="Nice, human readable title of the attribute",
        example="My attribute",
    )
    description: str | None = Field(
        None,
        title="Field description",
        example="Value of my attribute",
    )
    example: Any = Field(
        None,
        title="Field example",
        description="Example value of the field.",
        example="value1",
    )
    default: Any = Field(
        None,
        title="Field default value",
        description="Default value for the attribute. Do not set for list types.",
    )
    gt: int | float | None = Field(None, title="Greater than")
    ge: int | float | None = Field(None, title="Geater or equal")
    lt: int | float | None = Field(None, title="Less")
    le: int | float | None = Field(None, title="Less or equal")
    min_length: int | None = Field(None, title="Minimum length")
    max_length: int | None = Field(None, title="Maximum length")
    min_items: int | None = Field(
        None,
        title="Minimum items",
        description="Minimum number of items in list type.",
    )
    max_items: int | None = Field(
        None,
        title="Maximum items",
        description="Only for list types. Maximum number of items in the list.",
    )
    regex: str | None = Field(
        None,
        title="Field regex",
        description="Only for string types. The value must match this regex.",
        example="^[a-zA-Z0-9_]+$",
    )

    enum: list[AttributeEnumItem] | None = Field(
        None,
        title="Field enum",
        description="List of enum items used for displaying select/multiselect widgets",
        example=[
            {"value": "value1", "label": "Value 1"},
            {"value": "value2", "label": "Value 2"},
            {"value": "value3", "label": "Value 3"},
        ],
    )
    inherit: bool = Field(
        True,
        title="Inherit",
        description="Inherit the attribute value from the parent entity.",
    )


class AttributeNameModel(OPModel):
    name: str = Field(
        ...,
        title="Attribute name",
        regex="^[a-zA-Z0-9]{2,30}$",
        example="my_attribute",
    )


class AttributePutModel(OPModel):
    position: int = Field(
        ...,
        title="Positon",
        description="Default order",
        example=12,
    )
    scope: list[ProjectLevelEntityType | TopLevelEntityType] = Field(
        default_factory=list,
        title="Scope",
        description="List of entity types the attribute is available on",
        example=["folder", "task"],
    )
    builtin: bool = Field(
        False,
        title="Builtin",
        description="Is attribute builtin. Built-in attributes cannot be removed.",
    )
    data: AttributeData


class AttributeModel(AttributePutModel, AttributeNameModel):
    pass
