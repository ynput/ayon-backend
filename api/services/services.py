from datetime import datetime
from typing import Any

from fastapi import Path

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import CurrentUser, NoTraces
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel
from ayon_server.utils import SQLTool

from .router import router

#
# Models
#


class RegistryAuth(OPModel):
    username: str
    password: str


class ServiceConfigModel(OPModel):
    volumes: list[str] | None = Field(None, title="Volumes", example=["/tmp:/tmp"])
    ports: list[str] | None = Field(None, title="Ports", example=["8080:8080"])
    mem_limit: str | None = Field(None, title="Memory Limit", example="1g")
    user: str | None = Field(None, title="User", example="1000")
    env: dict[str, Any] = Field(default_factory=dict)
    storage_path: str | None = Field(None, title="Storage", example="/mnt/storage")
    registry_auth: RegistryAuth | None = None


class ServiceDataModel(ServiceConfigModel):
    image: str | None = Field(None, example="ayon/ftrack-addon-leecher:2.0.0")
    error: str | None = Field(None, title="Error", example="Failed to start service")


class ServiceModel(OPModel):
    name: str = Field(...)
    hostname: str = Field(..., example="worker03")
    addon_name: str = Field(..., example="ftrack")
    addon_version: str = Field(..., example="2.0.0")
    service: str = Field(..., example="collector")
    should_run: bool = Field(...)
    is_running: bool = Field(...)
    last_seen: datetime | None = Field(None)
    last_seen_delta: float | None = Field(None)
    data: ServiceDataModel = Field(default_factory=ServiceDataModel)


class ServiceListModel(OPModel):
    services: list[ServiceModel] = Field(default_factory=list)


#
# Utilities
#


async def validate_data(
    addon_name: str,
    addon_version: str,
    service: str,
    data: dict[str, Any],
) -> None:
    addon = AddonLibrary.addon(addon_name, addon_version)

    if service not in addon.services:
        raise BadRequestException("No such service")

    service_def = addon.services[service]

    if "image" in data:
        image = data["image"]
        if image != service_def.get("image"):
            raise BadRequestException("Invalid image")


#
# Endpoints
#


@router.get("/services", dependencies=[NoTraces])
async def list_services(user: CurrentUser) -> ServiceListModel:
    if not user.is_admin:
        return ServiceListModel(services=[])

    query = """
        SELECT *, extract(epoch from (now() - last_seen)) as last_seen_delta
        FROM services ORDER BY name ASC
    """

    services = []
    disable_services = {}
    for row in await Postgres.fetch(query):
        services.append(ServiceModel(**row))

        if services[-1].is_running and services[-1].data.error is not None:
            services[-1].data.error = None
            await Postgres.execute(
                """
                UPDATE services SET
                    data = jsonb_set(data, '{error}', 'null'::jsonb)
                WHERE name = $1
                """,
                row["name"],
            )

        try:
            await validate_data(
                addon_name=row["addon_name"],
                addon_version=row["addon_version"],
                service=row["service"],
                data=row["data"],
            )
        except (NotFoundException, BadRequestException) as e:
            disable_services[row["name"]] = str(e)
            services[-1].should_run = False

    for s_name, s_error in disable_services.items():
        await Postgres.execute(
            """
            UPDATE services SET
                should_run = false,
                data = jsonb_set(data, '{error}', $1)
            WHERE name = $2
            """,
            s_error,
            s_name,
        )

    return ServiceListModel(services=services)


#
# Spawn service
#


class SpawnServiceRequestModel(OPModel):
    addon_name: str = Field(..., title="Addon name", example="ftrack")
    addon_version: str = Field(..., title="Addon version", example="2.0.0")
    service: str = Field(..., title="Service", example="leecher")
    hostname: str = Field(..., title="Host", example="worker03")
    config: ServiceConfigModel = Field(default_factory=ServiceConfigModel)


@router.put("/services/{name}", status_code=204)
async def spawn_service(
    payload: SpawnServiceRequestModel,
    user: CurrentUser,
    name: str = Path(...),
) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("Only admins can spawn services")

    library = AddonLibrary.getinstance()
    addon = library.addon(payload.addon_name, payload.addon_version)
    if payload.service not in addon.services:
        # TODO: be more verbose
        raise NotFoundException("This addon does not have this service")

    image = addon.services[payload.service].get("image")
    if image is None:
        raise BadRequestException("This service does not have an image")

    data = payload.config.dict()
    data["image"] = image

    await validate_data(
        addon_name=payload.addon_name,
        addon_version=payload.addon_version,
        service=payload.service,
        data=data,
    )

    await Postgres.execute(
        """
        INSERT INTO SERVICES (
            name,
            hostname,
            addon_name,
            addon_version,
            service,
            data
        )
        VALUES
            ($1, $2, $3, $4, $5, $6)
        """,
        name,
        payload.hostname,
        payload.addon_name,
        payload.addon_version,
        payload.service,
        data,
    )

    return EmptyResponse()


@router.delete("/services/{name}", status_code=204)
async def delete_service(user: CurrentUser, name: str = Path(...)) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("Only admins can delete services")
    await Postgres.execute("DELETE FROM services WHERE name = $1", name)
    return EmptyResponse()


class PatchServiceRequestModel(ServiceConfigModel):
    should_run: bool | None = Field(None)
    error: str | None = Field(None)
    hostname: str | None = Field(None)

    # Deprecated, kept for backwards compatibility
    config: ServiceConfigModel | None = Field(
        None,
        title="Config",
        deprecated=True,
        description="Deprecated, use top level fields instead",
        example={},
    )


@router.patch("/services/{service_name}", status_code=204)
async def patch_service(
    payload: PatchServiceRequestModel,
    user: CurrentUser,
    service_name: str = Path(...),
) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("Only admins can modify services")

    query = """
        SELECT
            should_run,
            addon_name,
            addon_version,
            service,
            data
        FROM services
        WHERE name = $1 LIMIT 1
    """
    service_data_record = await Postgres.fetchrow(query, service_name)
    if service_data_record is None:
        raise NotFoundException("Service not found")

    service_data = dict(service_data_record)

    patch_dict = payload.dict(exclude_unset=True)

    if (should_run := patch_dict.pop("should_run", None)) is not None:
        service_data["should_run"] = should_run

    if (hostname := patch_dict.pop("hostname", None)) is not None:
        service_data["hostname"] = hostname

    if (error := patch_dict.pop("error", None)) is not None:
        if service_data["should_run"]:
            service_data["data"].pop("error", None)
        else:
            service_data["data"]["error"] = error

    # Old-style config (deprecated)
    if (patch_config := patch_dict.pop("config", None)) is not None:
        service_data["data"].update(patch_config)

    # at this point patch_dict should only contain config fields
    # and this is the new style config that should take precedence
    service_data["data"].update(patch_dict)

    await validate_data(
        addon_name=service_data["addon_name"],
        addon_version=service_data["addon_version"],
        service=service_data["service"],
        data=service_data["data"],
    )

    await Postgres.execute(
        *SQLTool.update(
            "services",
            f"WHERE name='{service_name}'",
            **service_data,
        )
    )
    return EmptyResponse()
