from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.api.responses import EmptyResponse
from ayon_server.entities import ProjectEntity
from ayon_server.exceptions import NotFoundException

from .models import TeamListItemModel, TeamMemberModel, TeamModel, TeamPutModel
from .router import router


@router.get("")
async def get_teams(
    project_name: ProjectName, current_user: CurrentUser
) -> list[TeamListItemModel]:
    """Get all teams in a project."""
    project = await ProjectEntity.load(project_name)
    teams: list[TeamListItemModel] = []
    for team_data in project.data.get("teams", []):
        team = TeamModel(**team_data)
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
        )
        teams.append(team_item)
    return teams


@router.put("/{team_name}")
async def save_team(
    team_name: str,
    team: TeamPutModel,
    project_name: ProjectName,
    current_user: CurrentUser,
) -> EmptyResponse:
    """Save a team."""
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


@router.put("/{team_name}/members/{member_name}")
async def save_team_member(
    team_name: str,
    member_name: str,
    member: TeamMemberModel,
    project_name: ProjectName,
    current_user: CurrentUser,
) -> EmptyResponse:
    """Save a team member."""
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


@router.delete("/{team_name}")
async def delete_team(
    team_name: str, project_name: ProjectName, current_user: CurrentUser
) -> EmptyResponse:
    """Delete a team."""
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


@router.delete("/{team_name}/members/{member_name}")
async def delete_team_member(
    team_name: str,
    member_name: str,
    project_name: ProjectName,
    current_user: CurrentUser,
) -> EmptyResponse:
    """Delete a team member."""
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
