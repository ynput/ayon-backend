from fastapi import APIRouter

from ayon_server.api.dependencies import (
    CurrentUser,
    ProductID,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.entities import ProductEntity
from ayon_server.operations.project_level import ProjectLevelOperations

router = APIRouter(tags=["Products"])

#
# [GET]
#


@router.get(
    "/projects/{project_name}/products/{product_id}", response_model_exclude_none=True
)
async def get_product(
    user: CurrentUser,
    project_name: ProjectName,
    product_id: ProductID,
) -> ProductEntity.model.main_model:  # type: ignore
    """Retrieve a product by its ID."""

    product = await ProductEntity.load(project_name, product_id)
    await product.ensure_read_access(user)
    return product.as_user(user)


#
# [POST]
#


@router.post("/projects/{project_name}/products", status_code=201)
async def create_product(
    post_data: ProductEntity.model.post_model,  # type: ignore
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
) -> EntityIdResponse:
    """Create a new product."""

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )
    ops.create("product", **post_data.dict())
    res = await ops.process(can_fail=False, raise_on_error=True)
    entity_id = res.operations[0].entity_id
    return EntityIdResponse(id=entity_id)


#
# [PATCH]
#


@router.patch("/projects/{project_name}/products/{product_id}", status_code=204)
async def update_product(
    post_data: ProductEntity.model.patch_model,  # type: ignore
    user: CurrentUser,
    project_name: ProjectName,
    product_id: ProductID,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Patch (partially update) a product."""

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )
    ops.update("product", product_id, **post_data.dict(exclude_unset=True))
    await ops.process(can_fail=False, raise_on_error=True)
    return EmptyResponse(status_code=204)


#
# [DELETE]
#


@router.delete("/projects/{project_name}/products/{product_id}", status_code=204)
async def delete_product(
    user: CurrentUser,
    project_name: ProjectName,
    product_id: ProductID,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Delete a product.

    This will also delete all the product's versions and representations.
    """

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )
    ops.delete("product", product_id)
    await ops.process(can_fail=False, raise_on_error=True)
    return EmptyResponse(status_code=204)
