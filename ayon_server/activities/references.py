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
from ayon_server.entities import TaskEntity, VersionEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.lib.postgres import Postgres


async def get_references_from_task(task: TaskEntity) -> list[ActivityReferenceModel]:
    """Get references from a task entity

    Supported references:
    - assignees
    - versions
    """
    references = []

    for assignee in task.assignees:
        references.append(
            ActivityReferenceModel(
                entity_type="user",
                entity_name=assignee,
                entity_id=None,
                reference_type="relation",
                data={"role": "assignee"},
            )
        )

    # Load a list of versions that belong to the task.
    async for row in Postgres.iterate(
        f"""
        SELECT id FROM project_{task.project_name}.versions WHERE task_id = $1
        """,
        task.id,
    ):
        references.append(
            ActivityReferenceModel(
                entity_type="version",
                entity_name=None,
                entity_id=row["id"],
                reference_type="relation",
            )
        )

    return references


async def get_references_from_version(
    version: VersionEntity,
) -> list[ActivityReferenceModel]:
    """Get references from a version

    Supported references:
    - author
    - task
    """

    references = []

    if version.author:
        references.append(
            ActivityReferenceModel(
                entity_type="user",
                entity_name=version.author,
                entity_id=None,
                reference_type="relation",
                data={"role": "author"},
            )
        )

    if version.task_id:
        references.append(
            ActivityReferenceModel(
                entity_type="task",
                entity_name=None,
                entity_id=version.task_id,
                reference_type="relation",
            )
        )

        task = await TaskEntity.load(version.project_name, version.task_id)
        for assignee in task.assignees:
            references.append(
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
) -> list[ActivityReferenceModel]:
    if isinstance(entity, TaskEntity):
        return await get_references_from_task(entity)
    elif isinstance(entity, VersionEntity):
        return await get_references_from_version(entity)
    else:
        return []
