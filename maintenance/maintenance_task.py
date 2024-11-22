from abc import ABC, abstractmethod
from typing import Literal

MaintenanceTaskType = Literal["studio", "project"]


class MaintenanceTask(ABC):
    task_type: MaintenanceTaskType

    @abstractmethod
    async def main(self, *args, **kwargs):
        pass


class StudioMaintenanceTask(MaintenanceTask):
    task_type = "studio"

    async def main(self):
        pass


class ProjectMaintenanceTask(MaintenanceTask):
    task_type = "project"

    async def main(self, project_name: str):
        pass
