from collections import Counter
from collections.abc import AsyncGenerator

from pydantic import ValidationError

from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.types import Field, OPModel
from ayon_server.utils import json_dumps

REPLICA_NS = "replicas"
# Set of replica ids, so readers don't have to scan the whole Redis keyspace.
# Liveness is still the per-replica key TTL; the set is only a directory.
REPLICA_INDEX = "index"


class ReplicaInfo(OPModel):
    id: str = Field(..., title="Replica ID", description="Generated on start")
    hostname: str = Field(..., title="Hostname", example="ayon-server-7f9c")
    version: str = Field(..., title="Server version", example="1.17.9+202611271250")
    boot_time: float = Field(..., title="Boot time", example=1795000000.0)
    ready: bool = Field(False, title="Ready", description="Startup finished")
    addons: dict[str, list[str]] = Field(
        default_factory=dict,
        title="Loaded addons",
        description="Addon name to list of loaded versions. Empty until ready.",
        example={"core": ["1.0.0", "1.1.0"]},
    )


class ServerReplicas:
    """Server replicas currently alive, as announced by their heartbeats

    Each replica keeps its own Redis key with a short TTL
    (see ayon_server.background.replica_heartbeat), so dead replicas
    disappear on their own.
    """

    @classmethod
    async def save(cls, info: ReplicaInfo, ttl: int) -> None:
        # key first, so a reader never finds an id without its key
        await Redis.set_json(REPLICA_NS, info.id, info.model_dump(), ttl=ttl)
        await Redis.sadd(REPLICA_NS, REPLICA_INDEX, info.id)

    @classmethod
    async def delete(cls, replica_id: str) -> None:
        await Redis.delete(REPLICA_NS, replica_id)
        await Redis.srem(REPLICA_NS, REPLICA_INDEX, replica_id)

    @classmethod
    async def iter(cls) -> AsyncGenerator[ReplicaInfo]:
        for replica_id in await Redis.smembers(REPLICA_NS, REPLICA_INDEX):
            if (data := await Redis.get_json(REPLICA_NS, replica_id)) is None:
                # Key expired: the replica died without a clean shutdown.
                # Conditional, so a heartbeat landing right now keeps its id.
                await Redis.srem_if_missing(REPLICA_NS, REPLICA_INDEX, replica_id)
                continue
            try:
                yield ReplicaInfo(**data)
            except ValidationError:
                # e.g. a replica of a different version during a rolling update
                logger.debug(f"Invalid replica info for {replica_id}")

    @staticmethod
    def out_of_sync(replicas: list[ReplicaInfo]) -> int:
        """Number of ready replicas that differ from the majority

        Replicas that are still starting are ignored (their addon list is empty).
        Anything above 0 for longer than a rolling update means some replicas
        run a different build or addon set.
        """
        # Only what must match across replicas
        builds = Counter(
            json_dumps(r.model_dump(include={"version", "addons"}))
            for r in replicas
            if r.ready
        )
        if not builds:
            return 0
        return builds.total() - builds.most_common(1)[0][1]
