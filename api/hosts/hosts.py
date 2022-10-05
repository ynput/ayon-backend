import time

from fastapi import APIRouter, Depends
from services.services import ServiceModel, list_services

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_current_user
from openpype.entities import UserEntity
from openpype.exceptions import ForbiddenException
from openpype.lib.postgres import Postgres
from openpype.types import Field, OPModel

router = APIRouter(
    prefix="/hosts",
    tags=["Hosts"],
    responses={401: ResponseFactory.error(401)},
)


class HostHealthModel(OPModel):
    cpu: float = Field(0, title="CPU utilization", ge=0, le=100)
    mem: float = Field(0, title="RAM utilization", ge=0, le=100)


class HostModel(OPModel):
    name: str
    last_seen: int
    health: HostHealthModel


class HostListResponseModel(OPModel):
    hosts: list[HostModel]


class HeartbeatRequestModel(OPModel):
    hostname: str
    health: HostHealthModel
    services: list[str] = Field(
        default_factory=list,
        title="List of running services",
    )


class HeartbeatResponseModel(OPModel):
    services: list[ServiceModel] = Field(
        default_factory=list,
        title="List of services that should be running",
    )


@router.get("", response_model=HostListResponseModel)
async def list_hosts(user: UserEntity = Depends(dep_current_user)):
    return HostListResponseModel(
        hosts=[
            HostModel(**row) async for row in Postgres.iterate("SELECT * FROM hosts")
        ]
    )


@router.post("/heartbeat", response_model=HeartbeatResponseModel)
async def host_heartbeat(
    payload: HeartbeatRequestModel,
    user: UserEntity = Depends(dep_current_user),
):

    if not user.is_service:
        raise ForbiddenException("Only services have hearts to beat")

    now = time.time()

    async with Postgres.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO hosts (name, last_seen, health)
                VALUES ($1, $2, $3)
                ON CONFLICT (name)
                DO UPDATE SET
                    last_seen = $2,
                    health = $3
                """,
                payload.hostname,
                time.time(),
                payload.health.dict(),
            )

            await conn.execute(
                """
                UPDATE services SET
                is_running = (name = ANY($1::VARCHAR[]))::BOOL,
                last_seen = $2
                WHERE hostname = $3
                """,
                payload.services,
                now,
                payload.hostname,
            )

    all_services = (await list_services(user=user)).services
    services = [
        service
        for service in all_services
        if service.hostname == payload.hostname and service.should_run
    ]

    return HeartbeatResponseModel(services=services)
