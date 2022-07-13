from typing import Any

from pydantic import BaseModel

from openpype.entities.core.base import BaseEntity
from openpype.utils import dict_exclude


class TopLevelEntity(BaseEntity):
    def __init__(
        self,
        payload: dict[str, Any],
        exists: bool = False,
        validate: bool = True,
    ) -> None:
        """Return a new entity instance from given data."""

        attrib_dict = payload.get("attrib", {})
        self.own_attrib = list(attrib_dict.keys())

        if validate:
            self._payload = self.model.main_model(**payload)
        else:
            attrib = self.model.attrib_model.construct(**payload.get("attrib", {}))
            self._payload = self.model.main_model.construct(
                attrib=attrib, **dict_exclude(payload, ["attrib"])
            )
        self.exists = exists

    @classmethod
    def from_record(cls, payload: dict[str, Any], validate: bool = True):
        """Return an entity instance based on a DB record.

        This factory method differs from the default constructor,
        # because it accepts a DB row data and de-serializes JSON fields
        and reformats ids.

        By default it does not validate the data, sice it is assumed the
        correct format is stored in the database.
        """
        parsed = {}
        for key in cls.model.main_model.__fields__:
            if key not in payload:
                continue  # there are optional keys too
            parsed[key] = payload[key]
        return cls(parsed, exists=True, validate=validate)

    def as_user(self, user):
        # TODO
        return self._payload.copy()

    def replace(self, replace_data: BaseModel) -> None:
        """Replace entity data with given data."""
        self._payload = self.model.main_model(name=self.name, **replace_data.dict())
