from typing import Any

from ayon_server.api.dependencies import (
    CurrentUser,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.api.responses import EntityIdResponse
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid

from .router import router

FAKE_LIST_ID = "56015c91278641a2a8b14bafee00b9e7"


@router.get("/{list_id}", response_model_exclude_none=True)
async def get_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
) -> Any:
    list_id = FAKE_LIST_ID

    return list_id


#
# [POST]
#


async def collect_versions_from_reviewables(project_name: ProjectName) -> list[str]:
    """This is used to create a testing list
    The list contains version with published reviewables,
    so it can be used to test... well... lists of versions with reviewable
    """
    result = []

    query = f"""
        SELECT entity_id FROM project_{project_name}.activity_feed
        WHERE
            entity_type = 'version'
        AND activity_type = 'reviewable'
        AND reference_type = 'origin'
        ORDER BY created_at ASC
        LIMIT 10
    """
    async for row in Postgres.iterate(query):
        result.append(row["entity_id"])
    return result


async def create_fake_list(project_name: ProjectName, user_name: str) -> str:
    """Create testing entity list and return its id"""
    list_id = FAKE_LIST_ID

    version_ids = await collect_versions_from_reviewables(project_name)

    async with Postgres.acquire() as conn, conn.transaction():
        await conn.execute(f"SET SEARCH_PATH TO project_{project_name}")
        await conn.execute(
            """
            INSERT INTO entity_lists
                (id, label, list_type, owner, created_by, updated_by)
            VALUES ($1, 'Fake List', 'Fake List', $2, $2, $2)
        """,
            list_id,
            user_name,
        )
        for position, version_id in enumerate(version_ids):
            await conn.execute(
                """
                INSERT INTO entity_list_items
                    (id, entity_list_id, entity_type, entity_id,
                    position, created_by, updated_by)
                VALUES ($1, $2, $3, $4, $5, $6, $6)
            """,
                create_uuid(),
                list_id,
                "version",
                version_id,
                position,
                user_name,
            )

    return list_id


@router.post("", status_code=201)
async def create_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
) -> EntityIdResponse:
    """Create a new entity list."""

    list_id = await create_fake_list(project_name, user.name)

    return EntityIdResponse(id=list_id)
