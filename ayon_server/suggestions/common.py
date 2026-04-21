from ayon_server.config import ayonconfig
from ayon_server.entities.project import ProjectEntity
from ayon_server.entities.user import UserEntity
from ayon_server.lib.postgres import Postgres
from ayon_server.suggestions.models import TeamSuggestionItem
from ayon_server.utils.sqltool import SQLTool


async def get_relevant_users_cte(project: ProjectEntity, user: UserEntity) -> str:
    xlist = ""
    if ayonconfig.limit_user_visibility and not user.is_manager:
        user_groups = user.data.get("accessGroups", {}).get(project.name, [])
        ug_arr = SQLTool.array(user_groups, curly=True)
        xlist = f" AND (data->'accessGroups'->'{project.name}' ?| {ug_arr})"

    return f"""relevant_users AS (
        SELECT name FROM public.users
        WHERE name = '{user.name}'
        OR (data->>'isAdmin' = 'true' OR data->>'isManager' = 'true')
        OR (data->'accessGroups'->'{project.name}' IS NOT NULL {xlist})
    )
    """


async def get_team_suggestion_items(project_name: str) -> list[TeamSuggestionItem]:
    query = f"""
        SELECT DISTINCT
            team_element->>'name' AS name
        FROM
            public.projects p,
            LATERAL jsonb_array_elements(data->'teams') AS team_element
        WHERE
            p.name = '{project_name}'
            AND jsonb_typeof(data->'teams') = 'array'
            AND team_element->>'name' IS NOT NULL
        ORDER BY
            name ASC
    """
    results = []
    async for row in Postgres.iterate(query):
        item = TeamSuggestionItem(
            name=row["name"],
            relevance=0,
        )
        results.append(item)

    return results


async def get_team_members(project_name: str, team_name: str) -> list[str]:
    """Return list of team members for the given team name in the project."""
    query = f"""
        SELECT
            member_element->>'name' AS member_name
        FROM
            public.projects p,
            LATERAL jsonb_array_elements(p.data->'teams') AS team_element,
            LATERAL jsonb_array_elements(team_element->'members') AS member_element
        WHERE
            p.name = '{project_name}'
            AND team_element->>'name' = '{team_name}'
            AND jsonb_typeof(p.data->'teams') = 'array'
            AND jsonb_typeof(team_element->'members') = 'array'
        ORDER BY
            member_name ASC;

    """
    results = []
    async for row in Postgres.iterate(query):
        results.append(row["member_name"])

    return results
