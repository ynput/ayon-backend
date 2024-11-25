from abc import ABC, abstractmethod
from typing import Literal

MaintenanceTaskType = Literal["studio", "project"]


class BaseMaintenanceTask(ABC):
    task_type: MaintenanceTaskType
    description: str

    @abstractmethod
    async def main(self, *args, **kwargs):
        pass


class StudioMaintenanceTask(BaseMaintenanceTask):
    task_type = "studio"

    async def main(self):
        pass


class ProjectMaintenanceTask(BaseMaintenanceTask):
    task_type = "project"

    async def main(self, project_name: str):
        pass
