"""Attribute values of entities.

All the rules for stored attribute values live here, so REST (entities),
GraphQL, the inherited attributes and the CLI tools use the same ones:

- `invalid_attrib` - which stored values are not valid
- `valid_attrib` - stored values without the invalid ones
- `validate_attrib` - strict validation of written values
- `resolve_attrib` - values of an entity including the inherited ones
"""

__all__ = [
    "INHERITING_ENTITY_TYPES",
    "ResolvedAttrib",
    "invalid_attrib",
    "resolve_attrib",
    "valid_attrib",
    "validate_attrib",
]

from .common import INHERITING_ENTITY_TYPES
from .invalid import invalid_attrib
from .resolve import ResolvedAttrib, resolve_attrib
from .valid import valid_attrib
from .validate import validate_attrib
