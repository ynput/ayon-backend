from typing import Literal

from openpype.access.access import AccessAssigned, AccessChildren, AccessHierarchy
from openpype.types import Field, OPModel

AccessList = list[AccessHierarchy | AccessAssigned | AccessChildren] | Literal["all"]


class Permissions(OPModel):
    """Set of permission for a role.

    Each permission is either bool or a list.
    List permissions also accept Literal["all"]
    value.

    Since access control is permissive by default, don't forget to set
    all permissions you don't want to be allowed to access to empty list.
    """

    create: AccessList = Field(
        default_factory=list,
        description="Defines a set of folders, in which the use can create children",
        example=[{"access_type": "hierarchy", "path": "assets/characters"}],
    )

    read: AccessList = Field(
        default_factory=list,
        description="Defines a set of folders, to which the user has read access.",
        example=[
            {"access_type": "hierarchy", "path": "assets/characters"},
            {"access_type": "hierarchy", "path": "assets/locations"},
            {"access_type": "assigned"},
        ],
    )

    update: AccessList = Field(
        default_factory=list,
        description="Defines a set of folders, to which the user has write access.",
        example=[{"access_type": "children", "path": "assets/characters"}],
    )

    delete: AccessList = Field(
        default_factory=list,
        description="Defines a set of folders, which user can delete",
        example=[{"access_type": "assigned"}],
    )

    attrib_read: list[str] | Literal["all"] = Field(
        default="all",
        description="List of attributes the user can read",
        example="all",
    )

    attrib_write: list[str] | Literal["all"] = Field(
        default="all",
        description="List of attributes the user can write",
        example=["resolutionWidth", "resolutionHeight"],
    )

    endpoints: list[str] | Literal["all"] = Field(
        default="all",
        description="List of REST endpoint user is allowed to use",
        example="all",
    )

    @classmethod
    def from_record(cls, perm_dict: dict) -> "Permissions":
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
        return cls(**permissions)
