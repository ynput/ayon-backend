__all__ = ["router"]

from typing import Annotated

from fastapi import APIRouter, Query

from ayon_server.addons.models import TraitDefinitionListItem
from ayon_server.addons.traits import get_trait_definitions
from ayon_server.api.dependencies import AllowGuests, CurrentUser, ProjectName
from ayon_server.traits.fields import (
    MAX_VALUES_LIMIT,
    ProjectTraitFields,
    TraitFieldValue,
    apply_filtering_settings,
    get_filtering_settings,
    get_project_trait_fields,
    get_trait_field_values,
)

router = APIRouter(tags=["Traits"])


@router.get("/traits", dependencies=[AllowGuests])
async def list_trait_definitions(
    user: CurrentUser,
    variant: Annotated[
        str | None,
        Query(
            description=(
                "Limit the result to addons of the given bundle variant "
                "(production, staging or a dev bundle name). "
                "If not set, all installed addon versions are used."
            ),
        ),
    ] = None,
) -> list[TraitDefinitionListItem]:
    """List definitions of representation traits provided by addons.

    Definitions are read from the trait manifests shipped with addons
    and merged by versioned trait ID. Items defined with different data
    models by installed addon versions are flagged as `conflict`.
    """

    return await get_trait_definitions(variant=variant)


@router.get("/projects/{project_name}/traitFields")
async def list_project_trait_fields(
    user: CurrentUser,
    project_name: ProjectName,
    variant: Annotated[
        str,
        Query(description="Bundle variant whose core addon settings are applied"),
    ] = "production",
) -> ProjectTraitFields:
    """List traits and trait fields used by representations of the project.

    Use the fields in representation filters as
    `traits/<versionless trait id>/<field>`, the traits as `traitIds`.
    Only fields with a value short enough to be indexed are listed:
    numbers, booleans, strings of up to 64 characters and lists of up
    to 32 such values.

    Only the fields exposed by the `traits_filtering` project settings
    of the core addon are listed (all used traits are, for `traitIds`).
    Other fields still work in filters.

    The result is cached for a minute.
    """

    await user.ensure_project_access(project_name)
    result = await get_project_trait_fields(project_name)
    settings = await get_filtering_settings(project_name, variant)
    return apply_filtering_settings(result, settings)


@router.get("/projects/{project_name}/traitFields/values")
async def list_trait_field_values(
    user: CurrentUser,
    project_name: ProjectName,
    trait: Annotated[
        str,
        Query(
            description="Trait ID, versionless for all versions",
            examples=["ayon.2d.PixelBased"],
        ),
    ],
    field: Annotated[
        str,
        Query(description="Field name", examples=["display_window_width"]),
    ],
    search: Annotated[
        str | None,
        Query(description="Case insensitive substring of the value"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_VALUES_LIMIT)] = 50,
) -> list[TraitFieldValue]:
    """List the most frequent values of a trait field in the project."""

    await user.ensure_project_access(project_name)
    return await get_trait_field_values(
        project_name, trait, field, search=search, limit=limit
    )
