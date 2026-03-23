from typing import List

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

async def get_team_names(project_name: str) -> List[TeamSuggestionItem]:
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
