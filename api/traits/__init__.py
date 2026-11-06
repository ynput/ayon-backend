__all__ = ["router"]

from typing import Annotated

from fastapi import APIRouter, Query

from ayon_server.addons.models import TraitDefinitionListItem
from ayon_server.addons.traits import get_trait_definitions
from ayon_server.api.dependencies import AllowGuests, CurrentUser

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
