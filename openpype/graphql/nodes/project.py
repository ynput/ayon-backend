from typing import Optional

import strawberry

from openpype.entities import ProjectEntity
from openpype.lib.postgres import Postgres

from ..connections import (
    FoldersConnection,
    RepresentationsConnection,
    SubsetsConnection,
    TasksConnection,
    VersionsConnection,
)
from ..resolvers.folders import get_folder, get_folders
from ..resolvers.representations import get_representation, get_representations
from ..resolvers.subsets import get_subset, get_subsets
from ..resolvers.tasks import get_task, get_tasks
from ..resolvers.versions import get_version, get_versions
from ..utils import lazy_type, parse_json_data
from .common import BaseNode

FolderNode = lazy_type("FolderNode", ".nodes.folder")
SubsetNode = lazy_type("SubsetNode", ".nodes.subset")
TaskNode = lazy_type("TaskNode", ".nodes.task")
VersionNode = lazy_type("VersionNode", ".nodes.version")
RepresentationNode = lazy_type("RepresentationNode", ".nodes.representation")


@strawberry.type
class TaskType:
    name: str


@strawberry.type
class FolderType:
    name: str

    @strawberry.field
    def icon(self) -> str:
        return self.name.lower()


@ProjectEntity.strawberry_attrib()
class ProjectAttribType:
    pass


@ProjectEntity.strawberry_entity()
class ProjectNode(BaseNode):

    folder: Optional[FolderNode] = strawberry.field(
        resolver=get_folder, description=get_folder.__doc__
    )

    folders: FoldersConnection = strawberry.field(
        resolver=get_folders, description=get_folders.__doc__
    )

    task: Optional[TaskNode] = strawberry.field(
        resolver=get_task, description=get_task.__doc__
    )

    tasks: TasksConnection = strawberry.field(
        resolver=get_tasks, description=get_tasks.__doc__
    )

    subset: Optional[SubsetNode] = strawberry.field(
        resolver=get_subset, description=get_subset.__doc__
    )

    subsets: SubsetsConnection = strawberry.field(
        resolver=get_subsets, description=get_subsets.__doc__
    )

    version: Optional[VersionNode] = strawberry.field(
        resolver=get_version, description=get_version.__doc__
    )

    versions: VersionsConnection = strawberry.field(
        resolver=get_versions, description=get_versions.__doc__
    )

    representation: Optional[RepresentationNode] = strawberry.field(
        resolver=get_representation, description=get_representation.__doc__
    )

    representations: RepresentationsConnection = strawberry.field(
        resolver=get_representations, description=get_representations.__doc__
    )

    @strawberry.field
    async def task_types(self, active_only: bool = False) -> list[TaskType]:
        if active_only:
            query = f"""
                SELECT DISTINCT(task_type) AS task_type
                FROM project_{self.project_name}.tasks
            """
        else:
            query = f"""
                SELECT name AS task_type
                FROM project_{self.project_name}.task_types
            """
        return [
            TaskType(name=row["task_type"]) async for row in Postgres.iterate(query)
        ]

    @strawberry.field
    async def folder_types(self, active_only: bool = False) -> list[FolderType]:
        if active_only:
            query = f"""
                SELECT DISTINCT(folder_type) AS folder_type
                FROM project_{self.project_name}.folders
                WHERE folder_type IS NOT NULL
            """
        else:
            query = f"""
                SELECT name AS folder_type
                FROM project_{self.project_name}.folder_types
            """
        return [
            FolderType(name=row["folder_type"]) async for row in Postgres.iterate(query)
        ]

    @strawberry.field
    async def subset_families(self) -> list[str]:
        return [
            row["family"]
            async for row in Postgres.iterate(
                f"""
                SELECT DISTINCT(family)
                FROM project_{self.project_name}.subsets
            """
            )
        ]


def project_from_record(record: dict, context: dict | None = None) -> ProjectNode:
    """Construct a project node from a DB row."""
    return ProjectNode(
        project_name=record["name"],
        name=record["name"],
        active=record["active"],
        library=record["library"],
        attrib=parse_json_data(ProjectAttribType, record["attrib"]),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


setattr(ProjectNode, "from_record", staticmethod(project_from_record))
