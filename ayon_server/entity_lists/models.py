from datetime import datetime
from enum import IntEnum
from typing import Annotated, Any

from ayon_server.types import Field, OPModel, ProjectLevelEntityType
from ayon_server.utils import create_uuid


class ListAccessLevel(IntEnum):
    READ = 10  # Can view the list and its items
    UPDATE = 20  # Can update attributes of the list items
    CONSTRUCT = 30  # Can add/remove items from the list or materialize new items
    ADMIN = 40  # Can update/delete the list itself and add new users to the list


class EntityListConfig(OPModel):
    entity_types: Annotated[
        list[ProjectLevelEntityType],
        Field(
            title="Entity Types",
            description="Entity types that can be included in the list",
        ),
    ] = ["folder", "version", "task"]


class BaseGetModel(OPModel):
    id: Annotated[
        str,
        Field(
            default_factory=create_uuid,
            title="ID",
            example="123e4567-e89b-12d3-a456-426614174000",
        ),
    ]


class EntityListItemPatchModel(OPModel):
    position: Annotated[
        int,
        Field(
            title="Position",
            description="Position of the item in the list",
            example=42,
        ),
    ] = 0

    label: Annotated[
        str | None,
        Field(
            title="Label",
            description="Label of the item",
            example="Version 1",
        ),
    ] = None

    attrib: Annotated[
        dict[str, Any],
        Field(
            default_factory=dict,
            title="Item attributes",
            description="Overrides of the listed entity attributes",
        ),
    ]

    data: Annotated[
        dict[str, Any],
        Field(
            default_factory=dict,
            title="Item data",
            description="Additional data associated with the item",
        ),
    ]

    tags: Annotated[
        list[str],
        Field(
            default_factory=list,
            title="Item tags",
            description="Tags associated with the item",
        ),
    ]

    created_by: Annotated[
        str | None,
        Field(
            title="Created by",
            description="Name of the user who created the item",
            example="admin",
        ),
    ] = None

    updated_by: Annotated[
        str | None,
        Field(
            title="Updated by",
            description="Name of the user who last updated the item",
            example="editor",
        ),
    ] = None

    created_at: Annotated[
        datetime,
        Field(
            default_factory=datetime.utcnow,
            title="Created at",
            description="Timestamp of when the item was created",
        ),
    ]

    updated_at: Annotated[
        datetime,
        Field(
            default_factory=datetime.utcnow,
            title="Updated at",
            description="Timestamp of when the item was last updated",
        ),
    ]


class EntityListItemModel(EntityListItemPatchModel, BaseGetModel):
    entity_type: Annotated[
        ProjectLevelEntityType,
        Field(
            title="Entity type",
            description="Type of the list item entity",
            example="version",
        ),
    ]

    entity_id: Annotated[
        str,
        Field(
            title="Entity ID",
            description="ID of the list item entity",
            example="123e4567-e89b-12d3-a456-426614174000",
        ),
    ]


class EntityListPatchModel(OPModel):
    entity_list_type: Annotated[
        str | None,
        Field(
            title="Entity list type",
            description="Type of the entity list",
            example="generic",
        ),
    ] = None

    label: Annotated[
        str | None,
        Field(
            title="List label",
            example="My list",
        ),
    ] = None

    tags: Annotated[
        list[str] | None,
        Field(
            title="Tags",
        ),
    ] = None

    access: Annotated[
        dict[str, ListAccessLevel] | None,
        Field(
            title="List access",
            description=(
                "Access control for the list. "
                " be specified for individual users or teams."
            ),
            example={
                "john": ListAccessLevel.READ,
                "!producers": ListAccessLevel.UPDATE,
            },
        ),
    ] = None

    attrib: Annotated[
        dict[str, Any] | None,
        Field(
            title="List attributes",
        ),
    ] = None

    data: Annotated[
        dict[str, Any] | None,
        Field(
            title="List data",
        ),
    ] = None

    template: Annotated[
        dict[str, Any] | None,
        Field(
            title="List template",
        ),
    ] = None

    owner: Annotated[
        str | None,
        Field(
            title="List owner",
            description="Name of the user who created the list",
            example="john",
        ),
    ] = None


class EntityListModel(EntityListPatchModel, BaseGetModel):
    items: Annotated[
        list[EntityListItemModel] | None,
        Field(
            title="List items",
        ),
    ] = None

    config: Annotated[
        EntityListConfig | None,
        Field(
            default_factory=EntityListConfig,
            title="List configuration",
        ),
    ]

    created_by: Annotated[
        str | None,
        Field(
            title="List creator",
            description="Name of the user who created the list",
            example="john",
        ),
    ] = None

    updated_by: Annotated[
        str | None,
        Field(
            title="List updater",
            description="Name of the user who updated the list",
            example="john",
        ),
    ] = None
