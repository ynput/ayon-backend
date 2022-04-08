from fastapi import APIRouter, Depends, Response
from nxtools import logging
from pydantic import BaseModel, Field

from openpype.api.dependencies import dep_current_user, dep_link_id, dep_project_name
from openpype.api.responses import EntityIdResponse, ResponseFactory
from openpype.entities import UserEntity
from openpype.lib.postgres import Postgres
from openpype.utils import EntityID

router = APIRouter(
    tags=["Links"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)


#
# [POST]
#


class CreateLinkRequestModel(BaseModel):
    """Request model for creating a link."""

    input_id: str = Field(..., description="The ID of the input entity.")
    output_id: str = Field(..., description="The ID of the output entity.")
    link_type_name: str = Field(
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

    link_type, input_type, output_type = post_data.link_type_name.split("|")
    link_id = EntityID.create()

    # TODO: access control

    await Postgres.execute(
        f"""
        INSERT INTO project_{project_name}.links
            (id, input_id, output_id, link_name, data)
        VALUES
            ($1, $2, $3, $4, $5)
        """,
        link_id,
        post_data.input_id,
        post_data.output_id,
        post_data.link_type_name,
        {"author": user.name},
    )

    logging.debug(
        f"{user.name} created {link_type} link between "
        f"{input_type} {post_data.input_id} and "
        f"{output_type} {post_data.output_id}."
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
