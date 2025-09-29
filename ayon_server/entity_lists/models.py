from datetime import datetime
from enum import IntEnum
from typing import Annotated, Any, Literal

from ayon_server.types import Field, OPModel, ProjectLevelEntityType
from ayon_server.utils import create_uuid, now


class ListAccessLevel(IntEnum):
    NO_ACCESS = 0  # No access to the list
    READ = 10  # Can view the list and its items
    UPDATE = 20  # Can add/remove items from the list, but not materialize new items
    MANAGE = 30  # Can manage list, rename, change access, etc.


# List attributes

FListID = Field(
    default_factory=create_uuid,
    title="ID",
    example=create_uuid(),
)
FListLabel = Field(
    title="List label",
    example="My list",
)
FListAttrib = Field(
    default_factory=dict,
    title="Attributes",
    description="List attributes",
)
FListType = Field(
    title="List type",
    description="Type of the list",
    example="generic",
)
FListOwner = Field(
    title="Owner",
    description="Name of the user who created the list",
    example="john",
)
FListEntityType = Field(
    title="Entity type",
    description="Type of the entity that can be included in the list",
    example="task",
)
FFolderID = Field(
    title="List folder ID",
    description="ID of the folder containing the list",
)
FListAccess = Field(
    title="Access",
    default_factory=dict,
    description="Access control for the list. Can be specified for users or teams.",
    example={"john": ListAccessLevel.READ, "!producers": ListAccessLevel.UPDATE},
)
FListTemplate = Field(
    default_factory=dict,
    title="Template",
)
FListTags = Field(
    default_factory=list,
    title="Tags",
    description="List tags",
    example=["tag1", "tag2"],
)
FListData = Field(
    default_factory=dict,
    title="Data",
    description="Additional data associated with the list",
)
FListItems = Field(
    title="List items",
    default_factory=list,
)
FListActive = Field(
    title="List active",
    description="Whether the list is active or not",
    example=True,
)

# List item attributes

FListItemId = Field(
    default_factory=create_uuid,
    title="Item ID",
    example=create_uuid(),
)
FListItemEntityId = Field(
    title="Entity ID",
    description="ID of the entity in the list",
    example=create_uuid(),
)
FListItemLabel = Field(
    title="Item label",
    description="Label of the item",
    example="Version 1",
)
FListItemPosition = Field(
    title="Position",
    description="Position of the item in the list",
    example=69,
)
FListItemAttrib = Field(
    default_factory=dict,
    title="Item attributes",
    description="Overrides of the listed entity attributes",
)
FListItemData = Field(
    default_factory=dict,
    title="Item data",
    description="Additional data associated with the item",
)
FListItemTags = Field(
    default_factory=list,
    title="Item tags",
    description="Tags associated with the item",
)
FListItemFolderPath = Field(
    title="Folder path",
    description="Path to the folder where the item is located",
    example="/path/to/folder",
)

FCreatedBy = Field(title="Created by", example="admin")
FUpdatedBy = Field(title="Updated by", example="editor")
FCreatedAt = Field(default_factory=now, title="Created at")
FUpdatedAt = Field(default_factory=now, title="Updated at")


class EntityListItemModel(OPModel):
    id: Annotated[str, FListItemId]
    entity_id: Annotated[str, FListItemEntityId]
    position: Annotated[int, FListItemPosition]
    label: Annotated[str | None, FListItemLabel]
    attrib: Annotated[dict[str, Any], FListItemAttrib]
    data: Annotated[dict[str, Any], FListItemData]
    tags: Annotated[list[str], FListItemTags]
    folder_path: Annotated[str, FListItemFolderPath]
    created_by: Annotated[str | None, FCreatedBy]
    updated_by: Annotated[str | None, FUpdatedBy]
    created_at: Annotated[datetime, FCreatedAt]
    updated_at: Annotated[datetime, FUpdatedAt]


class EntityListItemPostModel(OPModel):
    id: Annotated[str, FListItemId]
    entity_id: Annotated[str, FListItemEntityId]
    position: Annotated[int | None, FListItemPosition]
    label: Annotated[str | None, FListItemLabel]
    attrib: Annotated[dict[str, Any], FListItemAttrib]
    data: Annotated[dict[str, Any], FListItemData]
    tags: Annotated[list[str], FListItemTags]


class EntityListItemPatchModel(OPModel):
    entity_id: Annotated[str | None, FListItemEntityId] = None
    position: Annotated[int | None, FListItemPosition] = None
    label: Annotated[str | None, FListItemLabel] = None
    attrib: Annotated[dict[str, Any], FListItemAttrib]
    data: Annotated[dict[str, Any], FListItemData]
    tags: Annotated[list[str], FListItemTags]


class EntityListModel(OPModel):
    id: Annotated[str, FListID]
    entity_list_type: Annotated[str, FListType]
    entity_list_folder_id: Annotated[str | None, FFolderID] = None
    entity_type: Annotated[ProjectLevelEntityType, FListEntityType]
    label: Annotated[str, FListLabel]
    access: Annotated[dict[str, ListAccessLevel], FListAccess]
    attrib: Annotated[dict[str, Any], FListAttrib]
    data: Annotated[dict[str, Any], FListData]
    template: Annotated[dict[str, Any], FListTemplate]
    tags: Annotated[list[str], FListTags]
    items: Annotated[list[EntityListItemModel], FListItems]
    owner: Annotated[str | None, FListOwner]
    created_by: Annotated[str | None, FCreatedBy]
    updated_by: Annotated[str | None, FUpdatedBy]
    created_at: Annotated[datetime, FCreatedAt]
    updated_at: Annotated[datetime, FUpdatedAt]
    active: Annotated[bool, FListActive]
    access_level: Annotated[
        ListAccessLevel, Field(title="Current user's access level")
    ] = ListAccessLevel.MANAGE


class EntityListPostModel(OPModel):
    id: Annotated[str, FListID]
    entity_list_type: Annotated[str, FListType] = "generic"
    entity_list_folder_id: Annotated[str | None, FFolderID] = None
    entity_type: Annotated[ProjectLevelEntityType, FListEntityType]
    label: Annotated[str, FListLabel]
    access: Annotated[dict[str, ListAccessLevel], FListAccess]
    attrib: Annotated[dict[str, Any], FListAttrib]
    data: Annotated[dict[str, Any], FListData]
    template: Annotated[dict[str, Any], FListTemplate]
    tags: Annotated[list[str], FListTags]
    owner: Annotated[str | None, FListOwner] = None
    active: Annotated[bool | None, FListActive] = True
    items: Annotated[list[EntityListItemPostModel], FListItems]


class EntityListPatchModel(OPModel):
    label: Annotated[str | None, FListLabel] = None
    access: Annotated[dict[str, ListAccessLevel], FListAccess]
    attrib: Annotated[dict[str, Any], FListAttrib]
    entity_list_folder_id: Annotated[str | None, FFolderID] = None
    data: Annotated[dict[str, Any], FListData]
    tags: Annotated[list[str], FListTags]
    owner: Annotated[str | None, FListOwner] = None
    active: Annotated[bool | None, FListActive] = None


class EntityListSummary(OPModel):
    id: Annotated[str, FListID]
    entity_list_type: Annotated[str, FListType]
    entity_type: Annotated[ProjectLevelEntityType, FListEntityType]
    label: Annotated[str, FListLabel]
    count: Annotated[int, Field(title="Item count", ge=0)] = 0


#
# Multi-update
#

EntityListMultiPatchMode = Literal["replace", "merge", "delete"]


class EntityListMultiPatchItemModel(OPModel):
    id: Annotated[str | None, FListItemId]
    entity_id: Annotated[str | None, FListItemEntityId] = None
    position: Annotated[int | None, FListItemPosition] = None
    label: Annotated[str | None, FListItemLabel] = None
    attrib: Annotated[dict[str, Any], FListItemAttrib]
    data: Annotated[dict[str, Any], FListItemData]
    tags: Annotated[list[str], FListItemTags]


class EntityListMultiPatchModel(OPModel):
    items: Annotated[
        list[EntityListMultiPatchItemModel],
        Field(
            title="Patched items",
            default_factory=list,
            min_items=1,
        ),
    ]
    mode: Annotated[
        EntityListMultiPatchMode,
        Field(
            title="Patch mode",
            description=(
                "The mode of the operation. "
                "`replace` will replace all items with the provided ones. "
                "`merge` will merge the provided items with the existing ones."
                "`delete` will delete items with matching ids from the list."
            ),
        ),
    ] = "replace"
