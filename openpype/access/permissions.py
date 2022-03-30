from typing import Literal
from pydantic import BaseModel, Field

from openpype.access.access import AccessAssigned, AccessHierarchy, AccessChildren

AccessList = list[AccessHierarchy | AccessAssigned | AccessChildren] | Literal["all"]


class Permissions(BaseModel):
    """Set of permission for a role.

    Each permission is either bool or a list.
    List permissions also accept Literal["all"]
    value.
    """

    create: AccessList = Field(
        default_factory=list,
        description="Defines a set of folders, in which the use can create children",
    )

    read: AccessList = Field(
        default_factory=list,
        description="Defines a set of folders, to which the user has read access.",
    )

    update: AccessList = Field(
        default_factory=list,
        description="Defines a set of folders, to which the user has write access.",
    )

    delete: AccessList = Field(
        default_factory=list,
        description="Defines a set of folders, which user can delete",
    )

    attrib_read: list[str] | Literal["all"] = Field(
        default_factory=list, description="List of attributes the user can read"
    )

    attrib_write: list[str] | Literal["all"] = Field(
        default_factory=list, description="List of attributes the user can read"
    )

    endpoints: list[str] | Literal["all"] = Field(
        default_factory=list, description="List of Rest endpoint user is allowed to use"
    )

    @classmethod
    def from_record(cls, perm_dict: dict, validate: bool = True) -> "Permissions":
        """Recreate a permission object from a JSON object."""
        permissions = {}
        for key, value in perm_dict.items():
            if (type(value) is list) and (key in ["read", "write"]):
                access_list = []
                for access in value:
                    if access["access_type"] == "hierarchy":
                        access_list.append(AccessHierarchy(path=access["path"]))
                    elif access["access_type"] == "children":
                        access_list.append(AccessChildren(path=access["path"]))
                    elif access["access_type"] == "assigned":
                        access_list.append(AccessAssigned())
                permissions[key] = access_list
            else:
                permissions[key] = value

        if validate:
            return cls(**permissions)
        else:
            return cls.construct(**permissions)
