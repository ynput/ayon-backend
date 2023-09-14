from typing import TYPE_CHECKING, Any, Dict, Optional

from pydantic import BaseModel
from strawberry.experimental.pydantic import type as pydantic_type

from ayon_server.entities.core.patch import apply_patch
from ayon_server.entities.models import ModelSet

if TYPE_CHECKING:
    from ayon_server.entities.user import UserEntity


class BaseEntity:
    entity_type: str
    model: ModelSet
    exists: bool = False
    own_attrib: list[str] = []
    _payload: BaseModel

    def __repr__(self):
        return f"<{self.entity_type} {self.name}>"

    def __bool__(self) -> bool:
        return bool(self._payload)

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

    def patch(self, patch_data: BaseModel, user: Optional["UserEntity"] = None) -> None:
        """Apply a patch to the entity."""

        if user is not None and hasattr(self, "project_name"):
            if not (user.is_manager):
                # If a normal user tries to patch a project-level entity,
                # we need to check what attributes are being modified.
                # and if the user is allowed to do so.
                patch_data = patch_data.copy(deep=True)
                user.permissions(self.project_name)

                # TODO: check for attribute whitelist
                # and drop any attributes that are not allowed
                # from the patch data.

        if (attrib := patch_data.dict().get("attrib")) is not None:
            for key in attrib:
                if attrib.get(key) is None:
                    continue
                if key in self.own_attrib:
                    continue
                self.own_attrib.append(key)
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

    @property
    def created_by(self) -> str | None:
        return self._payload.data.get("createdBy")

    @created_by.setter
    def created_by(self, value: str) -> None:
        self._payload.data["createdBy"] = value

    @property
    def updated_by(self) -> str | None:
        return self._payload.data.get("updatedBy")

    @updated_by.setter
    def updated_by(self, value: str) -> None:
        self._payload.data["updatedBy"] = value
