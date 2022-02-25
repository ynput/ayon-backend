import json

from pydantic import BaseModel


class FolderAccess(BaseModel):
    access_type: str

    def __hash__(self):
        return hash(json.dumps(self.dict()))


class AccessToHierarchy(FolderAccess):
    access_type: str = "hierarchy"
    path: str


class AccessToAssigned(FolderAccess):
    access_type: str = "assigned"
