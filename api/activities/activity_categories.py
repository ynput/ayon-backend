from typing import Any

from ayon_server.activities.activity_categories import ActivityCategories
from ayon_server.api.dependencies import AllowGuests, CurrentUser, ProjectName
from ayon_server.entities import ProjectEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.entity_access import EntityAccessHelper
from ayon_server.types import Field, OPModel

from .router import router


class ActivityCategoriesResponseModel(OPModel):
    categories: list[dict[str, Any]] = Field(..., example=[{"name": "category1"}])


@router.get("/activityCategories", dependencies=[AllowGuests])
async def get_activity_categories(
    user: CurrentUser,
    project_name: ProjectName,
) -> ActivityCategoriesResponseModel:
    cats = []  # meow
    all_cats = await ActivityCategories.get_activity_categories(project_name)
    project = await ProjectEntity.load(project_name)

    for cat in all_cats:
        try:
            await EntityAccessHelper.check(
                user,
                access=cat.get("access"),
                level=EntityAccessHelper.MANAGE,
                default_open=False,
                project=project,
            )
            access_level = EntityAccessHelper.MANAGE
        except ForbiddenException as e:
            access_level = e.extra.get("access_level", 0)

        if user.is_guest:
            cat.pop("access", None)

        if access_level >= EntityAccessHelper.READ:
            cats.append({**cat, "accessLevel": access_level})

    return ActivityCategoriesResponseModel(categories=cats)
