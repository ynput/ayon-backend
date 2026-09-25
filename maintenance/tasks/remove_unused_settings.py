from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from maintenance.maintenance_task import ProjectMaintenanceTask


class RemoveUnusedSettings(ProjectMaintenanceTask):
    description = "Removing unused settings"

    async def main(self, project_name: str) -> None:
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            query = """
                WITH deleted_settings AS (
                    DELETE FROM project_site_settings t
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM public.sites s
                        WHERE s.id = t.site_id
                        )
                    OR NOT EXISTS (
                        SELECT 1
                        FROM public.users u
                        WHERE u.name = t.user_name
                        )
                    RETURNING *
                )
                SELECT count(*) AS count FROM deleted_settings;
            """

            res = await Postgres.fetchrow(query)
            if res and res["count"]:
                logger.info(
                    f"Removed {res['count']} unused site settings in {project_name}"
                )

            query = """
                WITH deleted_roots AS (
                    DELETE FROM custom_roots t
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM public.sites s
                        WHERE s.id = t.site_id
                        )
                    OR NOT EXISTS (
                        SELECT 1
                        FROM public.users u
                        WHERE u.name = t.user_name
                        )
                    RETURNING *
                )
                SELECT count(*) AS count FROM deleted_roots;
            """

            res = await Postgres.fetchrow(query)
            if res and res["count"]:
                logger.info(
                    f"Removed {res['count']} unused custom roots in {project_name}"
                )
