"""Base Entity class from which all other entities inherit.
"""

import asyncio
import collections
import copy
import enum
import threading
import time
from typing import Any, Dict, Optional

from nxtools import logging
from pydantic import BaseModel
from strawberry.experimental.pydantic import type as pydantic_type

from openpype.entities.models import ModelSet
from openpype.exceptions import ConstraintViolationException, RecordNotFoundException
from openpype.lib.postgres import Postgres
from openpype.utils import EntityID, SQLTool, dict_exclude, json_loads


class AttributeLibrary:
    """Dynamic attributes loader class.

    This is very wrong and i deserve a punishment for this,
    but it works. Somehow. It needs to be initialized when
    this module is loaded and it has to load the attributes
    from the database in blocking mode regardless the running
    event loop. So it connects to the DB independently in a
    different thread and waits until it is finished.

    Attribute list for each entity type may be then accessed
    using __getitem__ method.
    """

    def __init__(self):
        self.data = collections.defaultdict(list)
        _thread = threading.Thread(target=self.execute)
        _thread.start()
        _thread.join()

    def execute(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.load())
        loop.close()

    async def load(self):
        query = "SELECT name, scope, data from public.attributes"
        await Postgres.connect()
        async for row in Postgres.iterate(query):
            attrd = {"name": row["name"], **json_loads(row["data"])}
            for scope in row["scope"]:
                self.data[scope].append(attrd)

    def __getitem__(self, key):
        return self.data[key]


attribute_library = AttributeLibrary()


def apply_patch(original: BaseModel, patch: BaseModel) -> BaseModel:
    """Patch (partial update) an entity using its patch model."""
    update_data = {}

    for key, value in patch.dict(exclude_unset=True).items():
        if key not in original.__fields__:
            continue

        if isinstance(getattr(original, key), BaseModel):
            # Patch a submodel (attrib)
            ndata = apply_patch(
                getattr(original, key), getattr(original, key).__class__(**value)
            )
            update_data[key] = ndata

        elif type(getattr(original, key)) == dict:
            # Patch arbitrary dict (one level only!)
            if type(value) == dict:
                new_dict = copy.deepcopy(getattr(original, key))
                for dkey, dval in value.items():
                    if dval is None:
                        if dkey in new_dict:
                            del new_dict[dkey]
                    else:
                        new_dict[dkey] = dval
                update_data[key] = new_dict
            else:
                logging.error(f"Unable to patch. {key} only accepts dict")

        else:
            # Patch scalar types such as ints, strings and booleans
            update_data[key] = value

    if "updated_at" in original.__fields__:
        update_data["updated_at"] = int(time.time())

    updated_model = original.copy(update=update_data, deep=True)
    return updated_model


class EntityType(enum.IntEnum):
    UNDEFINED = 0
    PROJECT = 1
    FOLDER = 2
    SUBSET = 3
    VERSION = 4
    REPRESENTATION = 5
    TASK = 6
    USER = 7


class Entity:
    entity_type = EntityType.UNDEFINED
    entity_name: str
    model: ModelSet

    def __init__(
        self,
        project_name: str | None = None,
        exists: bool = False,
        validate: bool = True,
        **kwargs,
    ) -> None:
        """Return a new entity instance from given data.

        Entity data is stored in a pydantic model Entity._data,
        accessible via the "data" property.

        project_name: Name of the project to which the entity belongs
            (ignored in case of a project entity and user entity).
        exists: Set to True when the entity is loaded from the database.
        validate: Set to False to skip pydantic validation.
        **kwargs: Data to initialize the entity with.
        """

        self.exists = exists
        if validate:
            self._payload = self.model.main_model(**kwargs)
        else:
            self._payload = self.model.main_model.construct(**kwargs)

        if self.entity_type == EntityType.PROJECT:
            self.project_name = self.name or project_name
        elif self.entity_type == EntityType.USER:
            self.project_name = None
        else:
            self.project_name = project_name

    @classmethod
    def from_record(cls, project_name=None, validate=False, **kwargs):
        """Return an entity instance based on a DB record.

        This factory method differs from the default constructor,
        # because it accepts a DB row data and de-serializes JSON fields
        and reformats ids.

        By default it does not validate the data, sice it is assumed the
        correct format is stored in the database.
        """
        project_name = project_name.lower() if project_name else None
        parsed = {}
        for key in cls.model.main_model.__fields__:
            if key not in kwargs:
                continue  # there are optional keys too
            value = kwargs[key]
            if key in ["data", "attrib", "config"]:
                parsed[key] = json_loads(kwargs[key])
            elif key == "id" or key.endswith("_id"):
                parsed[key] = EntityID.parse(value, allow_nulls=True)
            else:
                parsed[key] = value
        return cls(project_name=project_name, exists=True, validate=validate, **parsed)

    def __bool__(self) -> bool:
        return not not self._payload

    def __getattr__(self, key) -> Any:
        """Return the value of an attribute."""
        if key in self.dict():
            return self.dict()[key]
        raise AttributeError(f"{key} not found in {self.entity_name}")

    def get(self, key, default=None) -> Any:
        return self.dict().get(key, default)

    def dict(
        self, exclude_defaults=False, exclude_unset=False, exclude_none=False
    ) -> dict:
        """Return the entity data as a dict."""
        return self._payload.dict(
            exclude_defaults=exclude_defaults,
            exclude_unset=exclude_unset,
            exclude_none=exclude_none,
        )

    @property
    def payload(self):
        return self._payload

    #
    # Modification
    #

    def patch(self, patch_data: BaseModel) -> None:
        """Apply a patch to the entity."""
        self._payload = apply_patch(self._payload, patch_data)

    def replace(self, replace_data: BaseModel) -> None:
        """Replace entity data with given data."""
        if self.entity_type == EntityType.PROJECT:
            self._payload = self.model.main_model(name=self.name, **replace_data.dict())
        else:
            self._payload = self.model.main_model(id=self.id, **replace_data.dict())

    #
    # GraphQL types
    #

    @classmethod
    def strawberry_attrib(cls):
        fields = list(cls.model.attrib_model.__fields__.keys())
        return pydantic_type(model=cls.model.attrib_model, fields=fields)

    @classmethod
    def strawberry_entity(cls):
        """Return a strawberry type of the entity.

        Automatically exclude dict attributes.
        """
        return pydantic_type(
            model=cls.model.main_model,
            fields=[
                fname
                for fname, field in cls.model.main_model.__fields__.items()
                if field.type_ not in [dict, Optional[dict]]
            ],
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

        ProjectEntity reimplements this method to load the project based
        on the project name.

        Raise ValueError if project_name or base_id is not valid.
        Raise KeyError if the folder does not exists.

        Set for_update=True and pass a transaction to lock the row
        for update.
        """

        project_name = project_name.lower()

        query = f"""
            SELECT  *
            FROM project_{project_name}.{cls.entity_name}s
            WHERE id=$1
            {'FOR UPDATE' if transaction and for_update else ''}
            """

        async for record in Postgres.iterate(query, EntityID.parse(entity_id)):
            return cls.from_record(project_name=project_name, validate=False, **record)
        raise RecordNotFoundException("Entity not found")

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

        if self.exists:
            # Update existing entity

            await transaction.execute(
                *SQLTool.update(
                    f"project_{self.project_name}.{self.entity_name}s",
                    f"WHERE id = '{self.id}'",
                    **dict_exclude(
                        self.dict(exclude_none=True),
                        ["id", "ctime"] + self.model.dynamic_fields,
                    ),
                )
            )
            if commit:
                await self.commit(transaction)
            return True

        # Create a new entity
        try:
            await transaction.execute(
                *SQLTool.insert(
                    f"project_{self.project_name}.{self.entity_name}s",
                    **self.dict(exclude_none=True),
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
            raise RecordNotFoundException(
                f"Unable to delete unloaded {self.entity_name}."
            )

        commit = not transaction
        transaction = transaction or Postgres
        res = await transaction.fetch(
            f"""
            WITH deleted AS (
                DELETE FROM project_{self.project_name}.{self.entity_name}s
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

    async def commit(self, transaction=False):
        """Post-update commit."""
        pass

    #
    # Common properties
    #

    @property
    def active(self) -> bool:
        return self._payload.active

    @active.setter
    def active(self, value) -> None:
        self._payload.active = value

    @property
    def data(self) -> Dict[str, Any]:
        return self._payload.data

    @data.setter
    def data(self, value: Dict[str, Any]) -> None:
        self._payload.data = value

    @property
    def created_at(self) -> float:
        return self._payload.created_at

    @created_at.setter
    def created_at(self, value: float) -> None:
        self._payload.created_at = value

    @property
    def updated_at(self) -> float:
        return self._payload.updated_at

    @updated_at.setter
    def updated_at(self, value: float) -> None:
        self._payload.updated_at = value
