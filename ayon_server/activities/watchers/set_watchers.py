from ayon_server.activities.create_activity import create_activity
from ayon_server.entities.core.projectlevel import ProjectLevelEntity
from ayon_server.entities.user import UserEntity
from ayon_server.lib.postgres import Postgres

from .watcher_list import build_watcher_list, get_watcher_list


async def set_watchers(
    entity: ProjectLevelEntity,
    watchers: list[str],  # list of user names
    user: UserEntity | None = None,  # who is setting the watchers
    *,
    sender: str | None = None,
) -> None:
    """Set watchers of an entity.

    Compare received watchers list with the current watchers list,
    delete users that are not in the received list, and add users that are
    not in the current list.
    """

    project_name = entity.project_name
    original_watchers = await get_watcher_list(entity)

    unwatchers = [w for w in original_watchers if w not in watchers]
    new_watchers = [w for w in watchers if w not in original_watchers]

    # We are just assuming here that no one dared to link any files to this
    # and it is safe to just delete the activities without checking for files.

    if unwatchers:
        query = f"""
            WITH activities_to_delete AS (
                SELECT activity_id FROM project_{project_name}.activity_feed
                WHERE activity_type = 'watch'
                AND reference_type = 'origin'
                AND entity_type = $1
                AND entity_id = $2
                AND COALESCE(activity_data->>'watcher', '')::TEXT = ANY ($3)
            )
            DELETE FROM project_{project_name}.activities
            WHERE id IN (SELECT activity_id FROM activities_to_delete)
        """

        await Postgres.execute(query, entity.entity_type, entity.id, unwatchers)

    # Add new watchers

    for watcher in new_watchers:
        await create_activity(
            entity=entity,
            activity_type="watch",
            body="",
            user_name=user.name if user else None,
            sender=sender,
            data={"watcher": watcher},
        )

    await build_watcher_list(entity)


async def ensure_watching(entity: ProjectLevelEntity, user: UserEntity) -> None:
    """Ensure that a user is watching an entity.

    This should be called when a user first adds a comment or a reviewable.
    """

    watchers = await get_watcher_list(entity)
    if user.name not in watchers:
        watchers.append(user.name)
        await set_watchers(entity, watchers, user=user)
