__all__ = ["EntityID"]

import re
import uuid
from typing import Any, Literal, TypedDict, overload

from pydantic import Field

from .hashing import create_uuid


class EntityIDMeta(TypedDict):
    example: str
    min_length: int
    max_length: int
    regex: str


_ENTITY_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


class EntityID:
    example: str = "af10c8f0e9b111e9b8f90242ac130003"
    META: dict[str, Any] = {
        "example": "af10c8f0e9b111e9b8f90242ac130003",
        "min_length": 32,
        "max_length": 32,
        "regex": r"^[0-9a-f]{32}$",
    }

    @classmethod
    def create(cls) -> str:
        return create_uuid()

    @overload
    @classmethod
    def parse(
        cls,
        entity_id: str | uuid.UUID | None,
        allow_nulls: Literal[False] = False,
    ) -> str: ...

    @overload
    @classmethod
    def parse(
        cls,
        entity_id: str | uuid.UUID | None,
        allow_nulls: bool,
    ) -> str | None: ...

    @classmethod
    def parse(
        cls,
        entity_id: str | uuid.UUID | None,
        allow_nulls: bool = False,
    ) -> str | None:
        """Convert UUID object or its string representation to string

        Returns 32 lowercase hex characters. Raises ValueError
        if the value is not a valid UUID.
        """
        if entity_id is None and allow_nulls:
            return None
        if isinstance(entity_id, uuid.UUID):
            return entity_id.hex
        if isinstance(entity_id, str):
            _entity_id = entity_id.replace("-", "").lower()
            if _ENTITY_ID_PATTERN.fullmatch(_entity_id):
                return _entity_id
        raise ValueError(f"Invalid entity ID {entity_id}")

    @classmethod
    def field(cls, name: str = "entity") -> Field:  # type: ignore
        return Field(  # type: ignore
            title=f"{name.capitalize()} ID",
            description=f"{name.capitalize()} ID",
            **cls.META,
        )
