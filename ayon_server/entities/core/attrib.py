import asyncio
import collections
import hashlib
import inspect
import threading
from collections.abc import Awaitable, Callable
from typing import Any

from ayon_server.lib.postgres import Postgres
from ayon_server.logging import log_traceback, logger
from ayon_server.utils import json_dumps

ReloadCallback = Callable[[], None] | Callable[[], Awaitable[None]]


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

    Attributes may be reloaded at runtime using `reload` method.
    Each (re)load replaces the data at once and increments `revision`,
    so consumers may cache derived data (such as pydantic models)
    and regenerate them when the revision changes. Additionally,
    callbacks registered using `on_reload` are executed after a reload.
    """

    def __init__(self) -> None:
        self.data: collections.defaultdict[str, Any] = collections.defaultdict(list)

        # Used in info endpoint to get the active list of attributes
        # in the same format as the attributes endpoint
        self.info_data: list[Any] = []

        # Incremented every time the attributes are (re)loaded
        self.revision: int = 0

        self._fingerprint: str | None = None
        self._inheritable: list[str] = []
        self._inheritable_set: frozenset[str] = frozenset()
        self._by_name: dict[str, dict[str, Any]] = {}
        self._by_name_scoped: dict[tuple[str, str], dict[str, Any]] = {}
        self._reload_callbacks: list[ReloadCallback] = []
        self._reload_lock: asyncio.Lock | None = None

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
        return (entity_type, attribute) in self._by_name_scoped

    async def _fetch(self) -> list[dict[str, Any]]:
        query = "SELECT * FROM public.attributes ORDER BY position"
        return [dict(row) for row in await Postgres.fetch(query)]

    async def load(self, initial: bool = False) -> None:
        # Initial load is executed in a separate thread, so we need to
        # connect to the database manually and close the connection
        # after the data is loaded
        if initial:
            await Postgres.connect()

        try:
            result = await self._fetch()
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

        self._apply(result)

        if initial:
            await Postgres.shutdown()
            Postgres.pool = None
            Postgres.shutting_down = False

    def _apply(self, rows: list[dict[str, Any]]) -> None:
        """Replace the attribute data with the given database rows.

        All the data is built first and then swapped at once,
        so readers never see a partially loaded library.
        """
        data: collections.defaultdict[str, Any] = collections.defaultdict(list)
        inheritable: set[str] = set()
        by_name: dict[str, dict[str, Any]] = {}
        by_name_scoped: dict[tuple[str, str], dict[str, Any]] = {}

        for row in rows:
            for scope in row["scope"]:
                attrd = {"name": row["name"], **row["data"]}
                # Only project attributes should have defaults.
                # All the others are nullable and should inherit from
                # their parent entities
                if (scope != "project") and ("default" in attrd):
                    del attrd["default"]
                data[scope].append(attrd)

        for entity_type, attributes in data.items():
            for attr in attributes:
                if attr.get("inherit", True):
                    inheritable.add(attr["name"])
                by_name.setdefault(attr["name"], attr)
                by_name_scoped[(entity_type, attr["name"])] = attr

        self.data = data
        self.info_data = rows
        self._inheritable = list(inheritable)
        self._inheritable_set = frozenset(inheritable)
        self._by_name = by_name
        self._by_name_scoped = by_name_scoped
        self._fingerprint = hashlib.sha256(json_dumps(rows).encode()).hexdigest()
        self.revision += 1

    #
    # Runtime reload
    #

    def on_reload(self, callback: ReloadCallback) -> None:
        """Register a callback executed after the attributes are reloaded.

        Use it to invalidate caches derived from the attribute data.
        Callbacks may be sync or async and they are executed in the
        order of registration.
        """
        self._reload_callbacks.append(callback)

    async def reload(self, force: bool = False) -> bool:
        """Reload the attributes from the database.

        Returns True if the attributes changed (and were reloaded).
        Unless `force` is set, nothing happens when the attributes
        are the same as the loaded ones - so it is cheap to call this
        repeatedly (e.g. once locally and once from the event handler).
        """
        if self._reload_lock is None:
            self._reload_lock = asyncio.Lock()

        async with self._reload_lock:
            rows = await self._fetch()
            fingerprint = hashlib.sha256(json_dumps(rows).encode()).hexdigest()
            if fingerprint == self._fingerprint and not force:
                return False

            self._apply(rows)
            logger.info(f"Attribute library reloaded (revision {self.revision})")

            for callback in self._reload_callbacks:
                try:
                    result = callback()
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    log_traceback(f"Attribute reload callback {callback} failed")
        return True

    #
    # Accessors
    #

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

    def inheritable_attributes(self) -> list[str]:
        return self._inheritable

    @property
    def inheritable(self) -> frozenset[str]:
        """Names of the inheritable attributes."""
        return self._inheritable_set

    def by_name(self, name: str) -> dict[str, Any]:
        """Return attribute definition by name."""
        try:
            return self._by_name[name]
        except KeyError:
            raise KeyError(f"Attribute {name} not found") from None

    def by_name_scoped(self, entity_type: str, name: str) -> dict[str, Any]:
        """Return attribute definition by name for a specific entity type."""
        try:
            return self._by_name_scoped[(entity_type, name)]
        except KeyError:
            raise KeyError(
                f"Attribute {name} not found for entity type {entity_type}"
            ) from None


attribute_library = AttributeLibrary()
