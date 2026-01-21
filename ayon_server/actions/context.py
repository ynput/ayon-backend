import base64
from typing import Annotated, Any, Literal

from pydantic import validator

from ayon_server.entities import ProjectEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.exceptions import NotFoundException
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.lib.redis import Redis
from ayon_server.types import Field, OPModel
from ayon_server.utils.hashing import create_uuid

ActionEntityType = Literal[
    "project",
    "list",
    "folder",
    "task",
    "product",
    "version",
    "representation",
    "workfile",
]


class FormFile:
    payload: str
    filename: str
    cache_key: str | None

    def __init__(
        self,
        payload: str,
        filename: str,
        cache_key: str | None = None,
    ) -> None:
        self.filename = filename
        self.payload = payload
        self.cache_key = cache_key

    def get_bytes(self) -> bytes:
        return base64.b64decode(self.payload)

    def dump(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "payload": self.payload,
        }

    async def save_to_cache(self) -> str:
        if not self.cache_key:
            self.cache_key = create_uuid()
        await Redis.set_json(
            "action-file",
            self.cache_key,
            self.dump(),
            ttl=3600,
        )
        return self.cache_key

    @classmethod
    async def from_cache(cls, cache_key: str) -> "FormFile":
        data = await Redis.get_json("action-file", cache_key)
        if not data:
            raise ValueError(f"No cached file found for cache key '{cache_key}'")
        return cls(
            payload=data["payload"],
            filename=data["filename"],
            cache_key=cache_key,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FormFile":
        payload = data.get("payload")
        filename = data.get("filename")
        if not (payload and filename):
            raise ValueError("Invalid file data")

        return cls(
            payload=payload,
            filename=filename,
            cache_key=None,
        )


class ActionContext(OPModel):
    """
    frontend sends this to backend.
    backend asks addons for actions based on this model.
    """

    project_name: Annotated[
        str | None,
        Field(
            title="Project Name",
            description=(
                "The name of the project. "
                "If not provided, use global actions, "
                "the rest of the fields are ignored."
            ),
            example="my_project",
        ),
    ] = None

    entity_type: Annotated[
        ActionEntityType | None,
        Field(
            title="Entity Type",
            description=(
                "The type of the entity. Either a project level entity, 'list' "
                "or 'project' for project-wide actions. or None for global actions."
            ),
            example="folder",
        ),
    ] = None

    # frontend already knows this, so it can speed up
    # the action resolving process when it sends this.

    entity_subtypes: Annotated[
        list[str] | None,
        Field(
            title="Entity Subtypes",
            description="List of subtypes present in the entity list",
            example=["asset"],
        ),
    ] = None

    entity_ids: Annotated[
        list[str] | None,
        Field(
            title="Entity IDs",
            description="The IDs of the entities",
            example=["1a3bfe33-1b1b-4b1b-8b1b-1b1b1b1b1b1b"],
        ),
    ] = None

    form_data: Annotated[
        dict[str, Any] | None,
        Field(
            title="Form Data",
            description="The data from the form",
            example={"key": "value"},
        ),
    ] = None

    async def get_form_file(self, key: str, *, cache: bool = False) -> FormFile:
        """Get file bytes from form data.

        If a form contains a file input, this function can be used to
        retrieve the file bytes and additional metadata.

        Optionally, the file can be cached in Redis for later retrieval
        using a cache key (which will be included in FormFile object returned).
        """
        if not self.form_data:
            raise ValueError("No form data provided")

        file_data = self.form_data.get(key)
        if not file_data:
            raise ValueError(f"No file found in form data for key '{key}'")

        result = FormFile.from_dict(file_data)
        if cache:
            await result.save_to_cache()
        return result

    async def get_cached_file(self, cache_key: str) -> FormFile:
        """Retrieve cached file bytes from Redis using the cache key."""
        return await FormFile.from_cache(cache_key)

    #
    # Sanity checks
    #

    @validator("entity_type", "entity_subtypes", "entity_ids")
    def global_actions_only(cls, v, values):
        """
        If project_name is not provided, ignore the rest of the fields.
        """
        if values.get("project_name") is None:
            return None
        return v

    @validator("entity_ids")
    def validate_entity_ids(cls, v, values):
        if values.get("project_name") is None:
            return None
        if values.get("entity_type") is None:
            return None
        if v is None:
            return []
        return v

    #
    # Entity caching
    #

    async def get_entities(self) -> list[ProjectLevelEntity]:
        # TODO : Cache this during the request lifecycle
        # Note: we cannot store it as the class variable tho :-/
        if (
            self.project_name is None
            or self.entity_type is None
            or self.entity_ids is None
            or self.entity_type == "list"
        ):
            return []

        result = []
        entity_class = get_entity_class(self.entity_type)
        for entity_id in self.entity_ids:
            try:
                entity = await entity_class.load(self.project_name, entity_id)
            except NotFoundException:
                continue

            result.append(entity)
        return result

    async def get_project_entity(self) -> ProjectEntity | None:
        # TODO : Cache this during the request lifecycle
        """Cached project entity DURING THE REQUEST"""
        if not self.project_name:
            return None
        return await ProjectEntity.load(self.project_name)

    #
    # Context comparison
    #

    def __hash__(self):
        elength = len(self.entity_ids) > 1 if self.entity_ids else 0
        hash_base = (
            self.project_name,
            self.entity_type,
            self.entity_subtypes,
            elength,
        )
        return hash(hash_base)

    def __eq__(self, other: Any):
        if isinstance(other, ActionContext):
            return self.__hash__() == other.__hash__()
        return False
