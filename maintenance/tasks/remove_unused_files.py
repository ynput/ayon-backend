from ayon_server.files import Storages
from maintenance.maintenance_task import ProjectMaintenanceTask


class RemoveUnusedFiles(ProjectMaintenanceTask):
    description = "Removing unused file records"

    async def main(self, project_name: str):
        storage = await Storages.project(project_name)
        await storage.delete_unused_files()
