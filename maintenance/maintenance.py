import time

from ayon_server.events import EventStream
from ayon_server.helpers.project_list import get_project_list
from ayon_server.logging import log_traceback, logger
from maintenance.maintenance_task import (
    ProjectMaintenanceTask,
    StudioMaintenanceTask,
)
from maintenance.tasks import task_sequence


async def run_maintenance(task_name: str | None = None) -> None:
    event_id: str | None = None
    start_time = time.monotonic()

    try:
        event_id = await EventStream.dispatch(
            "maintenance",
            description="Starting maintenance",
        )

        project_list = await get_project_list()
        for task_class in task_sequence:
            if task_name is not None and task_class.__name__ != task_name:
                continue
            task = task_class()
            logger.debug(f"Maintenance: {task.description}")
            if isinstance(task, StudioMaintenanceTask):
                description = task.description
                await EventStream.update(
                    event_id,
                    status="in_progress",
                    description=description,
                )
                await task.main()

            elif isinstance(task, ProjectMaintenanceTask):
                for project in project_list:
                    description = f"{task.description} for project {project.name}"
                    await EventStream.update(
                        event_id,
                        status="in_progress",
                        description=description,
                    )
                    await task.main(project.name)

    except Exception:
        log_traceback()

        if event_id is None:
            return

        await EventStream.update(
            event_id,
            status="failed",
        )

    else:
        elapsed = int(time.monotonic() - start_time)
        description = f"Maintenance completed in {elapsed} seconds"

        await EventStream.update(
            event_id,
            status="finished",
            description=description,
        )
