"""Activity relations solvers

This module contains functions that solve automatic relations for activities.
e.g. if an activity is created for a task, it should automatically reference all
assignees and versions that originate from that task.

Each entity type has its own get_references_from_{entity_type} function that
returns a list of ActivityReferenceModel objects.

Additionally, there is a get_references_from_entity function that takes a
ProjectLevelEntity object and calls the appropriate get_references_from_{entity_type}
function based on the entity type.

Resolved references are then stored to activity_references when an activity is created
or updated.
"""

__all__ = ["get_references_from_entity"]

from ayon_server.activities.models import ActivityReferenceModel
from ayon_server.entities import FolderEntity, TaskEntity, VersionEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.lib.postgres import Postgres


async def get_references_from_folder(
    folder: FolderEntity,
) -> set[ActivityReferenceModel]:
    """Get references from a folder entity

    Supported references:
    - assigneed on tasks
    """

    references: set[ActivityReferenceModel] = set()
    project_name = folder.project_name
    query = f"SELECT assignees FROM project_{project_name}.tasks WHERE folder_id = $1"

    res = await Postgres.fetch(query, folder.id)
    for row in res:
        for assignee in row["assignees"]:
            references.add(
                ActivityReferenceModel(
                    entity_type="user",
                    entity_name=assignee,
                    entity_id=None,
                    reference_type="relation",
                    data={"role": "assignee"},
                )
            )

    return references


async def get_references_from_task(task: TaskEntity) -> set[ActivityReferenceModel]:
    """Get references from a task entity

    Supported references:
    - assignees
    - versions
    """
    references: set[ActivityReferenceModel] = set()
    project_name = task.project_name

    for assignee in task.assignees:
        references.add(
            ActivityReferenceModel(
                entity_type="user",
                entity_name=assignee,
                entity_id=None,
                reference_type="relation",
                data={"role": "assignee"},
            )
        )

    # Load a list of versions that belong to the task.
    query = f"SELECT id FROM project_{project_name}.versions WHERE task_id = $1"
    res = await Postgres.fetch(query, task.id)
    for row in res:
        references.add(
            ActivityReferenceModel(
                entity_type="version",
                entity_name=None,
                entity_id=row["id"],
                reference_type="relation",
            )
        )

    references.add(
        ActivityReferenceModel(
            entity_type="folder",
            entity_name=None,
            entity_id=task.folder_id,
            reference_type="relation",
        )
    )

    return references


async def get_references_from_version(
    version: VersionEntity,
) -> set[ActivityReferenceModel]:
    """Get references from a version

    Supported references:
    - author
    - task
    """

    references: set[ActivityReferenceModel] = set()

    res = await Postgres.fetch(
        f"""
        SELECT p.folder_id as folder_id
        FROM project_{version.project_name}.products p
        WHERE p.id = $1
        """,
        version.product_id,
    )

    references.add(
        ActivityReferenceModel(
            entity_type="folder",
            entity_name=None,
            entity_id=res[0]["folder_id"],
            reference_type="relation",
        )
    )

    if version.author:
        references.add(
            ActivityReferenceModel(
                entity_type="user",
                entity_name=version.author,
                entity_id=None,
                reference_type="relation",
                data={"role": "author"},
            )
        )

    if version.task_id:
        references.add(
            ActivityReferenceModel(
                entity_type="task",
                entity_name=None,
                entity_id=version.task_id,
                reference_type="relation",
            )
        )

        task = await TaskEntity.load(version.project_name, version.task_id)
        for assignee in task.assignees:
            references.add(
                ActivityReferenceModel(
                    entity_type="user",
                    entity_name=assignee,
                    entity_id=None,
                    reference_type="relation",
                    data={"role": "assignee"},
                )
            )

    return references


async def get_references_from_entity(
    entity: ProjectLevelEntity,
) -> set[ActivityReferenceModel]:
    if isinstance(entity, TaskEntity):
        return await get_references_from_task(entity)
    if isinstance(entity, FolderEntity):
        return await get_references_from_folder(entity)
    elif isinstance(entity, VersionEntity):
        return await get_references_from_version(entity)
    else:
        return set()
