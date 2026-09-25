from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.common import query_entity_data
from ayon_server.entities.core.base import BaseEntity
from ayon_server.exceptions import (
    AyonException,
    ConstraintViolationException,
    NotFoundException,
)
from ayon_server.helpers.entity_links import remove_entity_links
from ayon_server.helpers.statuses import get_default_status_for_entity
from ayon_server.lib.postgres import Postgres
from ayon_server.types import ProjectLevelEntityType
from ayon_server.utils import EntityID, SQLTool, dict_exclude

BASE_GET_QUERY = """
    SELECT *
    FROM project_{project_name}.{entity_type}s entity
"""


class ProjectLevelEntity(BaseEntity):
    entity_type: ProjectLevelEntityType
    project_name: str
    base_get_query: str = BASE_GET_QUERY

    @staticmethod
    def preprocess_record(record: dict[str, Any]) -> dict[str, Any]:
        return record

    def __init__(
        self,
        project_name: str,
        payload: dict[str, Any],
        exists: bool = False,
        own_attrib: list[str] | None = None,
        inherited_attrib: dict[str, Any] | None = None,
        project_attrib: dict[str, Any] | None = None,
    ) -> None:
        """Return a new entity instance from given data.

        When own_attrib is set to None, all attributes are
        considered entity's own. When set to list, only selected
        attributes will be stored in the attrib column, others will
        be considered inherited (and stored in exported_attribs)

        Entities loaded from the database (`exists`) resolve their attribute
        values from the stored own values and the `inherited_attrib`
        (exported attributes of the parent) and `project_attrib` values.
        Invalid stored values are ignored (see `resolve_attrib`).
        """

        self._init_payload(
            payload,
            exists=exists,
            own_attrib=own_attrib,
            inherited_attrib=inherited_attrib,
            project_attrib=project_attrib,
            label=f"{self.entity_type} {payload.get('id')} in {project_name}",
        )
        self.project_name = project_name

    @classmethod
    def from_record(
        cls,
        project_name: str,
        payload: dict[str, Any],
        own_attrib: list[str] | None = None,
    ):
        """Return an entity instance based on a DB record.

        This factory method differs from the default constructor,
        # because it accepts a DB row data and de-serializes JSON fields
        and reformats ids.

        The record contains the own attribute values of the entity
        (`attrib`). Folders and tasks also contain the values they inherit
        (`inherited_attrib` and `project_attrib`, see `resolve_attrib`).
        """
        # ensure payload is a dict (it might be a asyncpg.Record)
        payload = cls.preprocess_record(dict(payload))
        parsed = {}
        for key in cls.model.main_model.model_fields:
            if key not in payload:
                continue  # there are optional keys too
            parsed[key] = payload[key]
        return cls(
            project_name,
            parsed,
            exists=True,
            own_attrib=own_attrib,
            inherited_attrib=payload.get("inherited_attrib"),
            project_attrib=payload.get("project_attrib"),
        )

    def replace(self, replace_data: BaseModel) -> None:
        """Replace the entity payload with new data."""
        self._payload = self.model.main_model(id=self.id, **replace_data.model_dump())

    #
    # Access control
    #

    def as_user(self, user):
        """Return a payload of the entity limited to the attributes that
        are accessible to the given user.
        """
        result = self._payload.model_copy(deep=True)
        if user.is_manager:  # managers have access to all attributes
            return result

        attr_perm = user.permissions(self.project_name).attrib_read
        if attr_perm.enabled:
            # Remove attributes the user cannot read from the payload,
            # so they are not included in the serialized output
            attrib = result.attrib  # type: ignore[attr-defined]
            for key in tuple(attrib):
                if key not in attr_perm.attributes:
                    attrib.pop(key)
        return result

    async def ensure_create_access(self, user, **kwargs) -> None:
        """Check if the user has access to create a new entity.

        Raises FobiddenException if the user does not have access.
        """

        raise AyonException(
            "Ensure created access called on base class. This is a bug."
        )

    async def ensure_read_access(self, user, **kwargs) -> None:
        """Check if the user has access to read the entity.

        Raises FobiddenException if the user does not have access.
        """
        await ensure_entity_access(user, self.project_name, self.entity_type, self.id)

    async def ensure_update_access(self, user, **kwargs) -> None:
        """Check if the user has access to update the entity.

        Raises FobiddenException if the user does not have access.
        """
        await ensure_entity_access(
            user, self.project_name, self.entity_type, self.id, "update"
        )

    async def ensure_delete_access(self, user, **kwargs) -> None:
        """Check if the user has access to delete the entity.

        Raises FobiddenException if the user does not have access.
        """
        await ensure_entity_access(
            user, self.project_name, self.entity_type, self.id, "delete"
        )

    #
    # Database methods
    #

    @classmethod
    async def load(
        cls,
        project_name: str,
        entity_id: str,
        for_update: bool = False,
        **kwargs,
    ):
        """Load a folder from the database by its project name and IDself.

        This is reimplemented, because we need to select dynamic
        attribute hierarchy.path along with the base data and
        the attributes inherited from parent entities.
        """

        if EntityID.parse(entity_id) is None:
            raise ValueError(f"Invalid {cls.entity_type} ID specified")

        query = cls.base_get_query.format(
            project_name=project_name,
            entity_type=cls.entity_type,
        )

        query += f"""
            WHERE entity.id=$1
            {"FOR UPDATE OF entity NOWAIT" if for_update else ""}
        """

        record = await query_entity_data(query, entity_id)

        return cls.from_record(
            project_name=project_name,
            payload=record,
        )

    #
    # Save
    #

    async def pre_save(self, insert: bool) -> None:
        """Hook called before saving the entity to the database."""
        pass

    async def save(self, *args, auto_commit: bool = True, **kwargs) -> None:
        """Save the entity to the database.

        Supports both creating and updating. Entity must be loaded from the
        database in order to update. If the entity is not loaded, it will be
        created.

        Optional `transaction` argument may be specified to pass a connection object,
        to run the query in (to run multiple transactions). When used,
        Entity.commit method is not called automatically and it is expected
        it is called at the end of the transaction block.
        """

        if self.status is None:
            self.status = await self.get_default_status()

        async with Postgres.transaction():
            attrib = self.own_attrib_to_save()

            if self.exists:
                await self.pre_save(False)
                # Update existing entity
                fields = dict_exclude(
                    self.dict(),
                    ["id", "created_at", "updated_at"] + self.model.dynamic_fields,
                )
                fields["attrib"] = attrib
                fields["updated_at"] = datetime.now()
                fields["updated_by"] = kwargs.get("user_name", None)

                await Postgres.execute(
                    *SQLTool.update(
                        f"project_{self.project_name}.{self.entity_type}s",
                        f"WHERE id = '{self.id}'",
                        **fields,
                    )
                )

            else:
                await self.pre_save(True)
                # Create a new entity
                fields = dict_exclude(
                    self.dict(exclude_none=True),
                    self.model.dynamic_fields,
                )
                fields["attrib"] = attrib
                fields["created_by"] = kwargs.get("user_name", None)
                fields["updated_by"] = kwargs.get("user_name", None)

                await Postgres.execute(
                    *SQLTool.insert(
                        f"project_{self.project_name}.{self.entity_type}s",
                        **fields,
                    )
                )

            if auto_commit:
                await self.commit()

    async def commit(self, **kwargs: Any) -> None:
        await self.refresh_views(self.project_name, **kwargs)

    @classmethod
    async def refresh_views(cls, project_name: str, **kwargs) -> None:
        """Refresh the views for the entity type in the given project.

        This method should be overridden in subclasses to refresh.
        and should be called from commit() method after the entity is saved.
        """
        pass

    #
    # Delete
    #

    async def delete(self, *args, auto_commit: bool = True, **kwargs) -> bool:
        """Delete an existing entity."""
        if not self.id:
            raise NotFoundException(f"Unable to delete unloaded {self.entity_type}.")

        async with Postgres.transaction():
            try:
                query = f"""
                    WITH deleted AS (
                        DELETE FROM project_{self.project_name}.{self.entity_type}s
                        WHERE id=$1
                        RETURNING *
                    ) SELECT count(*) FROM deleted;
                """
                res = await Postgres.fetch(query, self.id)
                await remove_entity_links(
                    self.project_name,
                    self.entity_type,
                    self.id,
                )
                if auto_commit:
                    await self.commit()
                return bool(res[0]["count"])

            except Postgres.ForeignKeyViolationError as e:
                detail = f"Unable to delete {self.entity_type} {self.id}"
                code: str | None = None
                if self.entity_type == "folder":
                    _ = e  # TODO: use this
                    detail = "Unable to delete a folder with products or tasks."
                    code = "delete-folder-with-children"
                raise ConstraintViolationException(detail, code=code)

    async def get_default_status(self) -> str:
        return await get_default_status_for_entity(
            self.project_name,
            self.entity_type,
        )

    #
    # Properties
    #

    @property
    def id(self) -> str:
        """Return the entity id."""
        return self._payload.id  # type: ignore

    @id.setter
    def id(self, value: str):
        """Set the entity id."""
        self._payload.id = value  # type: ignore

    @property
    def parent_id(self) -> str | None:
        """Return the parent id.

        Return None if the entity does not have a parent.
        In case of tasks and products, this is the folder id,
        in case of folders, this is the parent folder id,
        and so on...
        """
        raise NotImplementedError

    @property
    def status(self) -> str:
        """Return the entity status."""
        return self._payload.status  # type: ignore

    @status.setter
    def status(self, value: str):
        """Set the entity status."""
        self._payload.status = value  # type: ignore

    @property
    def tags(self) -> list[str]:
        return self._payload.tags  # type: ignore

    @tags.setter
    def tags(self, value: list[str]):
        self._payload.tags = value  # type: ignore

    #
    # Read only properties
    #

    @property
    def entity_subtype(self) -> str | None:
        """Return the entity subtype.

        For folders and tasks this is the folder type or task type.
        For other entities this is None.
        """
        return None

    @property
    def path(self) -> str:
        return ""

    @property
    def created_by(self) -> str | None:
        return self._payload.created_by  # type: ignore

    @property
    def updated_by(self) -> str | None:
        return self._payload.updated_by  # type: ignore
