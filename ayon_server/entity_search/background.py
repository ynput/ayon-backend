__all__ = ["entity_indexer"]

import asyncio
from collections import defaultdict

from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import log_traceback

from .indexer import ENTITY_TYPES, index_entities


class EntityIndexer(BackgroundWorker):
    """Keep `entity_search` up to date with the saved entities and comments.

    Saves only enqueue the id; the rows are indexed here in batches, so a bulk
    operation is not slowed down. The queue lives in memory: whatever is lost
    (a restart, a failure, a process without the workers such as the CLI)
    is picked up by the next sweep (`backfill`).
    """

    def initialize(self) -> None:
        self.queue: set[tuple[str, str, str]] = set()
        self.wakeup = asyncio.Event()

    async def enqueue(
        self, project_name: str, entity_type: str, entity_id: str
    ) -> None:
        """Index the entity after the current transaction commits.

        The indexer reads the committed row, so it must not run earlier.
        """
        if entity_type not in ENTITY_TYPES or not self.is_running:
            return

        async def add() -> None:
            self.queue.add((project_name, entity_type, entity_id))
            self.wakeup.set()

        await Postgres.on_commit(add)

    async def run(self) -> None:
        while True:
            await self.wakeup.wait()
            await asyncio.sleep(1)  # let a bulk operation finish, index it at once
            self.wakeup.clear()
            queue, self.queue = self.queue, set()

            groups: dict[tuple[str, str], list[str]] = defaultdict(list)
            for project_name, entity_type, entity_id in queue:
                groups[project_name, entity_type].append(entity_id)

            # Parents first: a moved product takes its versions along
            for key in sorted(groups, key=lambda k: ENTITY_TYPES.index(k[1])):
                try:
                    await index_entities(*key, groups[key])
                except Postgres.UndefinedTableError:
                    pass  # the project is deleted or has no search table yet
                except Exception:
                    log_traceback(f"Search indexing of {key[1]}s in {key[0]} failed")


entity_indexer = EntityIndexer()
