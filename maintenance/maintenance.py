from nxtools import logging

from ayon_server.helpers.project_list import get_project_list
from maintenance.maintenance_task import (
    ProjectMaintenanceTask,
    StudioMaintenanceTask,
)
from maintenance.tasks import task_sequence


async def run_maintenance():
    project_list = await get_project_list()

    for task_class in task_sequence:
        task = task_class()
        logging.info(f"Maintenance: {task.description}")
        if isinstance(task, StudioMaintenanceTask):
            await task.main()

        elif isinstance(task, ProjectMaintenanceTask):
            for project in project_list:
                await task.main(project.name)
