from typing import Annotated, cast

from ayon_server.api.dependencies import (
    AllowGuests,
    CurrentUser,
    NewProjectName,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.entities import ProjectEntity
from ayon_server.events import EventStream
from ayon_server.events.patch import build_project_change_events
from ayon_server.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.files import Storages
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres
from ayon_server.settings.anatomy.folder_types import FolderType
from ayon_server.settings.anatomy.product_base_types import (
    DefaultProductBaseType,
    ProductBaseType,
    default_product_type_definitions,
)
from ayon_server.settings.anatomy.statuses import Status
from ayon_server.settings.anatomy.tags import Tag
from ayon_server.settings.anatomy.task_types import TaskType
from ayon_server.types import Field
from ayon_server.utils.request_coalescer import RequestCoalescer

from .router import router

#
# [GET]
#


FOLDER_TYPES_FIELD = Annotated[
    list[FolderType],
    Field(default_factory=list, title="Folder types"),
]

TASK_TYPES_FIELD = Annotated[
    list[TaskType],
    Field(default_factory=list, title="Task types"),
]
STATUSES_FIELD = Annotated[
    list[Status],
    Field(default_factory=list, title="Statuses"),
]
TAGS_FIELD = Annotated[
    list[Tag],
    Field(default_factory=list, title="Tags"),
]


class ProjectModel(ProjectEntity.model.main_model):  # type: ignore
    folder_types: FOLDER_TYPES_FIELD
    task_types: TASK_TYPES_FIELD
    statuses: STATUSES_FIELD
    tags: TAGS_FIELD


class ProjectPostModel(ProjectEntity.model.post_model):  # type: ignore
    folder_types: FOLDER_TYPES_FIELD
    task_types: TASK_TYPES_FIELD
    statuses: STATUSES_FIELD
    tags: TAGS_FIELD


class ProjectPatchModel(ProjectEntity.model.patch_model):  # type: ignore
    folder_types: FOLDER_TYPES_FIELD
    task_types: TASK_TYPES_FIELD
    statuses: STATUSES_FIELD
    tags: TAGS_FIELD


default_pt_definitions = [p.dict() for p in default_product_type_definitions]


@router.get(
    "/projects/{project_name}",
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
    dependencies=[AllowGuests],
)
async def get_project(
    user: CurrentUser,
    project_name: ProjectName,
) -> ProjectModel:
    """Retrieve a project by its name."""

    await user.ensure_project_access(project_name)
    coalesce = RequestCoalescer()
    project = await coalesce(ProjectEntity.load, project_name)

    product_base_types_config = project.config.get("productBaseTypes", {})

    product_base_types_config["default"] = DefaultProductBaseType(
        **product_base_types_config.get("default", {})
    ).dict()

    if "definitions" not in product_base_types_config:
        product_base_types_config["definitions"] = default_pt_definitions
    else:
        product_base_types_config["definitions"] = [
            ProductBaseType(**pt).dict()
            for pt in product_base_types_config["definitions"]
        ]

    project.config["productBaseTypes"] = product_base_types_config
    project.config.pop("productTypes", None)  # legacy

    return cast(ProjectModel, project.as_user(user))


#
# [GET] /stats
#


@router.get("/projects/{project_name}/stats")
async def get_project_stats(user: CurrentUser, project_name: ProjectName):
    """Retrieve a project statistics by its name."""

    await user.ensure_project_access(project_name)
    counts = {}
    for entity in ["folders", "products", "versions", "representations", "tasks"]:
        res = await Postgres.fetch(
            f"""
            SELECT COUNT(id)
            FROM project_{project_name}.{entity}
            """
        )
        counts[entity] = res[0][0]

    return {"counts": counts}


#
# [PUT]
#


@router.put("/projects/{project_name}", status_code=201)
async def create_project(
    put_data: ProjectPostModel,
    user: CurrentUser,
    project_name: NewProjectName,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Create a new project.

    Since project has no ID, and a unique name is used as its
    identifier, use PUT request with the name provided in the URL
    to create a new project.

    This is different from the rest of the entities, which use POST
    requests to create new entities with a unique ID.

    Important: this endpoint only creates a project entity. It does
    not handle creating its anatomy and assigning users to the project,
    so it should be used only in special cases, when you need a granular
    control over a project creation process. Use `Deploy project`
    ([POST] /api/projects) for general usage.
    """

    user.check_permissions("studio.create_projects")

    try:
        project = await ProjectEntity.load(project_name)
    except NotFoundException:
        project = ProjectEntity(payload=put_data.dict() | {"name": project_name})
    else:
        raise ConflictException(f"Project {project_name} already exists")

    await project.save()

    await EventStream.dispatch(
        "entity.project.created",
        sender=sender,
        sender_type=sender_type,
        project=project.name,
        user=user.name,
        description=f"Created project {project.name}",
    )

    return EmptyResponse(status_code=201)


#
# [PATCH]
#


@router.patch("/projects/{project_name}", status_code=204)
async def update_project(
    patch_data: ProjectPatchModel,
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
):
    """Patch a project.

    Use a PATCH request to partially update a project.
    For example change the name or a particular key in 'data'.
    """

    project = await ProjectEntity.load(project_name)
    events = build_project_change_events(project, patch_data)

    if not user.is_manager:
        raise ForbiddenException(
            "You need to be a manager in order to update a project"
        )

    patch_data_dict = patch_data.dict(exclude_unset=True)
    patch_data_converted = ProjectEntity.model.patch_model(**patch_data_dict)

    project.patch(patch_data_converted)
    await project.save()

    for edata in events:
        await EventStream.dispatch(
            **edata,
            sender=sender,
            sender_type=sender_type,
            user=user.name,
        )
    return EmptyResponse()


#
# [DELETE]
#


async def unassign_users_from_deleted_projects() -> None:
    """Unassign all users from non-existent projects."""

    res = await Postgres.fetch(
        """
        SELECT DISTINCT jsonb_object_keys(data->'accessGroups')
        AS project_name FROM users
        """
    )
    assigned_projects = [row["project_name"] for row in res]
    existing_projects = [project.name for project in await get_project_list()]

    for project_name in assigned_projects:
        if project_name not in existing_projects:
            await Postgres.execute(
                f"""
                UPDATE users
                SET data = data #- '{{accessGroups, {project_name}}}'
                WHERE data->'accessGroups'->'{project_name}' IS NOT NULL;
                """
            )
    # we don't need to update sessions, as they are updated on the next login


@router.delete("/projects/{project_name}", status_code=204)
async def delete_project(
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Delete a given project including all its entities."""

    project = await ProjectEntity.load(project_name)

    if not user.is_manager:
        raise ForbiddenException("You need to be a manager in order to delete projects")

    await project.delete()

    # clean-up (TODO: consider running as a background task)

    storage = await Storages.project(project_name)
    await storage.trash()
    await unassign_users_from_deleted_projects()

    await EventStream.dispatch(
        "entity.project.deleted",
        sender=sender,
        sender_type=sender_type,
        project=project.name,
        user=user.name,
        description=f"Deleted project {project.name}",
    )

    return EmptyResponse()
