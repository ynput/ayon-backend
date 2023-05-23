import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter

from ayon_server.lib.postgres import Postgres
from ayon_server.types import NAME_REGEX, Field, OPModel

router = APIRouter(tags=["URI resolver"])


class ResolveRequestModel(OPModel):
    uris: list[str] = Field(..., title="URIs", description="list of uris to resolve")


class ResolvedEntityModel(OPModel):
    project_name: str = Field(..., title="Project name")
    folder_id: str | None = Field(None, title="Folder id")
    subset_id: str | None = Field(None, title="Subset id")
    task_id: str | None = Field(None, title="Task id")
    version_id: str | None = Field(None, title="Version id")
    representation_id: str | None = Field(None, title="Representation id")
    workfile_id: str | None = Field(None, title="Workfile id")


class ResolvedURIModel(OPModel):
    uri: str = Field(..., title="Resolved URI")
    entities: list[ResolvedEntityModel] = Field(..., title="Resolved entities")


class ParsedURIModel(OPModel):
    uri: str = Field(..., title="Resolved URI")
    project_name: str = Field(..., title="Project name")
    path: str | None = Field(None, title="Path")
    subset_name: str | None = Field(None, title="Subset name")
    task_name: str | None = Field(None, title="Task name")
    version_name: str | None = Field(None, title="Version name")
    representation_name: str | None = Field(None, title="Representation name")
    workfile_name: str | None = Field(None, title="Workfile name")


def parse_uri(uri: str) -> ParsedURIModel:
    project_name: str
    path: str | None
    subset_name: str | None
    task_name: str | None
    version_name: str | None
    representation_name: str | None
    workfile_name: str | None

    parsed_uri = urlparse(uri)
    assert parsed_uri.scheme in [
        "ayon",
        "ayon+entity",
    ], f"Invalid scheme: {parsed_uri.scheme}"

    project_name = parsed_uri.netloc
    name_validator = re.compile(NAME_REGEX)
    assert name_validator.match(project_name), f"Invalid project name: {project_name}"

    path = parsed_uri.path.strip("/") or None

    qs: dict[str, Any] = parse_qs(parsed_uri.query)

    subset_name = qs.get("subset", [None])[0]
    assert (subset_name is None) or name_validator.match(
        subset_name
    ), f"Invalid subset name: {subset_name}"

    task_name = qs.get("task", [None])[0]
    assert task_name is None or name_validator.match(
        task_name
    ), f"Invalid task name: {task_name}"

    version_name = qs.get("version", [None])[0]
    assert version_name is None or name_validator.match(
        version_name
    ), f"Invalid version name: {version_name}"

    representation_name = qs.get("representation", [None])[0]
    assert representation_name is None or name_validator.match(
        representation_name
    ), f"Invalid representation name: {representation_name}"

    workfile_name = qs.get("workfile", [None])[0]
    assert workfile_name is None or name_validator.match(
        workfile_name
    ), f"Invalid workfile name: {workfile_name}"

    # assert we don't have incompatible arguments

    if task_name is not None or workfile_name is not None:
        assert subset_name is None, "Tasks cannot be queried with subsets"
        assert version_name is None, "Tasks cannot be queried with versions"
        assert (
            representation_name is None
        ), "Tasks cannot be queried with representations"

    return ParsedURIModel(
        uri=uri,
        project_name=project_name,
        path=path,
        subset_name=subset_name,
        task_name=task_name,
        version_name=version_name,
        representation_name=representation_name,
        workfile_name=workfile_name,
    )


async def resolve_entities(conn, req: ParsedURIModel) -> list[ResolvedEntityModel]:
    result = []
    cols = ["h.id as folder_id"]
    joins = []
    conds = []

    if not req.path:
        return [ResolvedEntityModel(project_name=req.project_name)]

    if req.task_name is not None or req.workfile_name is not None:
        return []  # not implemented
    else:
        if req.representation_name is not None:
            cols.extend(
                ["s.id as subset_id", "v.id as version_id", "r.id as representation_id"]
            )
            joins.append("INNER JOIN subsets AS s ON h.id = s.folder_id")
            joins.append("INNER JOIN versions AS v ON s.id = v.subset_id")
            joins.append("INNER JOIN representations AS r ON v.id = r.version_id")
            conds.append(f"r.name = '{req.representation_name}'")
            if req.version_name is not None:
                conds.append(f"v.version = {int(req.version_name.lstrip('v'))}")
            if req.subset_name is not None:
                conds.append(f"s.name = '{req.subset_name}'")
            if req.path is not None:
                conds.append(f"h.path = '{req.path}'")
        elif req.version_name is not None:
            cols.extend(["s.id as subset_id", "v.id as version_id"])
            joins.append("INNER JOIN subsets AS s ON h.id = s.folder_id")
            joins.append("INNER JOIN versions AS v ON s.id = v.subset_id")
            conds.append(f"v.version = {int(req.version_name.lstrip('v'))}")
            if req.subset_name is not None:
                conds.append(f"s.name = '{req.subset_name}'")
            if req.path is not None:
                conds.append(f"h.path = '{req.path}'")
        elif req.subset_name is not None:
            cols.append("s.id as subset_id")
            joins.append("INNER JOIN subsets AS s ON h.id = s.folder_id")
            conds.append(f"s.name = '{req.subset_name}'")
            if req.path is not None:
                conds.append(f"h.path = '{req.path}'")
        elif req.path is not None:
            conds.append(f"h.path = '{req.path}'")

    query = f"""
        SELECT
            {", ".join(cols)}
        FROM
            hierarchy h
            {" ".join(joins)}
        WHERE
            {" AND ".join(conds)}
    """

    statement = await conn.prepare(query)
    async for row in statement.cursor():
        result.append(ResolvedEntityModel(project_name=req.project_name, **row))

    return result


@router.post("/resolve", response_model_exclude_none=True)
async def resolve(request: ResolveRequestModel) -> list[ResolvedURIModel]:
    result: list[ResolvedURIModel] = []
    current_project = ""
    async with Postgres.acquire() as conn:
        async with conn.transaction():
            for uri in request.uris:
                parsed_uri = parse_uri(uri)
                if parsed_uri.project_name != current_project:
                    await conn.execute(
                        f"SET LOCAL search_path TO project_{parsed_uri.project_name}"
                    )
                    current_project = parsed_uri.project_name
                entities = await resolve_entities(conn, parsed_uri)
                result.append(ResolvedURIModel(uri=uri, entities=entities))
    return result
