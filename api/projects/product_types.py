from typing import Annotated

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.types import Field, OPModel

from .anatomy import _get_project_anatomy
from .router import router


class ProductTypeListItemModel(OPModel):
    product_type: Annotated[str, Field(title="Product Type Name")]
    product_base_type: Annotated[str | None, Field(title="Base Product Type Name")] = (
        None
    )
    color: Annotated[str | None, Field(title="Color")] = None
    icon: Annotated[str | None, Field(title="Icon")] = None


class DefaultProductTypeModel(OPModel):
    color: Annotated[str, Field(title="Color")]
    icon: Annotated[str, Field(title="Icon")]


class ProductTypesListModel(OPModel):
    product_types: Annotated[
        list[ProductTypeListItemModel],
        Field(
            title="Product Types",
            default_factory=list,
        ),
    ]

    default: DefaultProductTypeModel


@router.get("/projects/{project_name}/productTypes")
async def list_product_types(
    user: CurrentUser,
    project_name: ProjectName,
) -> ProductTypesListModel:
    """Retrieve a project statistics by its name."""

    user.check_permissions("project.access", project_name)
    anatomy = await _get_project_anatomy(project_name)

    default = DefaultProductTypeModel(
        color=anatomy.product_base_types.default.color,
        icon=anatomy.product_base_types.default.icon,
    )

    product_types = []

    for pt in anatomy.product_base_types.definitions:
        product_types.append(
            ProductTypeListItemModel(
                product_type=pt.name,
                product_base_type=pt.name,
                color=pt.color or anatomy.product_base_types.default.color,
                icon=pt.icon or anatomy.product_base_types.default.icon,
            )
        )

    return ProductTypesListModel(product_types=product_types, default=default)
