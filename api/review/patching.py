from typing import Any

from ayon_server.api.dependencies import ActivityID, CurrentUser, ProjectName, VersionID
from ayon_server.entities import VersionEntity
from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.reviewables.models import RESERVED_FILE_DATA_KEYS
from ayon_server.types import Field, OPModel
from ayon_server.utils.json import json_dumps

from .router import router


class SortReviewablesRequest(OPModel):
    sort: list[str] | None = Field(
        None,
        title="Reviewables Order",
        description="List of reviewable (activity) ids in the order "
        "you want them to appear in the UI.",
        example=[
            "c197712a48ef11ef95450242ac1f0004",
            "c519a3f448ef11ef95450242ac1f0004",
            "c8edce0648ef11ef95450242ac1f0004",
        ],
    )


REVIEWABLE_DATA_MAX_SIZE = 8 * 1024 * 1024


class UpdateReviewablesRequest(OPModel):
    label: str | None = Field(
        None,
        title="Reviewable Label",
        example="Shoulder detail",
    )
    data: dict[str, Any] | None = Field(
        None,
        title="Reviewable Data",
        description=(
            "Custom data of the reviewable (e.g. 'overlay' with burnins "
            "drawn by the player). Top-level keys are merged into the "
            "current data, a key with `null` value is removed. "
            "Keys managed by the server cannot be changed."
        ),
        example={"overlay": {"schema": "premium_burnins/1"}},
    )


@router.patch("/versions/{version_id}/reviewables")
async def sort_version_reviewables(
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    request: SortReviewablesRequest,
) -> None:
    """Change the order of reviewables of a given version.

    In the payload, provide a list of activity ids (reviewables)
    in the order you want them to appear in the UI.
    """
    async with Postgres.transaction():
        version = await VersionEntity.load(project_name, version_id)
        await version.ensure_update_access(user)

        res = await Postgres.fetch(
            f"""
            SELECT activity_id FROM project_{project_name}.activity_feed
            WHERE reference_type = 'origin'
            AND activity_type = 'reviewable'
            AND entity_type = 'version'
            AND entity_id = $1
            """,
            version_id,
        )

        if not res:
            raise NotFoundException(detail="Version not found")

        if request.sort is not None:
            valid_ids = {row["activity_id"] for row in res}
            requested_ids = set(request.sort)

            if requested_ids != valid_ids:
                logger.trace("Saved:", valid_ids)
                logger.trace("Requested:", requested_ids)
                raise BadRequestException(detail="Invalid reviewable ids")

            for i, activity_id in enumerate(request.sort):
                await Postgres.execute(
                    f"""
                    UPDATE project_{project_name}.activities
                    SET data = data || jsonb_build_object(
                        'reviewableOrder', $1::integer
                    )
                    WHERE id = $2
                    """,
                    i,
                    activity_id,
                )
    return None


@router.patch("/versions/{version_id}/reviewables/{activity_id}")
async def update_reviewable(
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    reviewable_id: ActivityID,
    request: UpdateReviewablesRequest,
) -> None:
    """Update an existing reviewable.

    It is possible to update the label and the custom data of a reviewable.
    The data is stored to all files of the reviewable, including files
    transcoded from it.
    """

    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_update_access(user)

    if request.label is not None:
        if not request.label:
            raise BadRequestException(detail="Label cannot be empty")
        if not isinstance(request.label, str):
            raise BadRequestException(detail="Label must be a string")
        if not 0 < len(request.label) <= 255:
            raise BadRequestException(
                detail="Label must be between 1 and 255 characters"
            )

    if request.data:
        await _update_reviewable_data(
            project_name, version_id, reviewable_id, request.data
        )

    if request.label is not None:
        await Postgres.execute(
            f"""
            UPDATE project_{project_name}.activities
            SET data = data || jsonb_build_object(
                'reviewableLabel', $1::text
            )
            WHERE id = $2
            """,
            request.label,
            reviewable_id,
        )


async def _update_reviewable_data(
    project_name: str,
    version_id: str,
    reviewable_id: str,
    data: dict[str, Any],
) -> None:
    reserved_keys = sorted(RESERVED_FILE_DATA_KEYS & data.keys())
    if reserved_keys:
        raise BadRequestException(
            detail=f"Data keys managed by the server cannot be changed: "
            f"{', '.join(reserved_keys)}"
        )

    if len(json_dumps(data)) > REVIEWABLE_DATA_MAX_SIZE:
        raise BadRequestException(
            detail="Data must be smaller than "
            f"{REVIEWABLE_DATA_MAX_SIZE // (1024 * 1024)} MB"
        )

    new_data = {key: value for key, value in data.items() if value is not None}
    removed_keys = [key for key, value in data.items() if value is None]

    # Update only files of the reviewable that belongs to the version
    res = await Postgres.fetch(
        f"""
        UPDATE project_{project_name}.files AS files
        SET data = (files.data || $3::jsonb) - $4::text[]
        FROM project_{project_name}.activity_feed AS af
        WHERE files.activity_id = af.activity_id
        AND af.activity_id = $2
        AND af.reference_type = 'origin'
        AND af.activity_type = 'reviewable'
        AND af.entity_type = 'version'
        AND af.entity_id = $1
        RETURNING files.id
        """,
        version_id,
        reviewable_id,
        new_data,
        removed_keys,
    )
    if not res:
        raise NotFoundException(detail="Reviewable not found")
