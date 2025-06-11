from ayon_server.auth.session import Session
from ayon_server.events import EventStream
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres

PROJECT_QUERIES = [
    # Activities and files
    """
    UPDATE project_{project_name}.files SET
    author = $1 WHERE author = $2
    """,
    """
    UPDATE project_{project_name}.activity_references SET
    entity_name = $1 WHERE entity_name = $2 AND entity_type = 'user'
    """,
    # Workfiles
    """
    UPDATE project_{project_name}.workfiles
    SET created_by = $1 WHERE created_by = $2
    """,
    """
    UPDATE project_{project_name}.workfiles
    SET updated_by = $1 WHERE updated_by = $2
    """,
    # Entity lists
    """
    UPDATE project_{project_name}.entity_lists
    SET owner = $1 WHERE owner = $2
    """,
    """
    UPDATE project_{project_name}.entity_lists
    SET created_by = $1 WHERE created_by = $2
    """,
    """
    UPDATE project_{project_name}.entity_lists
    SET updated_by = $1 WHERE updated_by = $2
    """,
    """
    UPDATE project_{project_name}.entity_list_items
    SET created_by = $1 WHERE created_by = $2
    """,
    """
    UPDATE project_{project_name}.entity_list_items
    SET updated_by = $1 WHERE updated_by = $2
    """,
]


async def rename_user(
    old_name: str,
    new_name: str,
    *,
    invoking_user_name: str | None = None,
    sender: str | None = None,
    sender_type: str | None,
) -> None:
    """Changes the user name of a user in the database and all references to it.

    Requires only old_name and new_name as arguments. The rest are optional and
    is used only for logging purposes.
    """

    async with Postgres.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE public.users SET name = $1 WHERE name = $2",
                new_name,
                old_name,
            )

            # Update tasks assignees - since assignees is an array,
            # it won't update automatically (there's no foreign key)

            projects = await get_project_list()

            for project in projects:
                project_name = project.name
                query = f"""
                    UPDATE project_{project_name}.tasks SET
                    assignees = array_replace(
                        assignees, '{old_name}', '{new_name}'
                    )
                    WHERE '{old_name}' = ANY(assignees)
                """
                await conn.execute(query)

                # activities.data->>'author'

                query = f"""
                    UPDATE project_{project_name}.activities SET
                    data = jsonb_set(
                        data,
                        '{{author}}',
                        $1::jsonb
                    )
                    WHERE data->>'author' = $2
                """
                await conn.execute(query, new_name, old_name)

                # TODO: there is also an author record in:
                # activities->data->files[]->author
                # but it is probably not important to update it

                for query in PROJECT_QUERIES:
                    await conn.execute(
                        query.format(project_name=project_name),
                        new_name,
                        old_name,
                    )

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
