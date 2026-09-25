from typing import Annotated

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .router import router


class ProjectTagsModel(OPModel):
    folders: Annotated[list[str], Field(default_factory=list)]
    tasks: Annotated[list[str], Field(default_factory=list)]
    products: Annotated[list[str], Field(default_factory=list)]
    versions: Annotated[list[str], Field(default_factory=list)]
    representations: Annotated[list[str], Field(default_factory=list)]
    workfiles: Annotated[list[str], Field(default_factory=list)]


QUERY = """
      select 'folders' as table_name, array_agg(distinct tag) as tags_array
      from folders, unnest(folders.tags) as tag

      union all

      select 'tasks', array_agg(distinct tag)
      from tasks, unnest(tasks.tags) as tag

      union all

      select 'products', array_agg(distinct tag)
      from products, unnest(products.tags) as tag

      union all

      select 'versions', array_agg(distinct tag)
      from versions, unnest(versions.tags) as tag

      union all

      select 'representations', array_agg(distinct tag)
      from representations, unnest(representations.tags) as tag

      union all

      select 'workfiles', array_agg(distinct tag)
      from workfiles, unnest(workfiles.tags) as tag
"""


@router.get("/projects/{project_name}/tags")
async def get_project_tags(
    user: CurrentUser,
    project_name: ProjectName,
) -> ProjectTagsModel:
    """List tags used in the project."""

    _ = user

    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        result = await Postgres.fetch(QUERY)
        data = {}
        for row in result:
            table_name = row["table_name"]
            tags_array = row["tags_array"]
            data[table_name] = tags_array or []
        return ProjectTagsModel(**data)
