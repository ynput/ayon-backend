from typing import Annotated

from fastapi import Query

from ayon_server.api.dependencies import CurrentUser

from .models import ViewListModel
from .router import router

QProjectName = Annotated[str, Query(alias="project")]


@router.get("")
async def get_views(
    current_user: CurrentUser,
    project_name: QProjectName | None = None,
) -> ViewListModel:
    """Get the list of views available to the user."""

    return ViewListModel(views=[])
