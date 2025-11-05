from typing import Annotated

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.helpers.anatomy import get_project_anatomy
from ayon_server.types import Field, OPModel

from .router import router


class ProductTypeListItem(OPModel):
    name: Annotated[str, Field(title="Product Type Name")]
    base_type: Annotated[str | None, Field(title="Base Product Type Name")] = None
    color: Annotated[str | None, Field(title="Color")] = None
    icon: Annotated[str | None, Field(title="Icon")] = None


class DefaultProductType(OPModel):
    color: Annotated[str, Field(title="Color")]
    icon: Annotated[str, Field(title="Icon")]


class ProductTypesList(OPModel):
    product_types: Annotated[
        list[ProductTypeListItem],
        Field(
            title="Product Types",
            default_factory=list,
        ),
    ]

    default: DefaultProductType


@router.get("/projects/{project_name}/productTypes")
async def get_product_types(
    user: CurrentUser,
    project_name: ProjectName,
) -> ProductTypesList:
    """Retrieve a project statistics by its name."""

    user.check_permissions("project.access", project_name)
    anatomy = await get_project_anatomy(project_name)

    default = DefaultProductType(
        color=anatomy.product_base_types.default.color,
        icon=anatomy.product_base_types.default.icon,
    )

    product_types = []

    for pt in anatomy.product_base_types.definitions:
        product_types.append(
            ProductTypeListItem(
                name=pt.name,
                base_type=pt.name,
                color=pt.color or anatomy.product_base_types.default.color,
                icon=pt.icon or anatomy.product_base_types.default.icon,
            )
        )

    return ProductTypesList(product_types=product_types, default=default)
