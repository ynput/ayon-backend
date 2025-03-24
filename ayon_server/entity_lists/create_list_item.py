import re
from typing import Any

from ayon_server.entities.user import UserEntity
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Connection, Postgres
from ayon_server.types import PROJECT_NAME_REGEX, ProjectLevelEntityType
from ayon_server.utils import create_uuid


async def _create_list_item(
    conn: Connection,
    project_name: str,
    entity_list_id: str,
    entity_type: ProjectLevelEntityType,
    entity_id: str,
    position: int,
    *,
    id: str,
    attrib: dict[str, Any],
    data: dict[str, Any],
    tags: list[str],
    user: UserEntity | None = None,
    skip_schema_switching: bool = False,
):
    user_name = user.name if user else None

    if not skip_schema_switching:
        await conn.execute(f"SET LOCAL search_path TO project_{project_name}")
    await conn.execute(
        """
        INSERT INTO list_items
        (
          id, entity_list_id, entity_type, entity_id,
          position, attrib, data, tags, created_by, updated_by
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """,
        id,
        entity_list_id,
        entity_type,
        entity_id,
        position,
        attrib,
        data,
        tags,
        user_name,
        user_name,
    )


async def create_list_item(
    project_name: str,
    entity_list_id: str,
    entity_type: ProjectLevelEntityType,
    entity_id: str,
    position: int,
    *,
    id: str | None = None,
    attrib: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    user: UserEntity | None = None,
    conn: Connection | None = None,
    skip_schema_switching: bool = False,
) -> str:
    list_item_id = id or create_uuid()

    if not re.match(PROJECT_NAME_REGEX, project_name):
        raise BadRequestException(f"Invalid project name {project_name}")

    if attrib is None:
        attrib = {}
    if data is None:
        data = {}
    if tags is None:
        tags = []

    if conn is not None:
        await create_list_item(
            project_name,
            entity_list_id,
            entity_type,
            entity_id,
            position=position,
            id=list_item_id,
            attrib=attrib,
            data=data,
            tags=tags,
            user=user,
            skip_schema_switching=skip_schema_switching,
        )

    else:
        async with Postgres.acquire() as conn, conn.transaction():
            await create_list_item(
                project_name,
                entity_list_id,
                entity_type,
                entity_id,
                position=position,
                id=list_item_id,
                attrib=attrib,
                data=data,
                tags=tags,
                user=user,
                skip_schema_switching=False,
            )

    return list_item_id
