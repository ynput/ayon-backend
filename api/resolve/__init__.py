from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter

from ayon_server.lib.postgres import Postgres
from ayon_server.types import NAME_REGEX, Field, OPModel

router = APIRouter(tags=["URI resolver"])


class ResolveRequestModel(OPModel):
    uris: list[str] = Field(..., description="list of uris to resolve")


class ResolvedEntityModel(OPModel):
    project_name: str = Field(..., description="Project name")
    folder_id: str | None = Field(None, description="Folder id")
    subset_id: str | None = Field(None, description="Subset id")
    task_id: str | None = Field(None, description="Task id")
    subset_id: str | None = Field(None, description="Subset id")
    version_id: str | None = Field(None, description="Version id")
    representation_id: str | None = Field(None, description="Representation id")
    workfile_id: str | None = Field(None, description="Workfile id")


class ResolvedURIModel(OPModel):
    uri: str = Field(..., description="Resolved URI")
    entities: list[ResolvedEntityModel] = Field(..., description="Resolved entities")


class ParsedURIModel(OPModel):
    uri: str = Field(..., description="Resolved URI")
    project_name: str = Field(..., description="Project name")
    path: str | None = Field(None, description="Path")
    subset_name: str | None = Field(None, description="Subset name")
    task_name: str | None = Field(None, description="Task name")
    version_name: str | None = Field(None, description="Version name")
    representation_name: str | None = Field(None, description="Representation name")
    workfile_name: str | None = Field(None, description="Workfile name")


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
    assert NAME_REGEX.match(project_name), f"Invalid project name: {project_name}"

    path = parsed_uri.path or None

    qs = parse_qs(parsed_uri.query)

    subset_name = qs.get("subset", [None])[0]
    assert subset_name is None or NAME_REGEX.match(
        subset_name
    ), f"Invalid subset name: {subset_name}"

    task_name = qs.get("task", [None])[0]
    assert task_name is None or NAME_REGEX.match(
        task_name
    ), f"Invalid task name: {task_name}"

    version_name = qs.get("version", [None])[0]
    assert version_name is None or NAME_REGEX.match(
        version_name
    ), f"Invalid version name: {version_name}"

    representation_name = qs.get("representation", [None])[0]
    assert representation_name is None or NAME_REGEX.match(
        representation_name
    ), f"Invalid representation name: {representation_name}"

    workfile_name = qs.get("workfile", [None])[0]
    assert workfile_name is None or NAME_REGEX.match(
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


async def resolve_entities(req: ParsedURIModel) -> list[ResolvedEntityModel]:
    return []
    query = """
        SELECT r.attrib->>'path'
        FROM hierarchy as n
        INNER JOIN subsets AS s ON n.id = s.folder_id
        INNER JOIN versions AS v ON s.id = v.subset_id
        INNER JOIN representations AS r ON v.id = r.version_id
        WHERE
            n.path = $1
        AND s.name = $2
        AND v.version = $3
        AND r.name = $4
    """

    for elm in args.split("&"):
        key, val = elm.split("=")
        if key == "subset":
            subset = val
        elif key == "version":
            version = int(val.lower().lstrip("v"))
        elif key == "representation":
            representation = val

    result.append(await stmt.fetchval(hpath, subset, version, representation))


@router.post("/resolve")
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
                entities = await resolve_entities(parsed_uri)
                result.append(ResolvedURIModel(uri=uri, entities=entities))
    return result
