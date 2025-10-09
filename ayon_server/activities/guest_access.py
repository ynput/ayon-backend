from ayon_server.entities import ProjectEntity, UserEntity
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.helpers.entity_access import EntityAccessHelper
from ayon_server.lib.postgres import Postgres


async def get_guest_activity_category(
    user: UserEntity,
    project: ProjectEntity,
    entity_list_id: str | None,
) -> str:
    if entity_list_id is None:
        raise ForbiddenException("Guest has no comment category")

    if user.attrib.email not in project.data.get("guestUsers", {}):
        raise ForbiddenException("You are not allowed to access this project")

    # Get the entity list to check whether the guest has access to it
    # and to get the guest category
    res = await Postgres.fetchrow(
        f"""
        SELECT data, access FROM project_{project.name}.entity_lists
        WHERE id = $1
        """,
        entity_list_id,
    )

    if not res:
        raise NotFoundException("Entity list not found")

    access = res["access"]
    await EntityAccessHelper.check(
        user,
        access=access,
        level=EntityAccessHelper.READ,  # Read is enough to comment
        project=project,
    )

    # map guest email to category, in which the guest can comment
    list_guest_categories = res["data"].get("guestActivityCategories", {})
    list_guest_category = list_guest_categories.get(user.attrib.email)
    if not list_guest_category:
        raise ForbiddenException("Guest has no comment category")

    return list_guest_category


async def ensure_guest_can_react(user: UserEntity, project_name: str, activity_id: str):
    if not user.is_guest:
        return

    res = await Postgres.fetchrow(
        f"""
        SELECT 1
        FROM project_{project_name}.activities a
        JOIN project_{project_name}.entity_lists l
            ON (a.data->>'entityList')::UUID = l.id
        WHERE a.id = $1
        AND  (
            (l.access->'__guests__')::INTEGER >= 0
         OR (l.access->$2)::INTEGER >= 0
        )
        """,
        activity_id,
        f"guest:{user.attrib.email}",
    )

    if not res:
        raise NotFoundException("Can't react to this activity")
