from typing import Any

from fastapi import APIRouter, Depends, Response
from nxtools import logging
from pydantic import BaseModel, Field

from openpype.api.dependencies import (
    dep_current_user,
    dep_link_id,
    dep_link_type,
    dep_project_name,
)
from openpype.api.responses import EntityIdResponse, ResponseFactory
from openpype.entities import UserEntity
from openpype.exceptions import (
    BadRequestException,
    ConstraintViolationException,
    ForbiddenException,
    NotFoundException,
)
from openpype.lib.postgres import Postgres
from openpype.utils import EntityID

router = APIRouter(
    tags=["Links"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)


class LinkType(BaseModel):
    name: str
    data: dict[str, Any]
    # TODO: link_type, inp_type, out_type ... but after camelize config


class LinkTypeListResponse(BaseModel):
    types: list[dict]


class CreateLinkTypeRequestModel(BaseModel):
    data: dict = Field(default_factory=dict, description="Link data")


@router.get(
    "/projects/{project_name}/links/types",
    operation_id="get_link_types",
)
async def list_link_types(
    project_name: str = Depends(dep_project_name),
    current_user: UserEntity = Depends(dep_current_user),
):
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
    operation_id="create_link_type",
    status_code=201,
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
    operation_id="delete_link_type",
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


class CreateLinkRequestModel(BaseModel):
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
    operation_id="create_entity_link",
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
        raise NotFoundException(f"Input entity {post_data.input_id} not found.")

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
        f"{user.name} created {link_type} link between "
        f"{input_type} {post_data.input} and "
        f"{output_type} {post_data.output}."
    )

    return EntityIdResponse(id=link_id)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/links/{link_id}",
    operation_id="delete_entity_link",
    response_class=Response,
    status_code=204,
)
async def delete_entity_link(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    link_id: str = Depends(dep_link_id),
):
    """Delete a link."""

    # TODO: Access control

    await Postgres.execute(
        f"DELETE FROM project_{project_name}.links WHERE id = $1",
        link_id,
    )

    return Response(status_code=204)
