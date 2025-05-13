from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class MatchedEntity:
    operation: Literal["create", "update"]
    entity_type: Literal["folder", "task"]
    entity_id: str | None
    data: dict[str, Any]


async def match_entities(
    project_name: str,
    entities: list[dict[str, Any]],
) -> list[MatchedEntity]:
    """
    For a list of data, providing as much information as possible,
    resolve a list of operations to be performed.
    """
    result = []

    return result
