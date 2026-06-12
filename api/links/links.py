from typing import Annotated, Any

from fastapi import APIRouter

from ayon_server.api.dependencies import (
    CurrentUser,
    LinkID,
    LinkType,
    ProjectName,
)
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.entities.models.submodels import LinkTypeModel
from ayon_server.events import EventStream
from ayon_server.exceptions import (
    BadRequestException,
    ConstraintViolationException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import Field, OPModel
from ayon_server.utils import EntityID

router = APIRouter(tags=["Links"])


LINK_TYPE_LIST_EXAMPLE = [
    {
        "name": "reference|version|version",
        "link_type": "reference",
        "input_type": "version",
        "output_type": "version",
        "data": {},
    },
    {
        "name": "breakdown|folder|folder",
        "link_type": "breakdown",
        "input_type": "folder",
        "output_type": "folder",
        "data": {},
    },
]


class LinkTypeListResponse(OPModel):
    types: Annotated[
        list[LinkTypeModel],
        Field(
            description="List of link types defined in the project.",
            example=LINK_TYPE_LIST_EXAMPLE,
        ),
    ]


class CreateLinkTypeRequestModel(OPModel):
    data: Annotated[
        dict[str, Any],
        Field(
            default_factory=dict,
            description="Additional link type data (appearance, description, etc.).",
        ),
    ]


@router.get("/projects/{project_name}/links/types")
async def list_link_types(
    project_name: ProjectName,
    user: CurrentUser,
) -> LinkTypeListResponse:
    """List all link types"""

    await user.ensure_project_access(project_name)

    types: list[LinkTypeModel] = []
    query = f"""
        SELECT name, input_type, output_type, link_type, data
        FROM project_{project_name}.link_types
        """
    async for row in Postgres.iterate(query):
        types.append(LinkTypeModel(**row))

    return LinkTypeListResponse(types=types)


@router.put("/projects/{project_name}/links/types/{link_type}", status_code=204)
async def save_link_type(
    project_name: ProjectName,
    user: CurrentUser,
    link_type: LinkType,
    request_model: CreateLinkTypeRequestModel,
) -> EmptyResponse:
    """Save a link type"""

    user.check_permissions("project.anatomy", project_name, write=True)

    query = f"""
        INSERT INTO project_{project_name}.link_types
        (name, link_type, input_type, output_type, data)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (name) DO UPDATE
        SET data = $5
        """
    await Postgres.execute(
        query,
        f"{link_type[0]}|{link_type[1]}|{link_type[2]}",
        link_type[0],
        link_type[1],
        link_type[2],
        request_model.data,
    )

    return EmptyResponse()


@router.delete(
    "/projects/{project_name}/links/types/{link_type}",
    status_code=204,
)
async def delete_link_type(
    project_name: ProjectName,
    user: CurrentUser,
    link_type: LinkType,
) -> EmptyResponse:
    """Delete link type"""

    user.check_permissions("project.anatomy", project_name, write=True)

    query = f"""
        DELETE FROM project_{project_name}.link_types
        WHERE name = $1
        """
    await Postgres.execute(query, f"{link_type[0]}|{link_type[1]}|{link_type[2]}")

    return EmptyResponse()


#
# [POST]
#


class CreateLinkRequestModel(OPModel):
    """Request model for creating a link."""

    id: Annotated[
        str | None,
        Field(
            title="Link ID",
            description="ID of the link to create. If not provided, will be generated.",
            **EntityID.META,
        ),
    ] = None

    input: Annotated[
        str,
        Field(
            title="Input ID", description="The ID of the input entity.", **EntityID.META
        ),
    ]

    output: Annotated[
        str,
        Field(
            title="Output ID",
            description="The ID of the output entity.",
            **EntityID.META,
        ),
    ]

    name: Annotated[
        str | None,
        Field(
            title="Link Name",
            description="The name of the link.",
        ),
    ] = None

    link_type: Annotated[
        str | None,
        Field(
            title="Link Type",
            description="Link type to create.",
            example="reference|folder|version",
        ),
    ] = None

    data: Annotated[
        dict[str, Any],
        Field(
            title="Link Data",
            default_factory=dict,
            description="Additional data for the link.",
        ),
    ]

    # Deprecated field, kept for backward compatibility
    link: str | None = Field(
        None,
        description="Link type to create. This is deprecated. Use linkType instead.",
        example="reference|folder|version",
    )


class CreateLinksRequestModel(OPModel):
    """Request model for creating multiple links at once."""

    links: Annotated[
        list[CreateLinkRequestModel],
        Field(
            title="Links",
            description="List of links to create.",
        ),
    ]


class LinkCreatedItem(OPModel):
    id: Annotated[str, Field(**EntityID.META)]
    input: Annotated[str, Field(**EntityID.META)]
    output: Annotated[str, Field(**EntityID.META)]
    link_type: str


class CreateLinksResponseModel(OPModel):
    created: Annotated[
        list[LinkCreatedItem],
        Field(description="List of successfully created links."),
    ]


@router.post("/projects/{project_name}/links/bulk")
async def create_entity_links_bulk(
    user: CurrentUser,
    project_name: ProjectName,
    post_data: CreateLinksRequestModel,
    sender: Sender,
    sender_type: SenderType,
) -> CreateLinksResponseModel:
    """Create multiple entity links in a single request.

    All links are created within a single transaction — if any link fails
    validation or insertion, the entire batch is rolled back.
    """

    # Parse and validate all link entries upfront (before touching the DB)
    parsed_links: list[dict[str, Any]] = []
    perms = None if user.is_manager else user.permissions(project_name)

    for link in post_data.links:
        link_type = link.link_type or link.link
        if link_type is None:
            raise BadRequestException("Link type is not specified")

        if perms is not None:
            if perms.links.enabled and link_type not in perms.links.link_types:
                raise ForbiddenException(
                    "You do not have permission to create this link type."
                )

        if len(link_type.split("|")) != 3:
            raise BadRequestException(
                "Link type must be in the format 'name|input_type|output_type'"
            )

        link_type_name, input_type, output_type = link_type.split("|")
        link_id = link.id or EntityID.create()

        if input_type == output_type and link.input == link.output:
            raise BadRequestException("Cannot link an entity to itself.")

        parsed_links.append(
            {
                "id": link_id,
                "input": link.input,
                "output": link.output,
                "name": link.name,
                "link_type": link_type,
                "link_type_name": link_type_name,
                "input_type": input_type,
                "output_type": output_type,
                "data": link.data,
            }
        )

    # Collect entity IDs grouped by type for bulk existence checks
    entity_ids_by_type: dict[str, set[str]] = {}
    for pl in parsed_links:
        entity_ids_by_type.setdefault(pl["input_type"], set()).add(pl["input"])
        entity_ids_by_type.setdefault(pl["output_type"], set()).add(pl["output"])

    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)

        # Validate that all referenced entities exist
        for entity_type, ids in entity_ids_by_type.items():
            ids_list = list(ids)
            rows = await Postgres.fetch(
                f"SELECT id FROM {entity_type}s WHERE id = ANY($1::uuid[])",
                ids_list,
            )
            found_ids = {str(row["id"]) for row in rows}
            missing = set(ids_list) - found_ids
            if missing:
                raise NotFoundException(
                    f"{entity_type.capitalize()} entities not found: "
                    + ", ".join(sorted(missing))
                )

        # Bulk-insert all links in one round-trip
        try:
            await Postgres.executemany(
                """
                INSERT INTO links
                    (id, name, input_id, output_id, link_type, author, data)
                VALUES
                    ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (
                        pl["id"],
                        pl["name"],
                        pl["input"],
                        pl["output"],
                        pl["link_type"],
                        user.name,
                        pl["data"],
                    )
                    for pl in parsed_links
                ],
            )
        except Postgres.ForeignKeyViolationError:
            raise BadRequestException("Unsupported link type.") from None
        except Postgres.UniqueViolationError:
            raise ConstraintViolationException(
                "One or more link IDs already exist."
            ) from None

        await EventStream.dispatch(
            "links.created",
            summary={
                "count": len(parsed_links),
                "links": [
                    {
                        "id": pl["id"],
                        "linkType": pl["link_type_name"],
                        "inputType": pl["input_type"],
                        "outputType": pl["output_type"],
                        "inputId": pl["input"],
                        "outputId": pl["output"],
                    }
                    for pl in parsed_links
                ],
            },
            description=f"Created {len(parsed_links)} links.",
            project=project_name,
            user=user.name,
            sender=sender,
            sender_type=sender_type,
        )

    logger.debug(f"Created {len(parsed_links)} links in bulk for project {project_name}.")

    return CreateLinksResponseModel(
        created=[
            LinkCreatedItem(
                id=pl["id"],
                input=pl["input"],
                output=pl["output"],
                link_type=pl["link_type"],
            )
            for pl in parsed_links
        ]
    )


@router.post("/projects/{project_name}/links")
async def create_entity_link(
    user: CurrentUser,
    project_name: ProjectName,
    post_data: CreateLinkRequestModel,
) -> EntityIdResponse:
    """Create a new entity link."""

    # TODO: access control. Since we need entity class for that,
    # we could get rid of the following check and use Entity.load instead

    link_type = post_data.link_type or post_data.link

    if link_type is None:
        raise BadRequestException("Link type is not specified")

    if not user.is_manager:
        perms = user.permissions(project_name)
        if perms.links.enabled and link_type not in perms.links.link_types:
            raise ForbiddenException(
                "You do not have permission to create this link type."
            )

    if len(link_type.split("|")) != 3:
        msg = "Link type must be in the format 'name|input_type|output_type'"
        raise BadRequestException(msg)

    link_type_name, input_type, output_type = link_type.split("|")
    link_id = post_data.id or EntityID.create()

    if input_type == output_type and post_data.input == post_data.output:
        raise BadRequestException("Cannot link an entity to itself.")

    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        # Ensure input_id is in the project
        query = f"SELECT id FROM {input_type}s WHERE id = $1"
        res = await Postgres.fetchrow(query, post_data.input)
        if not res:
            raise NotFoundException(f"Input entity {post_data.input} not found.")

        # Ensure output_id is in the project
        query = f"SELECT id FROM {output_type}s WHERE id = $1"
        res = await Postgres.fetchrow(query, post_data.output)
        if not res:
            raise NotFoundException(f"Output entity {post_data.output} not found.")

        # Create a link
        try:
            await Postgres.execute(
                """
                INSERT INTO links
                    (id, name, input_id, output_id, link_type, author, data)
                VALUES
                    ($1, $2, $3, $4, $5, $6, $7)
                """,
                link_id,
                post_data.name,
                post_data.input,
                post_data.output,
                link_type,
                user.name,
                post_data.data,
            )
        except Postgres.ForeignKeyViolationError:
            raise BadRequestException("Unsupported link type.") from None
        except Postgres.UniqueViolationError:
            raise ConstraintViolationException("Link already exists.") from None

        # Emit an event

        event_summary = {
            "id": link_id,
            "linkType": link_type_name,
            "inputType": input_type,
            "outputType": output_type,
            "inputId": post_data.input,
            "outputId": post_data.output,
        }

        event_description = (
            f"Created {link_type_name} link between "
            f"{input_type} {post_data.input} and {output_type} {post_data.output}."
        )

        await EventStream.dispatch(
            "link.created",
            summary=event_summary,
            description=event_description,
            project=project_name,
            user=user.name,
        )

    logger.debug(
        f"Created {link_type_name} link between "
        f"{input_type} {post_data.input} and "
        f"{output_type} {post_data.output}."
    )

    return EntityIdResponse(id=link_id)


#
# [DELETE]
#


@router.delete("/projects/{project_name}/links/{link_id}", status_code=204)
async def delete_entity_link(
    user: CurrentUser,
    project_name: ProjectName,
    link_id: LinkID,
) -> EmptyResponse:
    """Delete a link.

    Normal users can only delete links they created.
    Managers can delete any link.
    """

    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)

        query = "SELECT input_id, output_id, link_type, author FROM links WHERE id = $1"
        res = await Postgres.fetchrow(query, link_id)
        if not res:
            raise NotFoundException(f"Link {link_id} not found.")

        link_type = res["link_type"]
        link_type_name, input_type, output_type = link_type.split("|")

        if res["author"] != user.name and not user.is_manager:
            raise ForbiddenException("You do not have permission to delete this link.")

        query = "DELETE FROM links WHERE id = $1"
        await Postgres.execute(query, link_id)

        await EventStream.dispatch(
            "link.deleted",
            summary={
                "id": link_id,
                "linkType": link_type_name,
                "inputType": input_type,
                "outputType": output_type,
                "inputId": res["input_id"],
                "outputId": res["output_id"],
            },
            description=(
                f"Deleted {link_type_name} link between "
                f"{input_type} {res['input_id']} and {output_type} {res['output_id']}."
            ),
            project=project_name,
            user=user.name,
        )

    return EmptyResponse()
