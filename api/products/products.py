from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header

from ayon_server.api.dependencies import CurrentUser, ProductID, ProjectName
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.entities import ProductEntity
from ayon_server.events import dispatch_event
from ayon_server.events.patch import build_pl_entity_change_events

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
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    x_sender: str | None = Header(default=None),
) -> EntityIdResponse:
    """Create a new product."""

    product = ProductEntity(project_name=project_name, payload=post_data.dict())
    await product.ensure_create_access(user)
    event: dict[str, Any] = {
        "topic": "entity.product.created",
        "description": f"Product {product.name} created",
        "summary": {"entityId": product.id, "parentId": product.parent_id},
        "project": project_name,
    }
    await product.save()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return EntityIdResponse(id=product.id)


#
# [PATCH]
#


@router.patch("/projects/{project_name}/products/{product_id}", status_code=204)
async def update_product(
    post_data: ProductEntity.model.patch_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    product_id: ProductID,
    x_sender: str | None = Header(default=None),
) -> EmptyResponse:
    """Patch (partially update) a product."""

    product = await ProductEntity.load(project_name, product_id)
    await product.ensure_update_access(user)
    events = build_pl_entity_change_events(product, post_data)
    product.patch(post_data)
    await product.save()
    for event in events:
        background_tasks.add_task(
            dispatch_event,
            sender=x_sender,
            user=user.name,
            **event,
        )
    return EmptyResponse(status_code=204)


#
# [DELETE]
#


@router.delete("/projects/{project_name}/products/{product_id}", status_code=204)
async def delete_product(
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    product_id: ProductID,
    x_sender: str | None = Header(default=None),
) -> EmptyResponse:
    """Delete a product.

    This will also delete all the product's versions and representations.
    """

    product = await ProductEntity.load(project_name, product_id)
    await product.ensure_delete_access(user)
    event: dict[str, Any] = {
        "topic": "entity.product.deleted",
        "description": f"Product {product.name} deleted",
        "summary": {"entityId": product.id, "parentId": product.parent_id},
        "project": project_name,
    }
    await product.delete()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return EmptyResponse()
