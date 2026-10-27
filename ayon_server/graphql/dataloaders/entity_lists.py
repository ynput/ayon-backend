import asyncio
from typing import Any

from ayon_server.entities import ProjectEntity, UserEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.graphql.nodes.common import EntityListInfo
from ayon_server.graphql.resolvers.common import EntityVisibility
from ayon_server.graphql.types import Info
from ayon_server.helpers.entity_access import EntityAccessHelper
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import SQLTool

from . import KeyType, get_project_name


async def entity_lists_by_entity_loader(
    keys: list[KeyType],
) -> list[list[dict[str, Any]]]:
    """Load the entity lists containing each of the given entities.
    keys must be a list of tuples (project_name, entity_id) and project_name
    values must be the same!
    """

    result_dict: dict[KeyType, list[dict[str, Any]]] = {k: [] for k in keys}
    project_name = get_project_name(keys)

    query = f"""
        SELECT
            items.entity_id,
            items.item_ids,
            lists.id,
            lists.label,
            lists.entity_list_type,
            lists.entity_type,
            lists.active,
            lists.owner,
            lists.access
        FROM project_{project_name}.entity_lists AS lists
        JOIN (
            SELECT
                entity_list_id,
                entity_id,
                array_agg(id ORDER BY position) AS item_ids
            FROM project_{project_name}.entity_list_items
            WHERE entity_id IN {SQLTool.id_array([k[1] for k in keys])}
            GROUP BY entity_list_id, entity_id
        ) AS items
        ON items.entity_list_id = lists.id
        ORDER BY lists.label, lists.creation_order
        """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["entity_id"])))
        result_dict[key].append(dict(record))
    return [result_dict[k] for k in keys]


async def can_read_entity_list(
    user: UserEntity,
    project: ProjectEntity,
    record: dict[str, Any],
) -> bool:
    """Same rules as project.entityLists, including guest access."""

    access = record["access"] or {}
    if user.is_guest:
        if user.data.get("guestAccess"):
            return bool(
                user.get_guest_access(
                    project_name=project.name,
                    type="entityList",
                    id=str(record["id"]),
                )
            )
        if (
            access.get(f"guest:{user.attrib.email}") is None
            and int(access.get("__guests__") or 0) <= 0
        ):
            return False

    try:
        await EntityAccessHelper.check(
            user,
            access=access,
            level=EntityAccessHelper.READ,
            owner=record["owner"],
            project=project,
            default_open=True,
        )
    except ForbiddenException:
        return False
    return True


async def get_request_project(info: Info, project_name: str) -> ProjectEntity:
    project = info.context.get("project")
    if project is not None and project.name == project_name:
        return project

    loads: dict[str, asyncio.Task[ProjectEntity]]
    loads = info.context.setdefault("entity_lists_projects", {})
    if project_name not in loads:
        loads[project_name] = asyncio.create_task(ProjectEntity.load(project_name))
    return await loads[project_name]


async def get_entity_lists_info(
    root,
    info: Info,
    visibility: EntityVisibility = EntityVisibility.ALL,
    entity_list_types: list[str] | None = None,
) -> list[EntityListInfo]:
    project_name = root.project_name
    user = info.context["user"]

    loader = info.context["entity_lists_by_entity_loader"]
    records = await loader.load((project_name, root.id))
    if not records:
        return []
    project = await get_request_project(info, project_name)

    # shared by all nodes of the request, which resolve concurrently
    checks: dict[tuple[str, str], asyncio.Task[bool]]
    checks = info.context.setdefault("entity_list_read_checks", {})

    result: list[EntityListInfo] = []
    for record in records:
        if visibility == EntityVisibility.VISIBLE and not record["active"]:
            continue
        if visibility == EntityVisibility.HIDDEN and record["active"]:
            continue
        if entity_list_types and record["entity_list_type"] not in entity_list_types:
            continue

        key = (project_name, str(record["id"]))
        if key not in checks:
            checks[key] = asyncio.create_task(
                can_read_entity_list(user, project, record)
            )
        if not await checks[key]:
            continue

        result.append(
            EntityListInfo(
                id=str(record["id"]),
                label=record["label"],
                entity_list_type=record["entity_list_type"],
                entity_type=record["entity_type"],
                active=record["active"],
                item_ids=[str(item_id) for item_id in record["item_ids"]],
            )
        )
    return result
