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
    _layout: str = "compact"
    access_type: str = Field(
        "assigned",
        title="Type",
        enum_resolver=lambda: ["assigned", "hierarchy", "children"],
    )

    path: str | None = Field("", title="Path")

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
    _layout: str = "root"

    create: FolderAccessList = Field(
        default_factory=FolderAccessList,
        title="Limit folder create",
    )

    read: FolderAccessList = Field(
        default_factory=FolderAccessList,
        title="Limit folder read",
    )

    update: FolderAccessList = Field(
        default_factory=FolderAccessList,
        title="Limit folder update",
    )

    delete: FolderAccessList = Field(
        default_factory=FolderAccessList,
        title="Limit folder delete",
    )

    attrib_read: AttributeAccessList = Field(
        default_factory=AttributeAccessList,
        title="Limit attribute read access",
    )

    attrib_write: AttributeAccessList = Field(
        default_factory=AttributeAccessList,
        title="Limit attribute write access",
    )

    endpoints: EndpointsAccessList = Field(
        default_factory=EndpointsAccessList,
        title="Limit REST endpoints",
    )

    @classmethod
    def from_record(cls, perm_dict: dict) -> "Permissions":
        """Recreate a permission object from a JSON object."""
        return cls(**perm_dict)
