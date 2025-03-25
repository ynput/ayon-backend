import re
from typing import Any

from ayon_server.entities.user import UserEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Connection, Postgres
from ayon_server.types import PROJECT_NAME_REGEX
from ayon_server.utils import create_uuid

from .models import EntityListConfig
from .summary import EntityListSummary, get_entity_list_summary


async def create_entity_list(
    project_name: str,
    label: str,
    *,
    id: str | None = None,
    tags: list[str] | None = None,
    attrib: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    access: dict[str, Any] | None = None,
    config: dict[str, Any] | EntityListConfig | None = None,
    template: dict[str, Any] | None = None,
    user: UserEntity | None = None,
    sender: str | None = None,
    sender_type: str | None = None,
    conn: Connection | None = None,
) -> EntityListSummary:
    # Populate default values

    if id is None:
        id = create_uuid()
    if access is None:
        access = {}
    if attrib is None:
        attrib = {}
    if tags is None:
        tags = []
    if data is None:
        data = {}
    if template is None:
        template = {}

    if config is None:
        config_obj = EntityListConfig()
    elif isinstance(config, EntityListConfig):
        config_obj = config
    else:
        config_obj = EntityListConfig(**config)

    # Sanity checks

    if not re.match(PROJECT_NAME_REGEX, project_name):
        raise BadRequestException(f"Invalid project name {project_name}")

    query = """
        INSERT INTO entity_lists
        (id, label, config, owner, access, template, attrib, data, tags)
        VALUES
        ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    """
    args = (
        id,
        label,
        config_obj.dict(),
        user.name if user else None,
        access,
        template,
        attrib,
        data,
        tags,
    )

    # Create a transaction if none is provided

    async def execute_transaction(conn: Connection) -> EntityListSummary:
        await conn.execute(f"SET LOCAL search_path TO project_{project_name}")
        await conn.execute(query, *args)
        return await get_entity_list_summary(conn, project_name, id)
        return summary

    if conn is None:
        async with Postgres.acquire() as conn, conn.transaction():
            summary = await execute_transaction(conn)
    else:
        summary = await execute_transaction(conn)

    await EventStream.dispatch(
        "entity_list.created",
        description=f"Entity list '{label}' created",
        summary=dict(summary),
        project=project_name,
        user=user.name if user else None,
        sender=sender,
        sender_type=sender_type,
    )
    return summary
