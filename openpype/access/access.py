from openpype.types import OPModel
from openpype.utils import json_dumps


class FolderAccess(OPModel):
    """Base class for folder access.

    Not to be used directly.
    """

    access_type: str

    def __hash__(self):
        return hash(json_dumps(self.dict()))


class AccessHierarchy(FolderAccess):
    access_type: str = "hierarchy"
    path: str


class AccessChildren(FolderAccess):
    access_type: str = "children"
    path: str


class AccessAssigned(FolderAccess):
    access_type: str = "assigned"
