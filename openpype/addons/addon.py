import os

try:
    import toml
except ModuleNotFoundError:
    toml = None  # type: ignore

from typing import TYPE_CHECKING, Any, Callable, Literal, Type

from nxtools import logging

from openpype.exceptions import AyonException, NotFoundException
from openpype.lib.postgres import Postgres
from openpype.settings import BaseSettingsModel, apply_overrides

if TYPE_CHECKING:
    from openpype.addons.definition import ServerAddonDefinition


class BaseServerAddon:
    name: str
    version: str
    title: str | None = None
    addon_type: Literal["module", "host"] = "module"
    definition: "ServerAddonDefinition"
    endpoints: list[dict[str, Any]]
    settings_model: Type[BaseSettingsModel] | None = None
    frontend_scopes: dict[str, Any] = {}
    services: dict[str, Any] = {}

    def __init__(self, definition: "ServerAddonDefinition", addon_dir: str):
        assert self.name and self.version
        self.definition = definition
        self.addon_dir = addon_dir
        self.endpoints = []
        self.restart_requested = False
        logging.info(f"Initializing addon {self.name} v{self.version} in {addon_dir}")
        self.initialize()

    def __repr__(self) -> str:
        return f"<Addon name='{self.definition.name}' version='{self.version}'>"

    @property
    def friendly_name(self) -> str:
        """Return the friendly name of the addon."""
        return f"{self.definition.friendly_name} {self.version}"

    def initialize(self) -> None:
        """Initialize the addon.

        This metod is started during the addon initialization
        and it is here just for the convinience (override this
        instead using super().__init__).

        Add `add_endpoint` calls here. This method cannot be async.
        """
        pass

    def setup(self) -> None:
        """Setup the addon.

        This method is called when all addons are initialized.
        Add code which needs to access other addons here.

        This method may be async if needed (for example when)
        it needs to access the database.
        """
        return None

    def request_server_restart(self):
        """Request the server to restart.

        call this method from initialize or setup to request server restart.
        For example when you change the server configuration. If called from
        initialize the server will restart after all addons are initialized.
        If called from setup the server will restart after all addons are
        setup.
        """
        self.restart_requested = True

    def add_endpoint(
        self,
        path: str,
        handler: Callable,
        *,
        method: str = "GET",
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        """Add a REST endpoint to the server."""

        self.endpoints.append(
            {
                "name": name or handler.__name__,
                "path": path,
                "handler": handler,
                "method": method,
                "description": description or handler.__doc__ or "",
            }
        )

    #
    # File serving
    #
    # Each addon supports serving files from the following directories:
    #  - frontend (html/javascript frontend code with index.html)
    #  - private (files which require authentication header to download)
    #  - public (files available for unauthenticated download)
    #

    def get_frontend_dir(self) -> str | None:
        """Return the addon frontend directory."""
        res = os.path.join(self.addon_dir, "frontend/dist")
        if os.path.isdir(res):
            return res
        return None  # just to make mypy happy

    def get_private_dir(self) -> str | None:
        """Return the addon private directory."""
        res = os.path.join(self.addon_dir, "private")
        if os.path.isdir(res):
            return res
        return None

    def get_public_dir(self) -> str | None:
        """Return the addon private directory."""
        res = os.path.join(self.addon_dir, "public")
        if os.path.isdir(res):
            return res
        return None

    #
    # Client code
    #

    def get_local_client_info(
        self,
        base_url: str | None = None,
    ) -> dict[str, Any] | None:
        """Returns information on local copy of the client code."""
        if (pdir := self.get_private_dir()) is None:
            return None
        if base_url is None:
            base_url = ""
        local_path = os.path.join(pdir, "client.zip")
        if not os.path.exists(local_path):
            return None
        return {
            "type": "http",
            "path": f"{base_url}/addons/{self.name}/{self.version}/private/client.zip",
        }

    async def get_client_source_info(
        self,
        base_url: str | None = None,
    ) -> list[dict[str, Any]] | None:
        """Return a list of locations from where the client part of
        the addon can be downloaded.
        """

        if (local := self.get_local_client_info(base_url)) is None:
            return None
        return [local]

    async def get_client_pyproject(self) -> dict[str, Any] | None:
        if (pdir := self.get_private_dir()) is None:
            return None
        pyproject_path = os.path.join(pdir, "pyproject.toml")
        if not os.path.exists(pyproject_path):
            return None
        if toml is None:
            return {"error": "Toml is not installed (but pyproject exists)"}
        try:
            return toml.load(open(pyproject_path))
        except Exception:
            raise AyonException("Unable to parse pyproject.toml")

    #
    # Settings
    #

    def get_settings_model(self) -> Type[BaseSettingsModel] | None:
        return self.settings_model

    async def get_studio_overrides(self, snapshot: int | None = None) -> dict[str, Any]:
        """Load the studio overrides from the database."""

        if snapshot is None:
            query = (
                """
                SELECT data FROM settings
                WHERE addon_name = $1 AND addon_version = $2
                ORDER BY snapshot_time DESC LIMIT 1
                """,
                self.definition.name,
                self.version,
            )
        else:
            query = (
                """
                SELECT data FROM settings
                WHERE addon_name = $1 AND addon_version = $2 AND snapshot_time = $3
                """,
                self.definition.name,
                self.version,
                snapshot,
            )
        res = await Postgres.fetch(*query)
        if res:
            return dict(res[0]["data"])
        return {}

    async def get_project_overrides(
        self,
        project_name: str,
        snapshot: int | None = None,
    ) -> dict[str, Any]:
        """Load the project overrides from the database."""

        if snapshot is None:
            query = (
                f"""
                SELECT data FROM project_{project_name}.settings
                WHERE addon_name = $1 AND addon_version = $2 AND project_name = $3
                ORDER BY snapshot_time DESC LIMIT 1
                """,
                self.definition.name,
                self.version,
                project_name,
            )
        else:
            query = (
                f"""
                SELECT data FROM project_{project_name}.settings
                WHERE addon_name = $1 AND addon_version = $2 AND snapshot_time = $3
                """,
                self.definition.name,
                self.version,
                snapshot,
            )

        try:
            res = await Postgres.fetch(*query)
        except Postgres.UndefinedTableError:
            raise NotFoundException(f"Project {project_name} does not exists")
        if res:
            return dict(res[0]["data"])
        return {}

    async def get_studio_settings(
        self,
        snapshot: int | None = None,
    ) -> BaseSettingsModel | None:
        """Return the addon settings with the studio overrides.

        You shouldn't override this method, unless absolutely necessary.
        """

        settings = await self.get_default_settings()
        if settings is None:
            return None  # this addon has no settings at all
        overrides = await self.get_studio_overrides(snapshot=snapshot)
        if overrides:
            settings = apply_overrides(settings, overrides)

        return settings

    async def get_project_settings(
        self,
        project_name: str,
        snapshot: int | None = None,
    ) -> BaseSettingsModel | None:
        """Return the addon settings with the studio and project overrides.

        You shouldn't override this method, unless absolutely necessary.
        """

        settings = await self.get_studio_settings()
        if settings is None:
            return None  # this addon has no settings at all
        studio_overrides = await self.get_studio_overrides(snapshot=snapshot)
        if studio_overrides:
            settings = apply_overrides(settings, studio_overrides)
        project_overrides = await self.get_project_overrides(
            project_name, snapshot=snapshot
        )
        if project_overrides:
            settings = apply_overrides(settings, project_overrides)
        return settings

    #
    # Overridable settings-related methods
    #

    async def get_default_settings(self) -> BaseSettingsModel | None:
        """Get the default addon settings.

        Override this method to return the default settings for the addon.
        By default it returns defaults from the addon's settings model, but
        if you need to use a complex model or force required fields, you should
        do something like: `return self.get_settings_model(**YOUR_ADDON_DEFAULTS)`.
        """

        if (model := self.get_settings_model()) is None:
            return None
        return model()

    def convert_system_overrides(
        self,
        source_version: str,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert system overrides from a previous version."""
        return overrides

    def convert_project_overrides(
        self,
        from_version: str,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert project overrides from a previous version."""
        return overrides
