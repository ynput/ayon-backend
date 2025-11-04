import builtins
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel
from strawberry.experimental.pydantic import type as pydantic_type

from ayon_server.entities.core.patch import apply_patch
from ayon_server.entities.models import ModelSet
from ayon_server.exceptions import ForbiddenException

if TYPE_CHECKING:
    from ayon_server.entities.user import UserEntity

ALWAYS_WRITABLE_ATTRS: list[str] = []
ALWAYS_WRITABLE_FIELDS: list[str] = ["thumbnail_id"]


class BaseEntity:
    entity_type: str
    model: ModelSet
    exists: bool = False
    project_name: str | None = None
    own_attrib: list[str] = []
    inherited_attrib: dict[str, Any] = {}
    _payload: BaseModel

    def __repr__(self):
        return f"<{self.entity_type} {self.name}>"

    def __bool__(self) -> bool:
        return bool(self._payload)

    def dict(
        self,
        exclude_defaults: bool = False,
        exclude_unset: bool = False,
        exclude_none: bool = False,
    ) -> dict[str, Any]:
        """Return the entity data as a dict."""
        return self._payload.dict(
            exclude_defaults=exclude_defaults,
            exclude_unset=exclude_unset,
            exclude_none=exclude_none,
        )

    def dict_simple(self) -> builtins.dict[str, Any]:
        """Return the entity data as a dict.
        Use aliases instead of the original field names
        and drop inherited attributes.
        """
        result = self._payload.dict(exclude_none=True, by_alias=True)
        attrib = result.pop("attrib", {})
        for key in list(attrib.keys()):
            if key not in self.own_attrib:
                attrib.pop(key)
        result["attrib"] = attrib
        result.pop("ownAttrib", None)
        return result

    #
    # Modification
    #

    def patch(self, patch_data: BaseModel, user: Optional["UserEntity"] = None) -> None:
        """Apply a patch to the entity."""

        pdata = patch_data.dict(exclude_unset=True)
        pattr = pdata.pop("attrib", {})  # attributes to be patched

        if user is not None and hasattr(self, "project_name"):
            if not (user.is_manager):
                # If a normal user tries to patch a project-level entity,
                # we need to check what attributes are being modified.
                # and if the user is allowed to do so.
                patch_data = patch_data.copy(deep=True)
                perms = user.permissions(self.project_name)

                if not user.is_developer and "developerMode" in pattr:
                    patch_data.attrib.developerMode = None  # type: ignore

                if perms.attrib_write.enabled:
                    writable_attrs = (
                        perms.attrib_write.attributes + ALWAYS_WRITABLE_ATTRS
                    )
                    writable_fields = perms.attrib_write.fields + ALWAYS_WRITABLE_FIELDS

                    for attr, val in pattr.items():
                        if getattr(self.attrib, attr) == val:
                            continue
                        if attr not in writable_attrs:
                            raise ForbiddenException(
                                f"You are not allowed to modify {attr}"
                                f" attribute in {self.project_name}"
                            )

                    for field_name, val in pdata.items():
                        if getattr(self._payload, field_name, None) == val:
                            continue
                        if field_name not in writable_fields:
                            raise ForbiddenException(
                                f"You are not allowed to modify {field_name}"
                                f" field in {self.project_name}"
                            )

        # list of attributes that will need to be set to inherited
        # after applying the patch
        inherit_list = set()

        if pattr:
            for key in pattr:
                if pattr.get(key) is None:
                    inherit_list.add(key)
                    continue
                if key in self.own_attrib:
                    continue
                self.own_attrib.append(key)
        self._payload = apply_patch(self._payload, patch_data)

        for attr in inherit_list:
            if attr in self.own_attrib:
                self.own_attrib.remove(attr)
            # Revert the attrib value to the value inherited from parent
            # (if available)
            if attr in self.inherited_attrib:
                setattr(self._payload.attrib, attr, self.inherited_attrib[attr])  # type: ignore

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

    async def commit(self):
        """Post-update commit.

        This method is called after the entity is saved to the database.
        It contains caches cleanup, hierarchy rebuilds, etc.

        This method should be overridden in subclasses and it is separated
        from the actual save logic in order to allow calling it only
        once after multiple operations. The logic of this method should
        not depend on the entity being saved, but the entity type (and
        project name if applicable) should be known.
        """
        pass

    #
    # Properties
    #

    @property
    def name(self) -> str:
        return self._payload.name  # type: ignore

    @name.setter
    def name(self, value: str) -> None:
        self._payload.name = value  # type: ignore

    @property
    def attrib(self):
        """Return the entity attributes."""
        return self._payload.attrib  # type: ignore

    @property
    def data(self) -> builtins.dict[str, Any]:
        return self._payload.data  # type: ignore

    @data.setter
    def data(self, value: builtins.dict[str, Any]) -> None:
        self._payload.data = value  # type: ignore

    @property
    def active(self) -> bool:
        return self._payload.active  # type: ignore

    @active.setter
    def active(self, value) -> None:
        self._payload.active = value  # type: ignore

    @property
    def created_at(self) -> float:
        return self._payload.created_at  # type: ignore

    @created_at.setter
    def created_at(self, value: float) -> None:
        self._payload.created_at = value  # type: ignore

    @property
    def updated_at(self) -> float:
        return self._payload.updated_at  # type: ignore

    @updated_at.setter
    def updated_at(self, value: float) -> None:
        self._payload.updated_at = value  # type: ignore
