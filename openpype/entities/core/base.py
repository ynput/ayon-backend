from typing import Any, Dict

from pydantic import BaseModel
from strawberry.experimental.pydantic import type as pydantic_type

from openpype.entities.core.patch import apply_patch
from openpype.entities.models import ModelSet


class BaseEntity:
    entity_type: str
    model: ModelSet
    exists: bool = False
    _payload: BaseModel

    def __repr__(self):
        return f"<{self.entity_type} {self.name}>"

    def __bool__(self) -> bool:
        return not not self._payload

    def dict(
        self,
        exclude_defaults=False,
        exclude_unset=False,
        exclude_none=False,
    ) -> dict:
        """Return the entity data as a dict."""
        return self._payload.dict(
            exclude_defaults=exclude_defaults,
            exclude_unset=exclude_unset,
            exclude_none=exclude_none,
        )

    #
    # Modification
    #

    def patch(self, patch_data: BaseModel) -> None:
        """Apply a patch to the entity."""
        self._payload = apply_patch(self._payload, patch_data)

    @property
    def payload(self) -> BaseModel:
        return self._payload

    @classmethod
    def strawberry_attrib(cls):
        fields = list(cls.model.attrib_model.__fields__.keys())
        return pydantic_type(model=cls.model.attrib_model, fields=fields)

    #
    # DB
    #

    async def commit(self, transaction=False):
        """Post-update commit."""
        pass

    #
    # Properties
    #

    @property
    def name(self) -> str:
        return self._payload.name

    @name.setter
    def name(self, value: str):
        self._payload.name = value

    @property
    def attrib(self):
        """Return the entity attributes."""
        return self._payload.attrib

    @property
    def data(self) -> Dict[str, Any]:
        return self._payload.data

    @data.setter
    def data(self, value: Dict[str, Any]) -> None:
        self._payload.data = value

    @property
    def active(self) -> bool:
        return self._payload.active

    @active.setter
    def active(self, value) -> None:
        self._payload.active = value

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
