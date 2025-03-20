from typing import Annotated

from fastapi import Query

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.api.responses import EmptyResponse
from ayon_server.entities import ProjectEntity
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.types import USER_NAME_REGEX

from .models import TeamListItemModel, TeamMemberModel, TeamModel, TeamPutModel
from .router import router


def dep_team_name(
    team_name: str = Query(min_length=2, max_length=64, title="Team Name"),
) -> str:
    return team_name


TeamName = Annotated[str, dep_team_name]


def dep_member_name(
    member_name: str = Query(title="User Name", regex=USER_NAME_REGEX),
) -> str:
    return member_name


MemberName = Annotated[str, dep_member_name]


@router.get("", response_model_exclude_none=True)
async def get_teams(
    project_name: ProjectName,
    current_user: CurrentUser,
    show_members: bool = Query(False),
) -> list[TeamListItemModel]:
    """Get all teams in a project."""
    project = await ProjectEntity.load(project_name)

    if current_user.is_guest:
        return []

    teams: list[TeamListItemModel] = []
    for team_data in project.data.get("teams", []):
        team = TeamModel(**team_data)

        members: list[TeamMemberModel] | None = None
        if show_members:
            members = [
                TeamMemberModel(
                    name=member.name,
                    leader=member.leader,
                    roles=member.roles,
                )
                for member in team.members
            ]

        team_item = TeamListItemModel(
            name=team.name,
            member_count=len(team.members),
            leaders=[
                TeamMemberModel(
                    name=member.name,
                    leader=member.leader,
                    roles=member.roles,
                )
                for member in team.members
                if member.leader
            ],
            members=members,
        )
        teams.append(team_item)
    return teams


@router.put("/{team_name}", status_code=204)
async def save_team(
    team_name: TeamName,
    team: TeamPutModel,
    project_name: ProjectName,
    current_user: CurrentUser,
) -> EmptyResponse:
    """Save a team."""

    if not current_user.is_manager:
        raise ForbiddenException("Only managers can update teams")

    project = await ProjectEntity.load(project_name)
    existing_teams = project.data.get("teams", [])

    # Remove existing team with the same name
    existing_teams = [
        existing_team
        for existing_team in existing_teams
        if existing_team["name"] != team_name
    ]

    # Add new team
    new_team_data = team.dict(exclude_unset=True)
    new_team_data["name"] = team_name
    existing_teams.append(new_team_data)

    project.data["teams"] = existing_teams
    await project.save()
    return EmptyResponse()


@router.put("/{team_name}/members/{member_name}", status_code=204)
async def save_team_member(
    team_name: TeamName,
    member_name: str,
    member: TeamMemberModel,
    project_name: ProjectName,
    current_user: CurrentUser,
) -> EmptyResponse:
    """Save a team member."""

    if not current_user.is_manager:
        raise ForbiddenException("Only managers can update teams")

    project = await ProjectEntity.load(project_name)
    existing_teams = project.data.get("teams", [])

    # Find existing team
    existing_team = next(
        (
            existing_team
            for existing_team in existing_teams
            if existing_team["name"] == team_name
        ),
        None,
    )
    if not existing_team:
        raise NotFoundException("Team not found")

    # Remove existing member with the same name
    existing_team["members"] = [
        existing_member
        for existing_member in existing_team["members"]
        if existing_member["name"] != member_name
    ]

    # Add new member
    new_member_data = member.dict(exclude_unset=True)
    new_member_data["name"] = member_name
    existing_team["members"].append(new_member_data)

    project.data["teams"] = existing_teams
    await project.save()
    return EmptyResponse()


@router.delete("/{team_name}", status_code=204)
async def delete_team(
    team_name: TeamName,
    project_name: ProjectName,
    current_user: CurrentUser,
) -> EmptyResponse:
    """Delete a team."""

    if not current_user.is_manager:
        raise ForbiddenException("Only managers can update teams")

    if current_user.is_guest:
        raise ForbiddenException("Guests cannot update teams")

    project = await ProjectEntity.load(project_name)
    existing_teams = project.data.get("teams", [])

    # Remove existing team with the same name
    existing_teams = [
        existing_team
        for existing_team in existing_teams
        if existing_team["name"] != team_name
    ]

    project.data["teams"] = existing_teams
    await project.save()
    return EmptyResponse()


@router.delete("/{team_name}/members/{member_name}", status_code=204)
async def delete_team_member(
    team_name: TeamName,
    member_name: MemberName,
    project_name: ProjectName,
    current_user: CurrentUser,
) -> EmptyResponse:
    """Delete a team member."""

    if not current_user.is_manager:
        raise ForbiddenException("Only managers can update teams")

    if current_user.is_guest:
        raise ForbiddenException("Guests cannot update teams")

    project = await ProjectEntity.load(project_name)
    existing_teams = project.data.get("teams", [])

    # Find existing team
    existing_team = next(
        (
            existing_team
            for existing_team in existing_teams
            if existing_team["name"] == team_name
        ),
        None,
    )
    if not existing_team:
        raise NotFoundException("Team not found")

    # Remove existing member with the same name
    existing_team["members"] = [
        existing_member
        for existing_member in existing_team["members"]
        if existing_member["name"] != member_name
    ]

    project.data["teams"] = existing_teams
    await project.save()
    return EmptyResponse()


@router.patch("", status_code=204)
async def update_teams(
    project_name: ProjectName,
    current_user: CurrentUser,
    payload: list[TeamModel],
) -> EmptyResponse:
    """Update teams."""

    if not current_user.is_manager:
        raise ForbiddenException("Only managers can update teams")

    if current_user.is_guest:
        raise ForbiddenException("Guests cannot update teams")

    project = await ProjectEntity.load(project_name)
    existing_teams = project.data.get("teams", [])

    new_names = [team.name.lower() for team in payload]

    # remove old existing existing_teams

    existing_teams = [
        existing_teams
        for existing_teams in existing_teams
        if existing_teams["name"].lower() not in new_names
    ]

    for new_team in payload:
        existing_teams.append(new_team.dict())

    project.data["teams"] = existing_teams

    await project.save()
    return EmptyResponse()
