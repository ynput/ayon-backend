from typing import Literal, cast

from ayon_server.api.dependencies import AllowGuests, CurrentUser, ProjectName
from ayon_server.entities import FolderEntity, TaskEntity, VersionEntity
from ayon_server.entities.project import ProjectEntity
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.suggestions.folder import get_folder_suggestions
from ayon_server.suggestions.models import (
    SuggestionType,
    TaskSuggestionItem,
    UserSuggestionItem,
    VersionSuggestionItem,
)
from ayon_server.suggestions.task import get_task_suggestions
from ayon_server.suggestions.version import get_version_suggestions
from ayon_server.types import Field, OPModel

from .router import router


class SuggestRequest(OPModel):
    entity_type: Literal["folder", "task", "version"] = Field(..., example="task")
    entity_id: str = Field(..., example="af3e4b3e-1b1b-4b3b-8b3b-3b3b3b3b3b3b")


class SuggestResponse(OPModel):
    users: list[UserSuggestionItem] = Field(default_factory=list)
    tasks: list[TaskSuggestionItem] = Field(default_factory=list)
    versions: list[VersionSuggestionItem] = Field(default_factory=list)


@router.post("/suggest", response_model_exclude_none=True, dependencies=[AllowGuests])
async def suggest_entity_mention(
    user: CurrentUser,
    project_name: ProjectName,
    request: SuggestRequest,
) -> SuggestResponse:
    """Suggests entity mentions based on the given entity type.

    This is triggered when the user begins commenting on a task,
    folder, or version. It populates the suggestions dropdown
    with relevant entities that the user can mention.
    """

    if user.is_guest:
        return SuggestResponse()

    entity_class = get_entity_class(request.entity_type)
    entity = await entity_class.load(project_name, request.entity_id)
    await entity.ensure_read_access(user)

    project = await ProjectEntity.load(project_name)

    res: dict[str, list[SuggestionType]]

    if request.entity_type == "folder":
        res = await get_folder_suggestions(project, user, cast(FolderEntity, entity))
    elif request.entity_type == "task":
        res = await get_task_suggestions(project, user, cast(TaskEntity, entity))
    elif request.entity_type == "version":
        res = await get_version_suggestions(project, user, cast(VersionEntity, entity))
    else:
        raise ValueError("Unrecognized entity type")

    return SuggestResponse(**res)
