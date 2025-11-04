from ayon_server.config import ayonconfig
from ayon_server.entities.project import ProjectEntity
from ayon_server.entities.user import UserEntity
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
