import asyncio
import collections
import hashlib
import inspect
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ayon_server.lib.postgres import Postgres
from ayon_server.logging import log_traceback, logger
from ayon_server.utils import json_dumps

ReloadCallback = Callable[[], None] | Callable[[], Awaitable[None]]

# Entity types, which inherit attributes (from the parent folders and the project)
INHERITING_ENTITY_TYPES = frozenset({"folder", "task"})


def _fingerprint(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json_dumps(rows).encode()).hexdigest()


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
    Each (re)load replaces the data at once and increments `revision`.
    Data derived from the attributes is kept up to date in one of two ways:

    - Objects derived on demand (such as the attribute models) store
      the `revision` they were built for and are rebuilt when it changes.
    - Caches the library cannot see into (such as aiocache caches or
      schema caches of other models) register a callback using `on_reload`,
      which is executed after a reload.
    """

    def __init__(self) -> None:
        self.data: collections.defaultdict[str, Any] = collections.defaultdict(list)

        # Used in info endpoint to get the active list of attributes
        # in the same format as the attributes endpoint
        self.info_data: list[Any] = []

        # Incremented every time the attributes are (re)loaded
        self.revision: int = 0

        self._fingerprint: str | None = None
        self._inheritable: frozenset[str] = frozenset()
        self._project_defaults: dict[str, Any] = {}
        self._inherited_defaults: dict[str, Any] = {}
        self._by_name: dict[str, dict[str, Any]] = {}
        # {entity type: {attribute name: definition}}
        self._scoped: dict[str, dict[str, dict[str, Any]]] = {}
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
        return attribute in self._scoped.get(entity_type, {})

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

    def _apply(
        self,
        rows: list[dict[str, Any]],
        fingerprint: str | None = None,
    ) -> None:
        """Replace the attribute data with the given database rows.

        All the data is built first and then swapped at once,
        so readers never see a partially loaded library.
        """
        data: collections.defaultdict[str, Any] = collections.defaultdict(list)
        inheritable: set[str] = set()
        by_name: dict[str, dict[str, Any]] = {}
        scoped: dict[str, dict[str, dict[str, Any]]] = {}

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
            scoped[entity_type] = {}
            for attr in attributes:
                if attr.get("inherit", True):
                    inheritable.add(attr["name"])
                by_name.setdefault(attr["name"], attr)
                scoped[entity_type][attr["name"]] = attr

        project_defaults = {
            attr["name"]: attr["default"]
            for attr in data.get("project", [])
            if attr.get("default") is not None
        }

        self.data = data
        self.info_data = rows
        self._inheritable = frozenset(inheritable)
        self._project_defaults = project_defaults
        self._inherited_defaults = {
            name: value
            for name, value in project_defaults.items()
            if name in inheritable
        }
        self._by_name = by_name
        self._scoped = scoped
        self._fingerprint = fingerprint or _fingerprint(rows)
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

    async def reload(self) -> set[str]:
        """Reload the attributes from the database.

        Returns names of the attributes, whose definitions changed
        (in any scope). Nothing happens when the attributes are the same
        as the loaded ones - so it is cheap to call this repeatedly
        (e.g. once locally and once from the event handler).
        """
        if self._reload_lock is None:
            self._reload_lock = asyncio.Lock()

        async with self._reload_lock:
            rows = await self._fetch()
            fingerprint = _fingerprint(rows)
            if fingerprint == self._fingerprint:
                return set()

            before = self._scoped
            self._apply(rows, fingerprint)
            changed = {
                name
                for entity_type in before.keys() | self._scoped.keys()
                for name, attr in self._scoped.get(entity_type, {}).items()
                if before.get(entity_type, {}).get(name) != attr
            }
            logger.info(f"Attribute library reloaded (revision {self.revision})")

            for callback in self._reload_callbacks:
                try:
                    result = callback()
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    log_traceback(f"Attribute reload callback {callback} failed")
        return changed

    #
    # Accessors
    #

    def __getitem__(self, key) -> list[dict[str, Any]]:
        return self.data[key]

    @property
    def project_defaults(self) -> dict[str, Any]:
        """Default values of the project attributes (a copy)."""
        return dict(self._project_defaults)

    @property
    def inheritable(self) -> frozenset[str]:
        """Names of the inheritable attributes."""
        return self._inheritable

    def by_name(self, name: str) -> dict[str, Any]:
        """Return attribute definition by name."""
        try:
            return self._by_name[name]
        except KeyError:
            raise KeyError(f"Attribute {name} not found") from None

    def by_name_scoped(self, entity_type: str, name: str) -> dict[str, Any]:
        """Return attribute definition by name for a specific entity type."""
        try:
            return self._scoped[entity_type][name]
        except KeyError:
            raise KeyError(
                f"Attribute {name} not found for entity type {entity_type}"
            ) from None


attribute_library = AttributeLibrary()


@dataclass
class ResolvedAttrib:
    #: Attribute values of the entity (own values over the inherited ones)
    values: dict[str, Any]
    #: Names of the attributes set on the entity itself
    own: list[str]
    #: Values inherited from the parents, the project and the defaults
    #: (also for the attributes set on the entity itself)
    inherited: dict[str, Any]


def resolve_attrib(
    entity_type: str,
    own: dict[str, Any] | None,
    *,
    inherited: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
) -> ResolvedAttrib:
    """Resolve the attribute values of an entity from the stored values.

    Used by both REST (entities) and GraphQL, so they return the same values.

    Folders and tasks inherit attributes. Each inheritable attribute
    has the first value set in the following order:

    1. own value of the entity
    2. value inherited from the parent folders (`inherited`,
       the exported attributes of the parent)
    3. project value (`project`)
    4. default value of the project attribute

    Projects have their own values and the defaults. Other entity types
    have only their own values (only project attributes have defaults).

    Stored values are not validated (they were, when they were written).
    None values and attributes without a definition are ignored.
    """
    lib = attribute_library
    defined = lib._scoped.get(entity_type)
    if defined is None:  # unknown entity type
        own_values = {k: v for k, v in (own or {}).items() if v is not None}
        return ResolvedAttrib(values=own_values, own=list(own_values), inherited={})

    own_values = {
        name: value
        for name, value in (own or {}).items()
        if value is not None and name in defined
    }

    if entity_type not in INHERITING_ENTITY_TYPES:
        defaults = lib._project_defaults if entity_type == "project" else {}
        return ResolvedAttrib(
            values={**defaults, **own_values},
            own=list(own_values),
            inherited={},
        )

    inherited_values: dict[str, Any] = {}
    for layer in (lib._inherited_defaults, project, inherited):
        if layer:
            inherited_values.update(
                {
                    name: value
                    for name, value in layer.items()
                    if value is not None
                    and name in lib._inheritable
                    and name in defined
                }
            )

    return ResolvedAttrib(
        values={**inherited_values, **own_values},
        own=list(own_values),
        inherited=inherited_values,
    )
