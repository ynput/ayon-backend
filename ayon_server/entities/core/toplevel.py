from typing import Any

from pydantic import BaseModel

from ayon_server.entities.core.base import BaseEntity


class TopLevelEntity(BaseEntity):
    def __init__(
        self,
        payload: dict[str, Any],
        exists: bool = False,
        validate: bool = True,  # deprecated
    ) -> None:
        """Return a new entity instance from given data."""

        self._init_payload(
            payload,
            exists=exists,
            label=f"{self.entity_type} {payload.get('name')}",
        )

    @classmethod
    def from_record(
        cls,
        payload: dict[str, Any],
        validate: bool = True,  # deprecated
    ):
        """Return an entity instance based on a DB record.

        This factory method differs from the default constructor,
        # because it accepts a DB row data and de-serializes JSON fields
        and reformats ids.
        """
        parsed = {}
        for key in cls.model.main_model.model_fields:
            if key not in payload:
                continue  # there are optional keys too
            parsed[key] = payload[key]
        return cls(parsed, exists=True)

    def as_user(self, user):
        # TODO
        return self._payload.model_copy()

    def replace(self, replace_data: BaseModel) -> None:
        """Replace entity data with given data."""
        self._payload = self.model.main_model(
            name=self.name, **replace_data.model_dump()
        )

    @property
    def created_by(self) -> str | None:
        return self._payload.data.get("createdBy")  # type: ignore

    @created_by.setter
    def created_by(self, value: str) -> None:
        self._payload.data["createdBy"] = value  # type: ignore

    @property
    def updated_by(self) -> str | None:
        return self._payload.data.get("updatedBy")  # type: ignore

    @updated_by.setter
    def updated_by(self, value: str) -> None:
        self._payload.data["updatedBy"] = value  # type: ignore

    async def commit(self):
        """Post-update commit."""
        await self.refresh_views()

    @classmethod
    async def refresh_views(cls) -> None:
        """Refresh the views for the entity type in the given project.

        This method should be overridden in subclasses to refresh.
        and should be called from commit() method after the entity is saved.
        """
        pass
