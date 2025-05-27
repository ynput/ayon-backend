from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from maintenance.maintenance_task import StudioMaintenanceTask


async def clear_action_configs_by_projects() -> None:
    project_names = set()
    async for row in Postgres.iterate(
        """
        SELECT DISTINCT project_name FROM public.action_config
        WHERE project_name IS NOT NULL
        """
    ):
        project_names.add(row["project_name"])

    existing_projects = await get_project_list()
    for project in existing_projects:
        project_names.discard(project.name)

    if not project_names:
        return

    query = """
        DELETE FROM public.action_config
        WHERE project_name = ANY($1)
        AND last_used < EXTRACT(EPOCH FROM NOW()) - 60 * 60 * 24 * 30
    """

    msg = f"Removing old action configs for projects: " f"{','.join(project_names)}"

    logger.info(msg)
    await Postgres.execute(query, list(project_names))


async def clear_action_configs_by_users() -> None:
    user_names = set()
    async for row in Postgres.iterate(
        """
        SELECT DISTINCT user_name FROM public.action_config
        WHERE user_name IS NOT NULL
        """
    ):
        user_names.add(row["user_name"])

    # Get the list of all users

    query = "SELECT name FROM public.users"
    async for row in Postgres.iterate(query):
        user_names.discard(row["name"])

    if not user_names:
        return

    query = """
        DELETE FROM public.action_config
        WHERE user_name = ANY($1)
        AND last_used < EXTRACT(EPOCH FROM NOW()) - 60 * 60 * 24 * 30
    """

    msg = f"Removing old action configs for users: " f"{','.join(user_names)}"
    logger.info(msg)

    await Postgres.execute(query, list(user_names))


class RemoveOldActionConfigs(StudioMaintenanceTask):
    description = "Removing old action configs"

    async def main(self):
        await clear_action_configs_by_projects()
