from ayon_server.types import ProjectLevelEntityType


async def get_watchers_list(
    project_name: str, entity_type: ProjectLevelEntityType, entity_id: str
) -> list[str]:
    """Get watchers of an entity."""

    watchers: list[str] = []

    return watchers


async def set_watchers_list(
    project_name: str,
    entity_type: ProjectLevelEntityType,
    entity_id: str,
    watchers: list[str],
    *,
    sender: str | None = None,
) -> None:
    """Set watchers of an entity."""
