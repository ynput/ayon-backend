from typing import Any

from fastapi import APIRouter, Depends, Response
from nxtools import logging

from ayon_server.api.dependencies import (
    dep_current_user,
    dep_link_id,
    dep_link_type,
    dep_project_name,
)
from ayon_server.api.responses import EntityIdResponse, ResponseFactory
from ayon_server.entities import UserEntity
from ayon_server.exceptions import (
    BadRequestException,
    ConstraintViolationException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel
from ayon_server.utils import EntityID

router = APIRouter(
    tags=["Links"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)


class LinkType(OPModel):
    name: str = Field(..., description="Name of the link type")
    link_type: str = Field(..., description="Type of the link")
    input_type: str = Field(..., description="Input entity type")
    output_type: str = Field(..., description="Output entity type")
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional link type data",
    )


class LinkTypeListResponse(OPModel):
    types: list[dict[str, Any]] = Field(
        ...,
        description="List of link types",
        example=[
            {
                "name": "referene|version|version",
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
        ],
    )


class CreateLinkTypeRequestModel(OPModel):
    data: dict[str, Any] = Field(default_factory=dict, description="Link data")


@router.get(
    "/projects/{project_name}/links/types",
    response_model=LinkTypeListResponse,
)
async def list_link_types(
    project_name: str = Depends(dep_project_name),
    current_user: UserEntity = Depends(dep_current_user),
) -> LinkTypeListResponse:
    """List all link types"""

    types: list[LinkType] = []
    query = f"""
        SELECT name, input_type, output_type, link_type, data
        FROM project_{project_name}.link_types
        """
    async for row in Postgres.iterate(query):
        types.append(LinkType(**row))

    return LinkTypeListResponse(types=types)


@router.put(
    "/projects/{project_name}/links/types/{link_type}",
    status_code=201,
    response_class=Response,
)
async def create_link_type(
    project_name: str = Depends(dep_project_name),
    current_user: UserEntity = Depends(dep_current_user),
    link_type: tuple[str, str, str] = Depends(dep_link_type),
    request_model: CreateLinkTypeRequestModel = Depends(),
):
    """Create new link type"""

    if not current_user.is_manager:
        raise ForbiddenException

    query = f"""
        INSERT INTO project_{project_name}.link_types
        (name, link_type, input_type, output_type, data)
        VALUES ($1, $2, $3, $4, $5)
        """
    await Postgres.execute(
        query,
        f"{link_type[0]}|{link_type[1]}|{link_type[2]}",
        link_type[0],
        link_type[1],
        link_type[2],
        request_model.data,
    )

    return Response(status_code=201)


@router.delete(
    "/projects/{project_name}/links/types/{link_type}",
    status_code=204,
)
async def delete_link_type(
    project_name: str = Depends(dep_project_name),
    current_user: UserEntity = Depends(dep_current_user),
    link_type: tuple[str, str, str] = Depends(dep_link_type),
):
    """Delete link type"""

    if not current_user.is_manager:
        raise ForbiddenException

    query = f"""
        DELETE FROM project_{project_name}.link_types
        WHERE name = $1
        """
    await Postgres.execute(query, f"{link_type[0]}|{link_type[1]}|{link_type[2]}")

    return Response(status_code=204)


#
# [POST]
#


class CreateLinkRequestModel(OPModel):
    """Request model for creating a link."""

    input: str = Field(..., description="The ID of the input entity.")
    output: str = Field(..., description="The ID of the output entity.")
    link: str = Field(
        ...,
        description="The name of the link type to create.",
        example="reference|folder|version",
    )


@router.post(
    "/projects/{project_name}/links",
    status_code=201,
    response_model=EntityIdResponse,
    responses={
        409: ResponseFactory.error(409, "Coflict"),
    },
)
async def create_entity_link(
    post_data: CreateLinkRequestModel,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Create a new entity link."""

    link_type, input_type, output_type = post_data.link.split("|")
    link_id = EntityID.create()

    if input_type == output_type and post_data.input == post_data.output:
        raise BadRequestException("Cannot link an entity to itself.")

    # TODO: access control. Since we need entity class for that,
    # we could get rid of the following check and use Entity.load instead

    # Ensure input_id is in the project

    query = f"""
        SELECT id
        FROM project_{project_name}.{input_type}s
        WHERE id = $1
        """
    for row in await Postgres.fetch(query, post_data.input):
        break
    else:
        raise NotFoundException(f"Input entity {post_data.input} not found.")

    # Ensure output_id is in the project

    query = f"""
        SELECT id
        FROM project_{project_name}.{output_type}s
        WHERE id = $1
        """
    for row in await Postgres.fetch(query, post_data.output):
        break
    else:
        raise NotFoundException(f"Output entity {post_data.output} not found.")

    # Create a link

    try:
        await Postgres.execute(
            f"""
            INSERT INTO project_{project_name}.links
                (id, input_id, output_id, link_name, data)
            VALUES
                ($1, $2, $3, $4, $5)
            """,
            link_id,
            post_data.input,
            post_data.output,
            post_data.link,
            {"author": user.name},
        )
    except Postgres.ForeignKeyViolationError:
        raise BadRequestException("Unsupported link type.")
    except Postgres.UniqueViolationError:
        raise ConstraintViolationException("Link already exists.")

    logging.debug(
        f"Created {link_type} link between "
        f"{input_type} {post_data.input} and "
        f"{output_type} {post_data.output}.",
        user=user.name,
    )

    return EntityIdResponse(id=link_id)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/links/{link_id}",
    response_class=Response,
    status_code=204,
)
async def delete_entity_link(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    link_id: str = Depends(dep_link_id),
):
    """Delete a link.

    Normal users can only delete links they created.
    Managers can delete any link.
    """

    query = f"SELECT data->'author' FROM project_{project_name}.links WHERE id = $1"
    for row in await Postgres.fetch(query, link_id):
        if (row["data"]["author"] != user.name) and (not user.is_manager):
            raise ForbiddenException
        break
    else:
        raise NotFoundException(f"Link {link_id} not found.")

    await Postgres.execute(
        f"DELETE FROM project_{project_name}.links WHERE id = $1",
        link_id,
    )

    return Response(status_code=204)
