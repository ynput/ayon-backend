from typing import Any

from openpype.entities.core.base import BaseEntity


class TopLevelEntity(BaseEntity):
    def __init__(
        self,
        payload: dict[str, Any],
        exists: bool = False,
        validate: bool = True,
    ) -> None:
        """Return a new entity instance from given data."""

        if validate:
            self._payload = self.model.main_model(**payload)
        else:
            self._payload = self.model.main_model.construct(**payload)
        self.exists = exists

    @classmethod
    def from_record(cls, payload: dict[str, Any], validate=False):
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
        return cls(parsed, exists=True, validate=False)

    def as_user(self, user):
        # TODO
        return self._payload.copy()

    #
    # Properties
    #

    @property
    def name(self) -> str:
        return self._payload.name

    @name.setter
    def name(self, value: str) -> None:
        self._payload.name = value
