from openpype.lib.postgres import Postgres


async def folder_types_enum(project_name: str | None = None):
    """TODO"""

    if project_name is None:
        return [
            "Folder type 1",
            "Folder type 2",
            "Folder type 3",
            "Folder type 4",
        ]

    return [
        row["name"]
        async for row in Postgres.iterate(
            f"""
            SELECT name FROM folder_types
            FROM project_{project_name} ORDER BY POSITION
            """
        )
    ]


async def task_types_enum(project_name: str | None = None):
    """TODO"""
    if project_name is None:
        return [
            "Task type 1",
            "Task type 2",
            "Task type 3",
            "Task type 4",
        ]

    return [
        row["name"]
        async for row in Postgres.iterate(
            f"""
            SELECT name FROM task_types
            FROM project_{project_name} ORDER BY POSITION
            """
        )
    ]
