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


class EntityListItemModel(OPModel):
    id: Annotated[
        str,
        Field(
            default_factory=create_uuid,
            title="Item ID",
            description="ID of the list item entity",
            example="123e4567-e89b-12d3-a456-426614174000",
        ),
    ]

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

    position: Annotated[
        int,
        Field(
            title="Position",
            description="Position of the item in the list",
            example=42,
        ),
    ] = 0

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


class EntityListModel(OPModel):
    id: Annotated[str, Field(default_factory=create_uuid)]
    label: Annotated[str, Field(...)]
    list_type: Annotated[str, Field(...)]
    template: Annotated[dict[str, Any] | None, Field()] = None
    tags: list[str] = Field(default_factory=list)
    items: list[EntityListItemModel] = Field(default_factory=list)
    access: dict[str, ListAccessLevel] = Field(default_factory=dict)
    attrib: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)
