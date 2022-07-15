from typing import Any

from pydantic import BaseModel

from openpype.access.utils import ensure_entity_access
from openpype.entities.core.base import BaseEntity
from openpype.exceptions import ConstraintViolationException, NotFoundException
from openpype.lib.postgres import Postgres
from openpype.types import ProjectLevelEntityType
from openpype.utils import SQLTool, dict_exclude


class ProjectLevelEntity(BaseEntity):
    entity_type: ProjectLevelEntityType
    project_name: str

    def __init__(
        self,
        project_name: str,
        payload: dict[str, Any],
        exists: bool = False,
        validate: bool = True,
        own_attrib: list[str] = None,
    ) -> None:
        """Return a new entity instance from given data.

        When own_attrib is set to None, all attributes are
        considered entity's own. When set to list, only selected
        attributes will be stored in the attrib column, others will
        be considered inherited (and stored in exported_attribs)
        """

        attrib_dict = payload.get("attrib", {})
        if own_attrib is None:
            self.own_attrib = list(attrib_dict.keys())
        else:
            self.own_attrib = own_attrib

        if validate:
            self._payload = self.model.main_model(
                **dict_exclude(payload, ["own_attrib"]),
                own_attrib=self.own_attrib,
            )
        else:
            attrib = self.model.attrib_model.construct(**attrib_dict)
            self._payload = self.model.main_model.construct(
                **dict_exclude(payload, ["attrib", "own_attrib"]),
                attrib=attrib,
                own_attrib=self.own_attrib,
            )

        self.exists = exists
        self.project_name = project_name

    @classmethod
    def from_record(
        cls,
        project_name: str,
        payload: dict[str, Any],
        validate: bool = False,
        own_attrib: list[str] | None = None,
    ):
        """Return an entity instance based on a DB record.

        This factory method differs from the default constructor,
        # because it accepts a DB row data and de-serializes JSON fields
        and reformats ids.

        By default it does not validate the data, sice it is assumed the
        correct format is stored in the database.
        """
        project_name = project_name.lower()
        parsed = {}
        for key in cls.model.main_model.__fields__:
            if key not in payload:
                continue  # there are optional keys too
            parsed[key] = payload[key]
        return cls(
            project_name,
            parsed,
            exists=True,
            validate=validate,
            own_attrib=own_attrib,
        )

    def replace(self, replace_data: BaseModel) -> None:
        """Replace the entity payload with new data."""
        self._payload = self.model.main_model(id=self.id, **replace_data.dict())

    #
    # Access control
    #

    def as_user(self, user):
        """Return a payload of the entity limited to the attributes that
        are accessible to the given user.
        """
        kw: dict[str, Any] = {"deep": True, "exclude": {}}

        # TODO: Clean-up. use model.attrb_model.__fields__ to create blacklist
        attrib = self._payload.attrib.dict()
        if not user.is_manager:
            kw["exclude"]["data"] = True

            attr_perm = user.permissions(self.project_name).attrib_read
            if attr_perm != "all":
                exattr = set()
                for key in [*attrib.keys()]:
                    if key not in attr_perm:
                        exattr.add(key)
                if exattr:
                    kw["exclude"]["attrib"] = exattr

        result = self._payload.copy(**kw)
        return result

    async def ensure_create_access(self, user) -> None:
        """Check if the user has access to create a new entity.

        Raises FobiddenException if the user does not have access.
        """
        await ensure_entity_access(
            user, self.project_name, self.entity_type, self.id, "create"
        )

    async def ensure_read_access(self, user) -> None:
        """Check if the user has access to read the entity.

        Raises FobiddenException if the user does not have access.
        """
        await ensure_entity_access(
            user, self.project_name, self.entity_type, self.id, "read"
        )

    async def ensure_update_access(self, user) -> None:
        """Check if the user has access to update the entity.

        Raises FobiddenException if the user does not have access.
        """
        await ensure_entity_access(
            user, self.project_name, self.entity_type, self.id, "update"
        )

    async def ensure_delete_access(self, user) -> None:
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
        transaction=None,
        for_update=False,
    ):
        """Return an entity instance based on its ID and a project name.

        Raise ValueError if project_name or base_id is not valid.
        Raise KeyError if the folder does not exists.

        Set for_update=True and pass a transaction to lock the row
        for update.
        """

        project_name = project_name.lower()

        query = f"""
            SELECT  *
            FROM project_{project_name}.{cls.entity_type}s
            WHERE id=$1
            {'FOR UPDATE' if transaction and for_update else ''}
            """

        async for record in Postgres.iterate(query, entity_id):
            return cls.from_record(project_name, record, validate=False)
        raise NotFoundException("Entity not found")

    #
    # Save
    #

    async def save(self, transaction=None) -> bool:
        """Save the entity to the database.

        Supports both creating and updating. Entity must be loaded from the
        database in order to update. If the entity is not loaded, it will be
        created.

        Returns True if the folder was successfully saved.

        Optional `transaction` argument may be specified to pass a connection object,
        to run the query in (to run multiple transactions). When used,
        Entity.commit method is not called automatically and it is expected
        it is called at the end of the transaction block.
        """

        commit = not transaction
        transaction = transaction or Postgres

        attrib = {}
        for key in self.own_attrib:
            if (value := getattr(self.attrib, key)) is not None:
                attrib[key] = value

        if self.exists:
            # Update existing entity

            fields = dict_exclude(
                self.dict(exclude_none=True),
                ["id", "ctime"] + self.model.dynamic_fields,
            )
            fields["attrib"] = attrib

            await transaction.execute(
                *SQLTool.update(
                    f"project_{self.project_name}.{self.entity_type}s",
                    f"WHERE id = '{self.id}'",
                    **fields,
                )
            )
            if commit:
                await self.commit(transaction)
            return True

        # Create a new entity
        try:
            fields = dict_exclude(
                self.dict(exclude_none=True),
                self.model.dynamic_fields,
            )
            fields["attrib"] = attrib

            await transaction.execute(
                *SQLTool.insert(
                    f"project_{self.project_name}.{self.entity_type}s",
                    **fields,
                )
            )
        except Postgres.ForeignKeyViolationError as e:
            raise ConstraintViolationException(e.detail)

        except Postgres.UniqueViolationError as e:
            raise ConstraintViolationException(e.detail)

        if commit:
            await self.commit(transaction)
        return True

    #
    # Delete
    #

    async def delete(self, transaction=None) -> bool:
        """Delete an existing entity."""
        if not self.id:
            raise NotFoundException(f"Unable to delete unloaded {self.entity_type}.")

        commit = not transaction
        transaction = transaction or Postgres
        res = await transaction.fetch(
            f"""
            WITH deleted AS (
                DELETE FROM project_{self.project_name}.{self.entity_type}s
                WHERE id=$1
                RETURNING *
            ) SELECT count(*) FROM deleted;
            """,
            self.id,
        )
        count = res[0]["count"]

        if commit:
            await self.commit(transaction)
        return not not count

    #
    # Properties
    #

    @property
    def id(self) -> str:
        """Return the entity id."""
        return self._payload.id

    @id.setter
    def id(self, value: str):
        """Set the entity id."""
        self._payload.id = value
