from typing import Type

from fastapi import Depends
from pydantic import Field

from openpype.addons import BaseServerAddon
from openpype.api.dependencies import dep_project_name
from openpype.entities import FolderEntity
from openpype.exceptions import NotFoundException
from openpype.lib.postgres import Postgres
from openpype.settings import BaseSettingsModel

# from openpype.api.dependencies import dep_current_user


class TestSettings(BaseSettingsModel):
    """Test addon settings"""

    folder_type: str = Field("Asset", title="Folder type")


class AddOn(BaseServerAddon):
    version = "1.0.0"
    settings: Type[TestSettings] = TestSettings
    frontend_scopes = ["project"]

    def setup(self):
        self.add_endpoint(
            "get-random-asset/{project_name}",
            self.get_random_asset,
            method="GET",
        )

    async def get_random_asset(
        self,
        # Uncomment this to disallow anonymous access
        # user: UserEntity = Depends(dep_current_user),
        project_name: str = Depends(dep_project_name),
    ):
        """Return a random asset from the database"""

        settings = await self.get_project_settings(project_name)
        assert settings is not None  # Keep mypy happy

        #
        # Get a random asset id from the project
        #

        try:
            result = await Postgres.fetch(
                f"""
                SELECT id FROM project_{project_name}.folders
                WHERE folder_type = $1
                ORDER BY RANDOM() LIMIT 1
                """,
                settings.folder_type,
            )
        except Postgres.UndefinedTableError:
            raise NotFoundException(f"Project {project_name} not found")

        try:
            folder_id = result[0]["id"]
        except IndexError:
            raise NotFoundException("No assets found")

        #
        # Load the asset and return it
        #

        folder = await FolderEntity.load(project_name, folder_id)
        return folder.payload

        # Optionally you can use:
        #
        # folder.ensure_read_access(user)
        # return folder.as_user(user)
