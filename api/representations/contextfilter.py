from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.lib.postgres import Postgres
from ayon_server.types import ENTITY_ID_EXAMPLE, Field, OPModel
from ayon_server.utils import SQLTool

from .router import router


class ContextFilterModel(OPModel):
    key: str = Field(
        ...,
        title="Context key",
        example="task.name",
    )
    values: list[str] = Field(
        ...,
        title="Possible values",
        description="List of regular expressions which at least one must match",
        example=["^work.*$"],
    )


class LookupRequestModel(OPModel):
    names: list[str] = Field(
        default_factory=list,
        title="Representation names",
        example=["ma", "obj"],
    )
    version_ids: list[str] = Field(
        default_factory=list,
        title="Version IDs",
        example=[
            ENTITY_ID_EXAMPLE,
        ],
    )
    context: list[ContextFilterModel] = Field(
        default_factory=list,
        title="Context filters",
    )


class LookupResponseModel(OPModel):
    ids: list[str] = Field(
        default_factory=list,
        title="Representation IDs",
        description="List of matching representation ids",
        example=[ENTITY_ID_EXAMPLE],
    )


def build_filter_condition(req):
    path = req.key.split(".")
    regexes = req.values
    path_clause = "data->'context'"
    for i, p in enumerate(path):
        if i == len(path) - 1:
            path_clause += f"->>'{p}'"
        else:
            path_clause += f"->'{p}'"
    regex_clause = " OR ".join([f"{path_clause} ~ '{regex}'" for regex in regexes])
    return f"({regex_clause})"


@router.post("/projects/{project_name}/repreContextFilter")
async def representation_context_filter(
    request: LookupRequestModel,
    user: CurrentUser,
    project_name: ProjectName,
) -> LookupResponseModel:
    """Return representation IDs matching the given criteria."""

    conditions: list[str] = []
    if request.names:
        conditions.append(f"name IN {SQLTool.array(request.names)}")

    if request.version_ids:
        conditions.append(f"version_id IN {SQLTool.id_array(request.version_ids)}")

    if request.context:
        for f in request.context:
            conditions.append(build_filter_condition(f))

    query = f"""
        SELECT id, name, data->'context' as context
        FROM project_{project_name}.representations
        {SQLTool.conditions(conditions)}
        LIMIT 100
    """

    result: list[str] = []
    async for row in Postgres.iterate(query):
        result.append(row["id"])

    return LookupResponseModel(ids=result)
