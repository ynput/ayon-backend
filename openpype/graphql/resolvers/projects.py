from typing import Annotated
from strawberry.types import Info

from openpype.lib.postgres import Postgres
from openpype.utils import SQLTool, validate_name

from ..connections import ProjectsConnection
from ..nodes.project import ProjectNode
from ..edges import ProjectEdge

from .common import argdesc


async def get_projects(
    root,
    info: Info,
    name: Annotated[
        str | None,
        argdesc(
            """
            The name of the project to retrieve.
            If not provided, all projects will be returned.
            """
        ),
    ] = None,

    first: int | None = None,
    after: str | None = None,
    last: int | None = None,
    before: str | None = None,
) -> ProjectsConnection:
    """Return a list of projects."""

    conditions = []
    if name is not None:
        # if name is valid, it is also safe to use it in a query
        # without worrying about SQL injection
        if not validate_name(name):
            raise ValueError("Invalid project name specified")
        conditions.append(f"projects.name ILIKE '{name}'")

    return ProjectsConnection(
        edges=[
            ProjectEdge(node=ProjectNode.from_record(record))
            async for record in Postgres.iterate(
                f"""
                SELECT * FROM projects
                {SQLTool.conditions(conditions)}
                """
            )
        ]
    )


async def get_project(root, info: Info, name: str) -> ProjectNode | None:
    """Return a project node based on its name."""
    if not name:
        return None
    connection = await get_projects(root, info, name=name)
    if not connection.edges:
        return None
    return connection.edges[0].node
