from ayon_server.auth.session import Session
from ayon_server.events import EventStream
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres

PROJECT_QUERIES = [
    """
    UPDATE tasks SET
    assignees = array_replace(assignees, $2, $1)
    WHERE $2 = ANY(assignees)
    """,
    """
    UPDATE versions SET
    author = $1 WHERE author = $2
    """,
    # Activities and files
    """
    UPDATE activities SET
    data = jsonb_set(data, '{author}', $1::jsonb)
    WHERE data->>'author' = $2
    """,
    """
    UPDATE activities SET
    data = jsonb_set(data, '{watcher}', $1::jsonb)
    WHERE activity_type = 'watch' AND data->>'watcher' = $2
    """,
    """
    UPDATE activities SET
    data = jsonb_set(data, '{assignee}', $1::jsonb)
    WHERE activity_type LIKE 'assignee.%' AND data->>'assignee' = $2
    """,
    """
    UPDATE activities
    SET data = jsonb_set(
        data,
        '{files}',
        (
            SELECT jsonb_agg(
                CASE
                    WHEN file->>'author' = $2
                    THEN jsonb_set(file, '{author}', $1::JSONB)
                    ELSE file
                END
            )
            FROM jsonb_array_elements(data->'files') AS file
        )
    )
    WHERE EXISTS (
        SELECT 1
        FROM jsonb_array_elements(data->'files') AS file
        WHERE file->>'author' = $2
    )
    """,
    # TODO: there is also an author record in:
    # activities->data->files[]->author
    # but it is not crucial to update it
    # we can do it later if needed
    """
    UPDATE files SET
    author = $1 WHERE author = $2
    """,
    """
    UPDATE activity_references SET
    entity_name = $1 WHERE entity_name = $2 AND entity_type = 'user'
    """,
    # Workfiles
    """
    UPDATE workfiles
    SET created_by = $1 WHERE created_by = $2
    """,
    """
    UPDATE workfiles
    SET updated_by = $1 WHERE updated_by = $2
    """,
    # Entity lists
    """
    UPDATE entity_lists
    SET owner = $1 WHERE owner = $2
    """,
    """
    UPDATE entity_lists
    SET created_by = $1 WHERE created_by = $2
    """,
    """
    UPDATE entity_lists
    SET updated_by = $1 WHERE updated_by = $2
    """,
    """
    UPDATE entity_list_items
    SET created_by = $1 WHERE created_by = $2
    """,
    """
    UPDATE entity_list_items
    SET updated_by = $1 WHERE updated_by = $2
    """,
    # Project settings
    """
    UPDATE project_site_settings
    SET user_name = $1 WHERE user_name = $2
    """,
    """
    UPDATE custom_roots
    SET user_name = $1 WHERE user_name = $2
    """,
]


async def rename_user(
    old_name: str,
    new_name: str,
    *,
    invoking_user_name: str | None = None,
    sender: str | None = None,
    sender_type: str | None = None,
) -> None:
    """Changes the user name of a user in the database and all references to it.

    Requires only old_name and new_name as arguments. The rest are optional and
    is used only for logging purposes.
    """

    async with Postgres.transaction():
        await Postgres.execute(
            "UPDATE public.users SET name = $1 WHERE name = $2",
            new_name,
            old_name,
        )

        projects = await get_project_list()

        for project in projects:
            await Postgres.set_project_schema(project.name)
            for query in PROJECT_QUERIES:
                await Postgres.execute(query, new_name, old_name)

    # Renaming user has many side effects, so we need to log out all Sessions
    # and let the user log in again
    await Session.logout_user(
        old_name, message="User has been logged out after renaming."
    )

    await EventStream.dispatch(
        "entity.user.renamed",
        description=f"Renamed user {old_name} to {new_name}",
        summary={"entityName": old_name},
        payload={"oldValue": old_name, "newValue": new_name},
        sender=sender,
        sender_type=sender_type,
        user=invoking_user_name,
    )
