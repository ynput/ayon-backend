from openpype.lib.postgres import Postgres


async def folder_types_enum(project_name: str | None = None):
    if project_name is None:
        return []

    return [
        row["name"]
        async for row in Postgres.iterate(
            f"""
            SELECT name
            FROM project_{project_name}.folder_types
            ORDER BY POSITION
            """
        )
    ]


async def task_types_enum(project_name: str | None = None):
    if project_name is None:
        return []

    return [
        row["name"]
        async for row in Postgres.iterate(
            f"""
            SELECT name
            FROM project_{project_name}.task_types
            ORDER BY POSITION
            """
        )
    ]
