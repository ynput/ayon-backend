from typing import Any

from fastapi import APIRouter

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.settings.anatomy import Anatomy
from ayon_server.settings.postprocess import postprocess_settings_schema
from ayon_server.types import Field, OPModel

router = APIRouter(tags=["Anatomy"], prefix="/anatomy")

VERSION = "1.0.0"


class AnatomyPresetListItem(OPModel):
    name: str = Field(..., title="Name of the preset")
    primary: bool = Field(..., title="Is this preset primary")
    version: str = Field(..., title="Version of the anatomy model")


class AnatomyPresetListModel(OPModel):
    version: str = Field(
        ...,
        title="Model version",
        description="Anatomy model version currently used in Ayon",
    )
    presets: list[AnatomyPresetListItem] = Field(
        default_factory=list,
        title="List of anatomy presets",
    )


@router.get("/schema")
async def get_anatomy_schema(user: CurrentUser) -> dict[str, Any]:
    """Returns the anatomy JSON schema.

    The schema is used to display the anatomy preset editor form.
    """

    schema = Anatomy.schema()
    await postprocess_settings_schema(schema, Anatomy)
    return schema


@router.get("/presets")
async def get_anatomy_presets(user: CurrentUser) -> AnatomyPresetListModel:
    """Return a list of stored anatomy presets."""

    presets = []
    query = "SELECT * from anatomy_presets ORDER BY name, version"
    async for row in Postgres.iterate(query):
        presets.append(
            AnatomyPresetListItem(
                name=row["name"],
                primary=row["is_primary"],
                version=row["version"],
            )
        )
    return AnatomyPresetListModel(version=VERSION, presets=presets)


@router.get("/presets/{preset_name}")
async def get_anatomy_preset(preset_name: str, user: CurrentUser) -> Anatomy:
    """Returns the anatomy preset with the given name.

    - Use `__builtin__` character as a preset name to return the builtin preset.
    - Use `__primary__` character as a preset name to return the primary preset.
    - `_` is an alias for built in preset (deprecated, kept for backward compatibility).
    """

    if preset_name == "__builtin__" or preset_name == "_":
        tpl = Anatomy()
        return tpl

    query: tuple[str, str, str] | tuple[str]
    if preset_name == "__primary__":
        query = ("SELECT * FROM anatomy_presets WHERE is_primary = TRUE",)
    else:
        query = (
            "SELECT * FROM anatomy_presets WHERE name = $1 AND version = $2",
            preset_name,
            VERSION,
        )

    res = await Postgres.fetchrow(*query)
    if res:
        tpl = Anatomy(**res["data"])
        return tpl

    if preset_name == "__primary__":
        # Primary preset not found, return the builtin preset
        tpl = Anatomy()
        return tpl
    raise NotFoundException(f"Anatomy preset {preset_name} not found.")


@router.put("/presets/{preset_name}", status_code=204)
async def update_anatomy_preset(
    preset_name: str, preset: Anatomy, user: CurrentUser
) -> EmptyResponse:
    """Create/update an anatomy preset with the given name."""

    if not user.is_manager:
        raise ForbiddenException("Only managers can update anatomy presets.")

    if preset_name == "__builtin__":
        raise BadRequestException("Cannot update builtin preset.")
    if preset_name == "__primary__":
        raise BadRequestException("Cannot update primary preset using a reference.")

    await Postgres.execute(
        """
        INSERT INTO anatomy_presets (name, version, data)
        VALUES ($1, $2, $3)
        ON CONFLICT (name, version) DO update
        SET data = $4
        """,
        preset_name,
        VERSION,
        preset.dict(),
        preset.dict(),
    )
    return EmptyResponse()


@router.post("/presets/{preset_name}/primary", status_code=204)
async def set_primary_preset(preset_name: str, user: CurrentUser) -> EmptyResponse:
    """Set the given preset as the primary preset."""

    if not user.is_manager:
        raise ForbiddenException("Only managers can set primary preset.")

    async with Postgres.transaction():
        await Postgres.execute(
            """
            UPDATE anatomy_presets
            SET is_primary = FALSE
            WHERE is_primary = TRUE
            """
        )
        if preset_name != "_":
            await Postgres.execute(
                """
                UPDATE anatomy_presets
                SET is_primary = TRUE
                WHERE name = $1
                """,
                preset_name,
            )
    return EmptyResponse()


@router.delete("/presets/{preset_name}/primary", status_code=204)
async def unset_primary_preset(preset_name: str, user: CurrentUser) -> EmptyResponse:
    """Unset the primary preset."""

    if not user.is_manager:
        raise ForbiddenException("Only managers can unset primary preset.")

    async with Postgres.transaction():
        query = "UPDATE anatomy_presets SET is_primary = FALSE WHERE name = $1"
        await Postgres.execute(query, preset_name)
    return EmptyResponse()


class RenamePresetModel(OPModel):
    name: str = Field(
        ...,
        title="New name of the anatomy preset",
        description="The new name of the anatomy preset.",
    )


@router.post("/presets/{preset_name}/rename", status_code=204)
async def rename_anatomy_preset(
    preset_name: str,
    user: CurrentUser,
    payload: RenamePresetModel,
) -> EmptyResponse:
    """Set the given preset as the primary preset."""

    if not user.is_manager:
        raise ForbiddenException("Only managers can set primary preset.")

    query = """
        UPDATE anatomy_presets
        SET name = $1
        WHERE name = $2
        RETURNING *
    """

    res = await Postgres.fetch(query, payload.name, preset_name)

    if not res:
        raise NotFoundException(f"Anatomy preset {preset_name} not found.")

    return EmptyResponse()


@router.delete("/presets/{preset_name}", status_code=204)
async def delete_anatomy_preset(preset_name: str, user: CurrentUser) -> EmptyResponse:
    """Delete the anatomy preset with the given name."""

    if not user.is_manager:
        raise ForbiddenException("Only managers can set primary preset.")

    async with Postgres.transaction():
        query = "DELETE FROM anatomy_presets WHERE name = $1"
        await Postgres.execute(query, preset_name)

    return EmptyResponse()
