from typing import Any

from pydantic import validator

from ayon_server.lib.postgres import Postgres
from ayon_server.settings import BaseSettingsModel, SettingsField
from ayon_server.settings.enum import addons_enum
from ayon_server.utils import json_dumps


def get_folder_access_types():
    return [
        {"value": "assigned", "label": "Assigned"},
        {"value": "hierarchy", "label": "Hierarchy"},
        {"value": "children", "label": "Children"},
    ]


async def attr_enum():
    return [
        row["name"]
        async for row in Postgres.iterate("SELECT name FROM public.attributes")
    ]


class FolderAccess(BaseSettingsModel):
    """FolderAccess model defines a single whitelist item on accessing a folder."""

    _layout: str = "compact"

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


class AttributeAccessList(BasePermissionsModel):
    attributes: list[str] = SettingsField(
        default_factory=list,
        enum_resolver=attr_enum,
    )


class EndpointsAccessList(BasePermissionsModel):
    endpoints: list[str] = SettingsField(default_factory=list)


class StudioSettingsAccessModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = SettingsField(True, title="Restrict access to settings")
    addons: list[str] = SettingsField(
        default_factory=list,
        title="Addons",
        description="List of addons a user can access",
        enum_resolver=addons_enum,
    )


class ProjectSettingsAccessModel(StudioSettingsAccessModel):
    anatomy_update: bool = SettingsField(
        False,
        title="Allow project anatomy update",
        description="Allow users to update the project anatomy",
    )


class Permissions(BaseSettingsModel):
    """
    The Permissions model defines the permissions for an access group.
    to interact with specific resources in the system.
    """

    _layout: str = "root"

    studio_settings: StudioSettingsAccessModel = SettingsField(
        default_factory=StudioSettingsAccessModel,
        title="Studio settings",
        description="Restrict access to studio settings",
        scope=["studio"],
    )

    project_settings: ProjectSettingsAccessModel = SettingsField(
        default_factory=ProjectSettingsAccessModel,
        title="Project settings",
        description="Restrict write access to project settings",
        scope=["studio", "project"],
    )

    create: FolderAccessList = SettingsField(
        default_factory=FolderAccessList,
        title="Restrict folder creation",
        description="Whitelist folders a user can create",
        section="Folder Access",
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

    attrib_read: AttributeAccessList = SettingsField(
        default_factory=AttributeAccessList,
        title="Restrict attribute read",
        description="Whitelist attributes a user can read",
    )

    attrib_write: AttributeAccessList = SettingsField(
        default_factory=AttributeAccessList,
        title="Restrict attribute update",
        description="Whitelist attributes a user can write",
    )

    endpoints: EndpointsAccessList = SettingsField(
        default_factory=EndpointsAccessList,
        title="Restrict REST endpoints",
        description="Whitelist REST endpoints a user can access",
    )

    @classmethod
    def from_record(cls, perm_dict: dict[str, Any]) -> "Permissions":
        """Recreate a permission object from a JSON object."""
        return cls(**perm_dict)
