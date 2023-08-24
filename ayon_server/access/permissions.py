from pydantic import Field, validator

from ayon_server.lib.postgres import Postgres
from ayon_server.settings import BaseSettingsModel
from ayon_server.utils import json_dumps


async def attr_enum():
    return [
        row["name"]
        async for row in Postgres.iterate("SELECT name FROM public.attributes")
    ]


class FolderAccess(BaseSettingsModel):
    """FolderAccess model defines a single whitelist item on accessing a folder."""

    _layout: str = "compact"
    access_type: str = Field(
        "assigned",
        title="Type",
        enum_resolver=lambda: ["assigned", "hierarchy", "children"],
    )

    path: str | None = Field(
        "",
        title="Path",
        description="The path of the folder to allow access to. "
        "Required for access_type 'hierarchy and 'children'",
        widget="hierarchy",
    )

    def __hash__(self):
        return hash(json_dumps(self.dict()))

    @validator("path")
    def validate_path(cls, value, values):
        # Do not store path if the access_type does not support it
        if values["access_type"] not in ["hierarchy", "children"]:
            return None
        return value


class BasePermissionsModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = Field(False)


class FolderAccessList(BasePermissionsModel):
    access_list: list[FolderAccess] = Field(default_factory=list, layout="compact")


class AttributeAccessList(BasePermissionsModel):
    attributes: list[str] = Field(
        default_factory=list,
        enum_resolver=attr_enum,
    )


class EndpointsAccessList(BasePermissionsModel):
    endpoints: list[str] = Field(default_factory=list)


class Permissions(BaseSettingsModel):
    """
    The Permissions model defines the permissions for an access group.
    to interact with specific resources in the system.
    """

    _layout: str = "root"

    create: FolderAccessList = Field(
        default_factory=FolderAccessList,
        title="Restrict folder creation",
        description="Whitelist folders a user can create",
    )

    read: FolderAccessList = Field(
        default_factory=FolderAccessList,
        title="Restrict folder read",
        description="Whitelist folders a user can read",
    )

    update: FolderAccessList = Field(
        default_factory=FolderAccessList,
        title="Restrict folder update",
        description="Whitelist folders a user can update",
    )

    delete: FolderAccessList = Field(
        default_factory=FolderAccessList,
        title="Restrict folder delete",
        description="Whitelist folders a user can delete",
    )

    attrib_read: AttributeAccessList = Field(
        default_factory=AttributeAccessList,
        title="Restrict attribute read",
        description="Whitelist attributes a user can read",
    )

    attrib_write: AttributeAccessList = Field(
        default_factory=AttributeAccessList,
        title="Restrict attribute update",
        description="Whitelist attributes a user can write",
    )

    endpoints: EndpointsAccessList = Field(
        default_factory=EndpointsAccessList,
        title="Restrict REST endpoints",
        description="Whitelist REST endpoints a user can access",
    )

    @classmethod
    def from_record(cls, perm_dict: dict) -> "Permissions":
        """Recreate a permission object from a JSON object."""
        return cls(**perm_dict)
