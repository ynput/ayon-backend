from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from maintenance.maintenance_task import ProjectMaintenanceTask

INDEXES = {
    "folder_attrib_idx": "folders USING gin(attrib);",
    "folder_type_idx": "folders(folder_type);",
    "folder_status_idx": "folders(status);",
    "task_type_idx": "tasks(task_type);",
    "task_status_idx": "tasks(status);",
    "task_assignees_idx": "tasks USING gin(assignees);",
    "task_attrib_idx": "tasks USING gin(attrib);",
    "product_status_idx": "products(status);",
    "product_attrib_idx": "products USING gin(attrib);",
    "version_task_id_idx": "versions(task_id);",
    "version_status_idx": "versions(status);",
    "version_attrib_idx": "versions USING gin(attrib);",
    "representation_status_idx": "representations(status);",
    "representation_attrib_idx": "representations USING gin(attrib);",
}


class AddMissingProjectIndexes(ProjectMaintenanceTask):
    description = "Adding missing project indexes"

    async def main(self, project_name: str):

        # get the list of existing indices

        query = """
            SELECT indexname FROM pg_indexes
            WHERE schemaname ILIKE $1
            AND tablename IN ('folders', 'tasks', 'versions', 'representations');
        """
        result = await Postgres.fetch(query, f"project_{project_name}")

        existing_indexes = {row["indexname"] for row in result}

        for index_name, index_query_stub in INDEXES.items():
            if index_name in existing_indexes:
                continue

            query = f"CREATE INDEX IF NOT EXISTS {index_name} ON {index_query_stub}"

            logger.info(
                f"Creating missing index {index_name} for project {project_name}"
            )

            async with Postgres.transaction():
                await Postgres.set_project_schema(project_name)
                await Postgres.execute(query, timeout=300)
