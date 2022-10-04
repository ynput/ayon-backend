from fastapi import APIRouter, Depends

from openpype.addons import AddonLibrary
from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_current_user
from openpype.entities import UserEntity
from openpype.exceptions import ForbiddenException, NotFoundException
from openpype.lib.postgres import Postgres
from openpype.types import Field, OPModel

router = APIRouter(
    prefix="/services",
    tags=["Services"],
    responses={401: ResponseFactory.error(401)},
)


class ServiceModel(OPModel):
    id: int = Field(...)
    hostname: str = Field(..., example="worker03")
    addon_name: str = Field(..., example="ftrack")
    addon_version: str = Field(..., example="2.0.0")
    service_name: str = Field(..., example="collector")
    image: str = Field(..., example="openpype/ftrack-addon-collector:2.0.0")
    is_running: bool = Field(False)
    last_seen: int = Field(0)


class ServiceListModel(OPModel):
    services: list[ServiceModel] = Field(default_factory=list)


@router.get("", response_model=ServiceListModel)
async def list_services(user: UserEntity = Depends(dep_current_user)):

    query = """
        SELECT
            s.id AS id,
            s.hostname AS hostname,
            s.addon_name AS addon_name,
            s.addon_version AS addon_version,
            s.service_name AS service_name,
            s.image AS image,
            h.services as host_runs,
            h.last_seen as last_seen
        FROM services AS s
        LEFT JOIN hosts AS h
            ON s.hostname = h.name
        ORDER BY s.id DESC
    """

    services = []
    async for row in Postgres.iterate(query):
        is_running = row["id"] in row["host_runs"]
        services.append(ServiceModel(is_running=is_running, **row))

    return ServiceListModel(services=services)


#
# Spawn service
#


class SpawnServiceRequestModel(OPModel):
    addon_name: str
    addon_version: str
    service_name: str
    hostname: str


class SpawnServiceResponseModel(OPModel):
    id: int


@router.post("", response_model=SpawnServiceResponseModel)
async def spawn_service(
    payload: SpawnServiceRequestModel,
    user: UserEntity = Depends(dep_current_user),
):

    if not user.is_admin:
        raise ForbiddenException("Only admins can spawn services")

    library = AddonLibrary.getinstance()
    addon = library.addon(payload.addon_name, payload.addon_version)
    if payload.service_name not in addon.services:
        # TODO: be more verbose
        raise NotFoundException("This addon does not have this service")

    image = addon.services[payload.service_name].get("image")
    assert image is not None  # TODO: raise smarter exception

    res = await Postgres.fetch(
        """
        INSERT INTO SERVICES (hostname, addon_name, addon_version, service_name, image)
        VALUES
        ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        payload.hostname,
        payload.addon_name,
        payload.addon_version,
        payload.service_name,
        image,
    )
    id = res[0]["id"]
    return SpawnServiceResponseModel(id=id)
