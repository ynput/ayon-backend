from datetime import datetime
from typing import Literal

from fastapi import Path

from ayon_server.activities.guest_access import ensure_guest_can_react
from ayon_server.api.dependencies import (
    ActivityID,
    AllowGuests,
    CurrentUser,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.entities import UserEntity
from ayon_server.events.eventstream import EventStream
from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import NAME_REGEX, Field, OPModel

from .router import router


async def modify_reactions(
    project_name: str,
    activity_id: str,
    user: UserEntity,
    reaction: str,
    action: Literal["add", "remove"],
    *,
    sender: str | None = None,
    sender_type: str | None = None,
):
    """

    Reactions are stored in the activity data as a list of dicts
    with the following structure:

    {
        "reaction": "like",
        "userName": "user1",
        "fullName": "User One",
        "timestamp": "2024-10-01T12:00:00Z"
    }


    """
    async with Postgres.transaction():
        res = await Postgres.fetch(
            f"""
            SELECT activity_type, data
            FROM project_{project_name}.activities
            WHERE id = $1
            """,
            activity_id,
        )

        if not res:
            raise NotFoundException("Activity not found")
        activity_type = res[0]["activity_type"]

        # modify the reactions

        activity_data = res[0]["data"]
        reactions = activity_data.get("reactions", [])

        if action == "add":
            # check if the user has already reacted
            for r in reactions:
                if r["reaction"] == reaction and r["userName"] == user.name:
                    raise BadRequestException("Already reacted")

            reactions.append(
                {
                    "reaction": reaction,
                    "userName": user.name,
                    "fullName": user.attrib.fullName or None,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        elif action == "remove":
            reactions = [
                r
                for r in reactions
                if r["reaction"] != reaction or r["userName"] != user.name
            ]

        activity_data["reactions"] = reactions

        await Postgres.execute(
            f"""
            UPDATE project_{project_name}.activities
            SET data = $1
            WHERE id = $2
            """,
            activity_data,
            activity_id,
        )

        # load activity references (used to generate the event summary)

        references = await Postgres.fetch(
            f"""
            SELECT entity_id, entity_type, reference_type
            FROM project_{project_name}.activity_references
            WHERE activity_id = $1
            """,
            activity_id,
        )

        summary = {
            "activity_id": activity_id,
            "activity_type": activity_type,
            "references": [dict(r) for r in references],
        }

    await EventStream.dispatch(
        "activity.updated",
        project=project_name,
        description="",
        summary=summary,
        store=False,
        user=user.name,
        sender=sender,
        sender_type=sender_type,
    )


#
# REST API
#


class CreateReactionModel(OPModel):
    reaction: str = Field(..., description="The reaction to be created", example="like")


@router.post(
    "/activities/{activity_id}/reactions",
    status_code=201,
    dependencies=[AllowGuests],
)
async def create_reaction_to_activity(
    user: CurrentUser,
    project_name: ProjectName,
    activity_id: ActivityID,
    request: CreateReactionModel,
    sender: Sender,
    sender_type: SenderType,
):
    if user.is_guest:
        await ensure_guest_can_react(user, project_name, activity_id)

    await modify_reactions(
        project_name,
        activity_id,
        user,
        request.reaction,
        "add",
        sender=sender,
        sender_type=sender_type,
    )


@router.delete(
    "/activities/{activity_id}/reactions/{reaction}",
    status_code=204,
    dependencies=[AllowGuests],
)
async def delete_reaction_to_activity(
    user: CurrentUser,
    project_name: ProjectName,
    activity_id: ActivityID,
    sender: Sender,
    sender_type: SenderType,
    reaction: str = Path(
        ...,
        description="The reaction to be deleted",
        example="like",
        regex=NAME_REGEX,
    ),
):
    await modify_reactions(
        project_name,
        activity_id,
        user,
        reaction,
        "remove",
        sender=sender,
        sender_type=sender_type,
    )
