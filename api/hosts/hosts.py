import time

from fastapi import APIRouter, Depends

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_current_user
from openpype.entities import UserEntity
from openpype.exceptions import ForbiddenException
from openpype.lib.postgres import Postgres
from openpype.types import OPModel, Field

from services.services import ServiceModel, list_services

router = APIRouter(
    prefix="/hosts",
    tags=["Hosts"],
    responses={401: ResponseFactory.error(401)},
)


@router.get("")
async def list_hosts(user: UserEntity = Depends(dep_current_user)):
    pass


class HostHealthModel(OPModel):
    cpu: float = Field(0, title="CPU utilization", ge=0, le=100)
    mem: float = Field(0, title="RAM utilization", ge=0, le=100)


class HeartbeatRequestModel(OPModel):
    hostname: str
    health: HostHealthModel
    services: list[int] = Field(
        default_factory=list,
        title="List of running service ids",
    )


class HeartbeatResponseModel(OPModel):
    services: list[ServiceModel] = Field(
        default_factory=list,
        title="List of services that should be running",
    )


@router.post("/heartbeat", response_model=HeartbeatResponseModel)
async def host_heartbeat(
    payload: HeartbeatRequestModel,
    user: UserEntity = Depends(dep_current_user),
):

    if not user.is_service:
        raise ForbiddenException("Only services have hearts to beat")

    await Postgres.execute(
        """
        INSERT INTO hosts (name, last_seen, health, services)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (name)
        DO UPDATE SET
            last_seen = $2,
            health = $3,
            services = $4
        """,
        payload.hostname,
        time.time(),
        payload.health.dict(),
        payload.services,
    )

    all_services = (await list_services(user=user)).services
    services = [
        service for service in all_services if service.hostname == payload.hostname
    ]

    return HeartbeatResponseModel(services=services)
