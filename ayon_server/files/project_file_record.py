from typing import Any

from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid


async def create_project_file_record(
    project_name: str,
    file_name: str,
    *,
    size: int,
    file_id: str | None = None,
    activity_id: str | None = None,
    content_type: str | None = None,
    user_name: str | None = None,
    additional_data: dict[str, Any] | None = None,
) -> str:
    if file_id:
        file_id = file_id.replace("-", "")
        if len(file_id) != 32:
            raise BadRequestException("Invalid file ID")
    else:
        file_id = create_uuid()

    if not content_type:
        content_type = "application/octet-stream"

    data = {
        "filename": file_name,
        "mime": content_type,
    }
    if additional_data:
        data.update(additional_data)

    await Postgres.execute(
        f"""
        INSERT INTO project_{project_name}.files
        (id, size, author, activity_id, data)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (id) DO UPDATE
        SET
            size = $2,
            author = COALESCE(EXCLUDED.author, $3),
            activity_id = $4,
            data = project_{project_name}.files.data || EXCLUDED.data
        """,
        file_id,
        size,
        user_name,
        activity_id,
        data,
    )

    return file_id
