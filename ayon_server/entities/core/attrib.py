import asyncio
import collections
import functools
import threading
from typing import Any, Callable

from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger


class AttributeLibrary:
    """Dynamic attributes loader class.

    This is very wrong and i deserve a punishment for this,
    but it works. Somehow. It needs to be initialized when
    this module is loaded and it has to load the attributes
    from the database in blocking mode regardless the running
    event loop. So it connects to the DB independently in a
    different thread and waits until it is finished.

    Attribute list for each entity type may be then accessed
    using __getitem__ method.
    """

    def __init__(self) -> None:
        self.data: collections.defaultdict[str, Any] = collections.defaultdict(list)

        # Used in info endpoint to get the active list of attributes
        # in the same format as the attributes endpoint
        self.info_data: list[Any] = []

        self._invalidation_callbacks: list[Callable[[], None]] = []

        # We need to load attribute data in a separate thread
        # with a separate event loop, because the main event loop
        # is already running and we cannot run another one
        # that brings some caveats, but it works
        _thread = threading.Thread(target=self.initial_load_thread)
        _thread.start()
        _thread.join()

    def initial_load_thread(self) -> None:
        if Postgres.pool is not None:
            with logger.contextualize(nodb=True):
                logger.error(
                    "Postgres pool exist during attribute load. This should not happen."
                )
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.load(True))
        loop.close()

    def is_valid(self, entity_type: str, attribute: str) -> bool:
        """Check if attribute is valid for entity type."""
        return attribute in [k["name"] for k in self.data[entity_type]]

    async def load(self, initial: bool = False) -> None:
        query = "SELECT * FROM public.attributes ORDER BY position"

        # Initial load is executed in a separate thread, so we need to
        # connect to the database manually and close the connection
        # after the data is loaded
        if initial:
            await Postgres.connect()

        info_data: list[dict[str, Any]] = []
        try:
            result = await Postgres.fetch(query)
        except Postgres.UndefinedTableError:
            # A default list of fake attributes is used when the
            # attributes table does not exist. This is used when the
            # database is not initialized yet.
            result = [
                {
                    "name": "default",
                    "scope": [
                        "project",
                        "folder",
                        "task",
                        "product",
                        "version",
                        "representation",
                        "workfile",
                        "user",
                    ],
                    "position": 1,
                    "builtin": True,
                    "data": {
                        "type": "string",
                        "title": "DEFAULT",
                        "inherit": False,
                    },
                }
            ]

        for row in result:
            info_data.append(row)
            for scope in row["scope"]:
                attrd = {"name": row["name"], **row["data"]}
                # Only project attributes should have defaults.
                # All the others are nullable and should inherit from
                # their parent entities
                if (scope != "project") and ("default" in attrd):
                    del attrd["default"]
                self.data[scope].append(attrd)
        self.info_data = info_data

        if initial:
            await Postgres.shutdown()
            Postgres.pool = None
            Postgres.shutting_down = False

    def __getitem__(self, key) -> list[dict[str, Any]]:
        return self.data[key]

    @property
    def project_defaults(self) -> dict[str, Any]:
        project_attribs = self.data.get("project", [])
        defaults = {}
        for attr in project_attribs:
            if "default" in attr:
                defaults[attr["name"]] = attr["default"]
        return defaults

    @functools.cache
    def inheritable_attributes(self) -> list[str]:
        result = set()
        for entity_type in self.data:
            for attr in self.data[entity_type]:
                if attr.get("inherit", True):
                    result.add(attr["name"])
        return list(result)

    @functools.cache
    def by_name(self, name: str) -> dict[str, Any]:
        """Return attribute definition by name."""
        for entity_type in self.data:
            for attr in self.data[entity_type]:
                if attr["name"] == name:
                    return attr
        raise KeyError(f"Attribute {name} not found")

    @functools.cache
    def by_name_scoped(self, entity_type: str, name: str) -> dict[str, Any]:
        """Return attribute definition by name for a specific entity type."""
        for attr in self.data[entity_type]:
            if attr["name"] == name:
                return attr
        raise KeyError(f"Attribute {name} not found for entity type {entity_type}")

    def register_invalidation_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when attributes are reloaded."""
        self._invalidation_callbacks.append(callback)

    async def reload(self) -> None:
        """Reload attributes from the database and invalidate all cached models.

        Fetches fresh data from the database, updates the in-memory attribute
        lists in-place (preserving list object identity so ModelSet.attributes
        references remain valid), and invalidates all cached Pydantic models
        so they are regenerated on next access.
        """
        query = "SELECT * FROM public.attributes ORDER BY position"
        result = await Postgres.fetch(query)

        # Build new data in a temporary structure first to minimize
        # the window of inconsistency
        new_data: collections.defaultdict[str, list[Any]] = collections.defaultdict(list)
        new_info_data: list[Any] = []

        for row in result:
            new_info_data.append(row)
            for scope in row["scope"]:
                attrd = {"name": row["name"], **row["data"]}
                if (scope != "project") and ("default" in attrd):
                    del attrd["default"]
                new_data[scope].append(attrd)

        # Update self.data in-place to preserve list object identity.
        # ModelSet instances hold direct references to these list objects,
        # so we must mutate them rather than replace them.
        all_scopes = set(self.data.keys()) | set(new_data.keys())
        for scope in all_scopes:
            self.data[scope].clear()
            self.data[scope].extend(new_data.get(scope, []))

        self.info_data = new_info_data

        # Clear functools caches since the underlying data has changed
        AttributeLibrary.inheritable_attributes.cache_clear()
        AttributeLibrary.by_name.cache_clear()
        AttributeLibrary.by_name_scoped.cache_clear()

        # Invalidate all registered ModelSet Pydantic model caches
        for callback in self._invalidation_callbacks:
            callback()

        logger.info("Attribute library reloaded")

    async def reload_handler(self, event: Any = None) -> None:
        """Event handler adapter for reload(), for use with EventStream.subscribe."""
        await self.reload()


attribute_library = AttributeLibrary()
