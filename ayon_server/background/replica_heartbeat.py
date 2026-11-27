import asyncio
import socket
import uuid

from ayon_server.addons import AddonLibrary
from ayon_server.api.readiness import is_ready
from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.helpers.replicas import ReplicaInfo, ServerReplicas
from ayon_server.info import BOOT_TIME, get_version
from ayon_server.logging import log_traceback

HEARTBEAT_INTERVAL = 10
# A replica that missed ~3 heartbeats is considered gone
HEARTBEAT_TTL = 30


class ReplicaHeartbeat(BackgroundWorker):
    """Periodically announce this server replica in Redis.

    Each replica writes its own key with a TTL, so replicas that die
    without a clean shutdown simply expire. See ServerReplicas for reading.
    """

    def initialize(self):
        self.replica_id = uuid.uuid1().hex

    def get_info(self) -> ReplicaInfo:
        addons: dict[str, list[str]] = {}
        # Accessing definition.versions before startup finishes would
        # trigger addon initialization from here, so only list them once ready
        if ready := is_ready():
            for name, definition in AddonLibrary.items():
                addons[name] = list(definition.versions)
        return ReplicaInfo(
            id=self.replica_id,
            hostname=socket.gethostname(),
            version=get_version(),
            boot_time=BOOT_TIME,
            ready=ready,
            addons=addons,
        )

    async def run(self):
        while True:
            try:
                await ServerReplicas.save(self.get_info(), ttl=HEARTBEAT_TTL)
            except Exception:
                log_traceback("Replica heartbeat failed")
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def finalize(self):
        # finalize also runs before a restart after a crash, keep the key then
        if not self.shutting_down:
            return
        try:
            await ServerReplicas.delete(self.replica_id)
        except Exception:
            pass


replica_heartbeat = ReplicaHeartbeat()
