import os
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Query

from ayon_server.api.dependencies import AllowGuests, ClientSiteID, CurrentUser
from ayon_server.exceptions import (
    BadRequestException,
    NotFoundException,
    ServiceUnavailableException,
)
from ayon_server.helpers.project_list import normalize_project_name
from ayon_server.helpers.roots import get_roots_for_projects
from ayon_server.lib.postgres import Postgres
from ayon_server.types import NAME_REGEX, ProjectLevelEntityType

from .models import (
    ParsedURIModel,
    ResolvedEntityModel,
    ResolvedURIModel,
    ResolveRequestModel,
)
from .templating import StringTemplate

router = APIRouter(tags=["URIs"])


SDF_REGEX = re.compile(r":SDF_FORMAT_ARGS.*$")
NAME_VALIDATOR = re.compile(NAME_REGEX)


def sanitize_uri(uri: str) -> str:
    # remove `:SDF_FORMAT_ARGS` suffix
    uri = re.sub(SDF_REGEX, "", uri)
    return uri


def validate_name(name: str | None) -> None:
    if name is None:
        return
    if name == "*":
        return
    if not NAME_VALIDATOR.match(name):
        raise ValueError(f"Invalid name: {name}")


def parse_uri(uri: str) -> ParsedURIModel:
    project_name: str
    path: str | None
    product_name: str | None
    task_name: str | None
    version_name: str | None
    representation_name: str | None
    workfile_name: str | None

    uri = sanitize_uri(uri)

    parsed_uri = urlparse(uri)
    if parsed_uri.scheme not in ["ayon", "ayon+entity"]:
        raise ValueError(f"Invalid scheme: {parsed_uri.scheme}")

    project_name = parsed_uri.netloc
    if not NAME_VALIDATOR.match(project_name):
        raise ValueError(f"Invalid project name: {project_name}")

    path = parsed_uri.path.strip("/") or None
    if path:
        for element in path.split("/"):
            if not NAME_VALIDATOR.match(element):
                raise ValueError(f"Invalid path element: {element}")

    qs: dict[str, Any] = parse_qs(parsed_uri.query)

    product_name = qs.get("product", [None])[0]
    if product_name is not None:
        validate_name(product_name)

    task_name = qs.get("task", [None])[0]
    if task_name is not None:
        validate_name(task_name)

    version_name = qs.get("version", [None])[0]
    if version_name is not None:
        validate_name(version_name)

    representation_name = qs.get("representation", [None])[0]
    if representation_name is not None:
        validate_name(representation_name)

    workfile_name = qs.get("workfile", [None])[0]
    if workfile_name is not None:
        validate_name(workfile_name)

    # assert we don't have incompatible arguments

    if task_name is not None or workfile_name is not None:
        if product_name is not None:
            raise ValueError("Tasks and workfiles cannot be queried with products")
        if version_name is not None:
            raise ValueError("Tasks and workfiles cannot be queried with versions")
        if representation_name is not None:
            raise ValueError(
                "Tasks and workfiles cannot be queried with representations"
            )

    return ParsedURIModel(
        uri=uri,
        project_name=project_name,
        path=path,
        product_name=product_name,
        task_name=task_name,
        version_name=version_name,
        representation_name=representation_name,
        workfile_name=workfile_name,
    )


def get_representation_path(
    template: str,
    context: dict[str, Any],
    roots: dict[str, str] | None = None,
) -> str:
    context["root"] = roots or {}
    return StringTemplate.format_template(template, context)


def get_path_conditions(path: str | None) -> list[str]:
    if path is None:
        return []
    if path == "*":
        return []
    return [f"h.path = '{path}'"]


def get_product_conditions(product_name: str | None) -> list[str]:
    if product_name is None:
        return []
    if product_name == "*":
        return []
    return [f"s.name = '{product_name}'"]


def get_version_conditions(version_name: str | None) -> list[str]:
    if version_name is None:
        return []

    if version_name == "*":
        return []

    original_version_name = version_name
    version_name = version_name.strip().lower()
    if version_name.startswith("v"):
        version_name = version_name[1:]

    if version_name.isdigit():
        return [f"v.version = {int(version_name)}"]

    if version_name == "latest":
        return [
            """
            v.id in (
                SELECT l.ids[array_upper(l.ids, 1)]
                FROM version_list AS l
            )
        """
        ]

    if version_name == "hero":
        return ["v.version < 0"]

    raise ValueError(f"Invalid version name: {original_version_name}")


def get_representation_conditions(representation_name: str | None) -> list[str]:
    if representation_name is None:
        return []
    if representation_name == "*":
        return []
    return [f"r.name = '{representation_name}'"]


async def resolve_entities(
    req: ParsedURIModel,
    roots: dict[str, str],
    site_id: str | None = None,
    path_only: bool = False,
) -> list[ResolvedEntityModel]:
    assert await Postgres.is_in_transaction(), "Must be called in a transaction"

    result = []
    cols = ["h.id as folder_id"]
    joins = []
    conds = []

    # if not req.path:
    #     return [ResolvedEntityModel(project_name=req.project_name)]

    target_entity_type: ProjectLevelEntityType | None = None

    if not (
        req.product_name
        or req.version_name
        or req.representation_name
        or req.task_name
        or req.workfile_name
        or req.path
    ):
        return []

    platform = None
    if site_id:
        platform = await get_platform_for_site_id(site_id)

    if req.task_name is not None or req.workfile_name is not None:
        cols.append("t.id as task_id")
        joins.append("INNER JOIN tasks AS t ON h.id = t.folder_id")
        conds.append(f"t.name = '{req.task_name}'")
        target_entity_type = "task"
        if req.workfile_name is not None:
            cols.append("w.id as workfile_id")
            joins.append("INNER JOIN workfiles AS w ON t.id = w.task_id")
            conds.append(f"w.path LIKE '%/{req.workfile_name}'")
            target_entity_type = "workfile"

        conds.extend(get_path_conditions(req.path))

    else:
        if req.representation_name is not None:
            cols.extend(
                [
                    "s.id as product_id",
                    "v.id as version_id",
                    "r.id as representation_id",
                    "r.attrib->>'template' as file_template",
                    "r.data->'context' as context",
                ]
            )
            joins.append("INNER JOIN products AS s ON h.id = s.folder_id")
            joins.append("INNER JOIN versions AS v ON s.id = v.product_id")
            joins.append("INNER JOIN representations AS r ON v.id = r.version_id")
            conds.extend(get_representation_conditions(req.representation_name))
            conds.extend(get_version_conditions(req.version_name))
            conds.extend(get_product_conditions(req.product_name))
            conds.extend(get_path_conditions(req.path))
            target_entity_type = "representation"

        elif req.version_name is not None:
            cols.extend(["s.id as product_id", "v.id as version_id"])
            joins.append("INNER JOIN products AS s ON h.id = s.folder_id")
            joins.append("INNER JOIN versions AS v ON s.id = v.product_id")
            conds.extend(get_version_conditions(req.version_name))
            conds.extend(get_product_conditions(req.product_name))
            conds.extend(get_path_conditions(req.path))
            target_entity_type = "version"

        elif req.product_name is not None:
            cols.append("s.id as product_id")
            joins.append("INNER JOIN products AS s ON h.id = s.folder_id")
            conds.extend(get_product_conditions(req.product_name))
            conds.extend(get_path_conditions(req.path))
            target_entity_type = "product"

        else:
            conds.extend(get_path_conditions(req.path))
            target_entity_type = "folder"

    query = f"""
        SELECT {", ".join(cols)}
        FROM hierarchy h {" ".join(joins)}
    """
    if conds:
        query += f""" WHERE {" AND ".join(conds)}"""

    query += " LIMIT 1000"

    statement = await Postgres.prepare(query)
    async for row in statement.cursor():
        file_path = None
        if ("file_template" in row) and ("context" in row):
            if row["file_template"]:
                file_path = get_representation_path(
                    row["file_template"],
                    row["context"],
                    roots,
                )
                file_path = os.path.normpath(file_path)
                file_path = file_path.replace("//", "/")
                if platform == "windows":
                    file_path = file_path.replace("/", "\\")

        if path_only:
            result.append(ResolvedEntityModel(file_path=file_path))
        else:
            result.append(
                ResolvedEntityModel(
                    project_name=req.project_name,
                    file_path=file_path,
                    target=target_entity_type,
                    **row,
                )
            )

    return result


async def get_platform_for_site_id(site_id: str) -> str:
    """Return the platform for the given site id."""
    res = await Postgres.fetch(
        "SELECT data->>'platform' as platform FROM public.sites WHERE id = $1", site_id
    )
    if not res:
        raise BadRequestException(status_code=404, detail="Site not found")
    return res[0]["platform"]


@router.post("/resolve", response_model_exclude_none=True, dependencies=[AllowGuests])
async def resolve_uris(
    request: ResolveRequestModel,
    site_id: ClientSiteID,
    user: CurrentUser,
    path_only: bool = Query(
        False,
        alias="pathOnly",
        description="Return only file paths",
    ),
) -> list[ResolvedURIModel]:
    """Resolve a list of ayon:// URIs to entities.

    Each URI starts with `ayon://{project_name}/{path}` which
    determines the requested folder.

    Schemes `ayon://` and `ayon+entity://` are equivalent (ayon is a shorter alias).

    Additional query arguments [`product`, `version`, `representation`]
    or [`task`, `workfile`] are allowed.
    Note that arguments from product/version/representations cannot be mixed with
    task/workfile arguments.

    ### Implicit wildcards

    The response contains a list of resolved URIs with the requested entities.
    One URI can match multiple entities - for example when
    **product** and **representation** are requested,
    the response will contain all matching **representations**
    from all **versions** of the product.

    ### Explicit wildcards

    It is possible to use a `*` wildcard for querying multiple
    entities at the deepest level of the data structure:

    `ayon://my_project/assets/characters?product=setdress?version=*`
    will return all versions of the given product.

    ### Representation paths

    When a representation is requested, the response will contain the
    resolved file path, and if the request contains `X-ayon-site-id`
    header and `resolve_roots` is set to `true`, in the request,
    the server will resolve the file path to the actual absolute path.

    """

    if Postgres.get_available_connections() < 3:
        msg = f"Postgres remaining pool size: {Postgres.get_available_connections()}"
        raise ServiceUnavailableException(msg)

    roots = {}
    if request.resolve_roots and site_id:
        projects = [parse_uri(uri).project_name for uri in request.uris]
        roots = await get_roots_for_projects(user.name, site_id, projects)

    result: list[ResolvedURIModel] = []
    current_project = ""
    async with Postgres.transaction():
        for uri in request.uris:
            try:
                parsed_uri = parse_uri(uri)
            except ValueError as e:
                result.append(ResolvedURIModel(uri=uri, error=str(e)))
                continue

            if parsed_uri.project_name != current_project:
                try:
                    project_name = await normalize_project_name(parsed_uri.project_name)
                except NotFoundException:
                    result.append(
                        ResolvedURIModel(
                            uri=uri,
                            entities=[],
                            error=f"Project {parsed_uri.project_name} not found",
                        )
                    )
                    continue
                await Postgres.set_project_schema(project_name)
                current_project = parsed_uri.project_name

            try:
                entities = await resolve_entities(
                    parsed_uri,
                    roots.get(project_name, {}),
                    site_id,
                    path_only=path_only,
                )
            except ValueError as e:
                result.append(ResolvedURIModel(uri=uri, entities=[], error=str(e)))
                continue
            result.append(ResolvedURIModel(uri=uri, entities=entities))
    return result
