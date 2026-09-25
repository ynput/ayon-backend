"""Attribute values of entities.

All the rules for stored attribute values live here, so REST (entities),
GraphQL, the inherited attributes and the maintenance tools use the same ones.
Values are validated when they are written. Stored values are trusted.

- `invalid_attrib` - which stored values are not valid
- `validate_attrib` - strict validation of written values
- `resolve_attrib` - values of an entity including the inherited ones
"""

__all__ = [
    "INHERITING_ENTITY_TYPES",
    "ResolvedAttrib",
    "invalid_attrib",
    "resolve_attrib",
    "validate_attrib",
]

from .common import INHERITING_ENTITY_TYPES
from .invalid import invalid_attrib
from .resolve import ResolvedAttrib, resolve_attrib
from .validate import validate_attrib
