from typing import Any

from .project import ProjectEntity


class ProjectSkeletonEntity(ProjectEntity):
    @classmethod
    async def load(
        cls,
        name: str,
        transaction: Any = None,
        for_update: bool = False,
    ) -> "ProjectSkeletonEntity":
        """Load a project skeleton entity from the database."""
        raise NotImplementedError("ProjectSkeletonEntity is not implemented yet")
