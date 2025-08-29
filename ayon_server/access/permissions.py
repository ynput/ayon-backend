from typing import Any

import aiocache
from pydantic import validator

from ayon_server.lib.postgres import Postgres
from ayon_server.settings import BaseSettingsModel, SettingsField
from ayon_server.utils import json_dumps


def get_folder_access_types():
    return [
        {"value": "assigned", "label": "Assigned"},
        {"value": "hierarchy", "label": "Hierarchy"},
        {"value": "children", "label": "Children"},
    ]


@aiocache.cached(ttl=300)
async def attr_enum():
    return [
        {"value": row["name"], "label": row["title"] or row["name"]}
        async for row in Postgres.iterate(
            """
            SELECT name, data->'title' as title FROM public.attributes
            ORDER BY COALESCE(data->>'title', name)
            """
        )
    ]


def top_level_fields_enum() -> list[dict[str, str]]:
    return [
        {"value": "name", "label": "Entity name"},
        {"value": "label", "label": "Entity label"},
        {"value": "status", "label": "Entity status"},
        {"value": "tags", "label": "Entity tags"},
        {"value": "active", "label": "Entity active state"},
        {"value": "parent_id", "label": "Folder parent ID"},
        {"value": "folder_type", "label": "Folder type"},
        {"value": "task_type", "label": "Task type"},
        {"value": "assignees", "label": "Task assignees"},
        {"value": "product_type", "label": "Product type"},
        {"value": "author", "label": "Version author"},
    ]


class FolderAccess(BaseSettingsModel):
    """FolderAccess model defines a single whitelist item on accessing a folder."""

    _layout = "compact"

    access_type: str = SettingsField(
        "assigned",
        title="Type",
        enum_resolver=get_folder_access_types,
    )

    path: str | None = SettingsField(
        "",
        title="Path",
        description="The path of the folder to allow access to. "
        "Required for access_type 'hierarchy and 'children'",
        example="/assets/characters",
        widget="hierarchy",
    )

    def __hash__(self):
        return hash(json_dumps(self.dict()))

    @validator("path")
    def validate_path(cls, value, values):
        # Do not store path if the access_type does not support it
        if values["access_type"] not in ["hierarchy", "children"]:
            return None
        # We display path WITH a leading slash
        # access control filters remove it when conditions are evaluated
        # but in the access list we want to have it
        value = "/" + value.strip("/")
        return value


class BasePermissionsModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = SettingsField(False)


class FolderAccessList(BasePermissionsModel):
    access_list: list[FolderAccess] = SettingsField(
        default_factory=list, layout="compact"
    )


class AttributeReadAccessList(BasePermissionsModel):
    # We cannot restrict reading top-level fields for now
    # as they are not nullable and we need to return at least something
    # Keeping this here for the future reference
    # fields: list[str] = SettingsField(
    #     title="Readable fields",
    #     default_factory=list,
    #     enum_resolver=top_level_fields_enum,
    # )

    attributes: list[str] = SettingsField(
        title="Readable attributes",
        default_factory=list,
        enum_resolver=attr_enum,
    )


class AttributeWriteAccessList(BasePermissionsModel):
    fields: list[str] = SettingsField(
        title="Writable fields",
        default_factory=list,
        enum_resolver=top_level_fields_enum,
    )
    attributes: list[str] = SettingsField(
        title="Writable attributes",
        default_factory=list,
        enum_resolver=attr_enum,
    )


class EndpointsAccessList(BasePermissionsModel):
    endpoints: list[str] = SettingsField(default_factory=list)


# Model for studio management permissions


class StudioManagementPermissions(BaseSettingsModel):
    create_projects: bool = SettingsField(
        False,
        title="Create projects",
        description="Allow users to create new projects",
        scope=["studio"],
        widget="permission",
    )

    list_all_users: bool = SettingsField(
        False,
        title="List all users",
        description="Allow users to list all users in the studio",
        scope=["studio"],
        widget="permission",
    )

    # For future use, if needed

    # list_all_projects: bool = SettingsField(
    #     False,
    #     title="List all projects",
    #     scope=["studio"],
    #     widget="permission",
    # )


# Model for Project management permissions


class ProjectManagementPermissions(BaseSettingsModel):
    anatomy: int = SettingsField(
        0,
        title="Project anatomy",
        description="Allow users to view or edit the project anatomy",
        widget="permission",
    )
    access: int = SettingsField(
        0,
        title="Project access",
        description="Allow users to view or assign users to project access groups",
        widget="permission",
    )
    settings: int = SettingsField(
        0,
        title="Project addon settings",
        description="Allow users to view or edit the project addon settings",
        widget="permission",
    )


# Full permissions model, we separate project and studio permissions here
# To be able to return just the relevant part of the permissions to the client
# But the model used to store all the permissions is the combined one


class ProjectAdvancedPermissions(BaseSettingsModel):
    show_sibling_tasks: bool = SettingsField(
        True,
        title="Show sibling tasks",
        description="Show sibling tasks when access mode is 'Assigned'",
    )


class Permissions(BaseSettingsModel):
    _layout = "root"

    studio: StudioManagementPermissions = SettingsField(
        default_factory=StudioManagementPermissions,
        title="Studio permissions",
        scope=["studio"],
    )

    project: ProjectManagementPermissions = SettingsField(
        default_factory=ProjectManagementPermissions,
        title="Project permissions",
    )

    create: FolderAccessList = SettingsField(
        default_factory=FolderAccessList,
        title="Restrict folder creation",
        description="Whitelist folders a user can create",
    )

    read: FolderAccessList = SettingsField(
        default_factory=FolderAccessList,
        title="Restrict folder read",
        description="Whitelist folders a user can read",
    )

    update: FolderAccessList = SettingsField(
        default_factory=FolderAccessList,
        title="Restrict folder update",
        description="Whitelist folders a user can update",
    )

    publish: FolderAccessList = SettingsField(
        default_factory=FolderAccessList,
        title="Restrict publishing",
        description="Whitelist folders a user can publish to",
    )

    delete: FolderAccessList = SettingsField(
        default_factory=FolderAccessList,
        title="Restrict folder delete",
        description="Whitelist folders a user can delete",
    )

    attrib_read: AttributeReadAccessList = SettingsField(
        default_factory=AttributeReadAccessList,
        title="Restrict attribute read",
        description="Whitelist attributes a user can read",
    )

    attrib_write: AttributeWriteAccessList = SettingsField(
        default_factory=AttributeWriteAccessList,
        title="Restrict attribute update",
        description="Whitelist attributes a user can write",
    )

    endpoints: EndpointsAccessList = SettingsField(
        default_factory=EndpointsAccessList,
        title="Restrict REST endpoints",
        description="Whitelist REST endpoints a user can access",
    )

    advanced: ProjectAdvancedPermissions = SettingsField(
        default_factory=lambda: ProjectAdvancedPermissions(),
        title="Advanced access control",
    )

    @classmethod
    def from_record(cls, perm_dict: dict[str, Any]) -> "Permissions":
        """Recreate a permission object from a JSON object."""
        return cls(**perm_dict)
