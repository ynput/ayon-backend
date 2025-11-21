from datetime import datetime
from typing import Any

from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.exceptions import (
    AyonException,
    ForbiddenException,
)
from ayon_server.helpers.hierarchy_cache import rebuild_hierarchy_cache
from ayon_server.helpers.inherited_attributes import rebuild_inherited_attributes
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import ProjectLevelEntityType
from ayon_server.utils import SQLTool, dict_exclude

BASE_GET_QUERY = """
    WITH RECURSIVE folder_closure AS (
        SELECT id AS ancestor_id, id AS descendant_id
        FROM project_{project_name}.folders
        UNION ALL
        SELECT fc.ancestor_id, f.id AS descendant_id
        FROM folder_closure fc
        JOIN project_{project_name}.folders f
        ON f.parent_id = fc.descendant_id
    ),

    folder_with_versions AS (
        SELECT DISTINCT fc.ancestor_id
        FROM folder_closure fc
        JOIN project_{project_name}.products p ON p.folder_id = fc.descendant_id
        JOIN project_{project_name}.versions v ON v.product_id = p.id
    )

    SELECT
        entity.id as id,
        entity.name as name,
        entity.label as label,
        entity.folder_type as folder_type,
        entity.parent_id as parent_id,
        entity.thumbnail_id as thumbnail_id,
        entity.attrib as attrib,
        entity.data as data,
        entity.active as active,
        entity.created_at as created_at,
        entity.updated_at as updated_at,
        entity.created_by as created_by,
        entity.updated_by as updated_by,
        entity.status as status,
        entity.tags as tags,
        hierarchy.path as path,
        ia.attrib AS inherited_attrib,
        p.attrib AS project_attrib,
        (fwv.ancestor_id IS NOT NULL)::BOOLEAN AS has_versions

    FROM project_{project_name}.folders as entity

    INNER JOIN project_{project_name}.hierarchy as hierarchy
    ON entity.id = hierarchy.id

    LEFT JOIN project_{project_name}.exported_attributes as ia
    ON entity.parent_id = ia.folder_id

    LEFT JOIN folder_with_versions fwv
    ON fwv.ancestor_id = entity.id

    INNER JOIN public.projects as p
    ON p.name ILIKE '{project_name}'
"""


class FolderEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "folder"
    model: ModelSet = ModelSet("folder", attribute_library["folder"])
    base_get_query = BASE_GET_QUERY

    @staticmethod
    def preprocess_record(record: dict[str, Any]) -> dict[str, Any]:
        path = record.pop("path")
        if path is not None:
            # ensure path starts with / but does not end with /
            record["path"] = f"/{path.strip('/')}"
        attrib: dict[str, Any] = {}
        inherited_attrib: dict[str, Any] = {}

        for key, value in record.get("project_attrib", {}).items():
            if key in attribute_library.inheritable_attributes():
                attrib[key] = value
                inherited_attrib[key] = value

        if (ia := record["inherited_attrib"]) is not None:
            for key, value in ia.items():
                if key in attribute_library.inheritable_attributes():
                    attrib[key] = value
                    inherited_attrib[key] = value

        elif record["parent_id"] is not None:
            logger.warning(
                f"Folder {record['path']} does not have inherited attributes."
                "this shouldn't happen"
            )
        attrib.update(record["attrib"])
        return {**record, "attrib": attrib, "inherited_attrib": inherited_attrib}

    async def save(self, *args, auto_commit: bool = True, **kwargs) -> None:
        async with Postgres.transaction():
            if self.status is None:
                self.status = await self.get_default_status()

            if self.folder_type is None:
                res = await Postgres.fetch(
                    f"""
                    SELECT name from project_{self.project_name}.folder_types
                    ORDER BY position ASC LIMIT 1
                    """
                )
                if not res:
                    raise AyonException("No folder types defined")
                self.folder_type = res[0]["name"]

            attrib = {}
            for key in self.own_attrib:
                if not hasattr(self.attrib, key):
                    continue
                if (value := getattr(self.attrib, key)) is not None:
                    attrib[key] = value

            if self.exists:
                # Update existing entity

                await Postgres.execute(
                    *SQLTool.update(
                        f"project_{self.project_name}.{self.entity_type}s",
                        f"WHERE id = '{self.id}'",
                        name=self.name,
                        label=self.label,
                        folder_type=self.folder_type,
                        parent_id=self.parent_id,
                        thumbnail_id=self.thumbnail_id,
                        status=self.status,
                        tags=self.tags,
                        attrib=attrib,
                        data=self.data,
                        active=self.active,
                        updated_at=datetime.now(),
                        updated_by=kwargs.get("user_name"),
                    )
                )

            else:
                # Create a new entity
                await Postgres.execute(
                    *SQLTool.insert(
                        f"project_{self.project_name}.{self.entity_type}s",
                        created_by=kwargs.get("user_name"),
                        updated_by=kwargs.get("user_name"),
                        **dict_exclude(self.dict(exclude_none=True), ["own_attrib"]),
                    )
                )

            # This needs to run in save, not in refresh_views, because
            # we may need the hierarchy record in the same transaction
            await Postgres.execute(
                f"""
                REFRESH MATERIALIZED VIEW
                project_{self.project_name}.hierarchy
                """
            )

            if auto_commit:
                await self.commit()

    @classmethod
    async def refresh_views(cls, project_name: str) -> None:
        """Refresh hierarchy materialized view on folder save."""
        logger.trace(f"Refreshing folder views for project {project_name}")

        # Do not change the order of these calls!
        #
        # Inherited attributes call:
        #  - refreshes hierarchy materialized view
        #  - rebuilds exported_attributes table
        #
        # Hierarchy cache call:
        #  - caches the hierarchy table in Redis
        #  - which depends on the exported_attributes table

        await rebuild_inherited_attributes(project_name)
        await rebuild_hierarchy_cache(project_name)

    async def delete(self, *args, auto_commit: bool = True, **kwargs) -> bool:
        async with Postgres.transaction():
            if kwargs.get("force", False):
                logger.info(f"Force deleting folder and all its children: {self.path}")
                await Postgres.execute(
                    f"""
                    DELETE FROM project_{self.project_name}.products
                    WHERE folder_id IN (
                        SELECT id FROM project_{self.project_name}.hierarchy
                        WHERE path = $1
                        OR path LIKE $1 || '/%'
                    ) RETURNING name
                    """,
                    self.path.lstrip("/"),
                )

            res = await super().delete()
            if not res:
                return False
            elif auto_commit:
                await self.commit()
        return res

    async def get_versions(self) -> list[str]:
        """Return of version ids associated with this folder."""
        query = f"""
            SELECT v.id as version_id
            FROM project_{self.project_name}.versions as v
            INNER JOIN project_{self.project_name}.products as s
                ON s.id = v.product_id
            WHERE s.folder_id = $1
            """
        res = await Postgres.fetch(query, self.id)
        if not res:
            return []
        return [row["version_id"] for row in res]

    async def ensure_create_access(self, user, **kwargs) -> None:
        """Check if the user has access to create a new entity.

        Raises FobiddenException if the user does not have access.
        Reimplements the method from the parent class, because in
        case of folders we need to check the parent folder.
        """
        try:
            if self.parent_id is None:
                # if user can create a project, they can create a root folders
                user.check_permissions("studio.create_projects")
        except ForbiddenException:
            pass
        else:
            return

        await ensure_entity_access(
            user,
            self.project_name,
            self.entity_type,
            self.parent_id,
            "create",
        )

    async def ensure_update_access(self, user, **kwargs) -> None:
        """Check if the user has access to update the folder.

        Raises FobiddenException if the user does not have access.
        """

        if user.is_manager:
            return

        # if only thumbnail is updated, check publish access,
        # which is less restrictive than update access and it is
        # good enough for thumbnail updates
        if kwargs.get("thumbnail_only"):
            try:
                await ensure_entity_access(
                    user, self.project_name, self.entity_type, self.id, "publish"
                )
            except ForbiddenException:
                pass
            else:
                return

        await ensure_entity_access(
            user, self.project_name, self.entity_type, self.id, "update"
        )

    #
    # Helper methods
    #

    async def get_folder_descendant_ids(self) -> set[str]:
        query = f"""
            WITH RECURSIVE descendants AS (
                SELECT id, parent_id
                FROM project_{self.project_name}.folders
                WHERE parent_id = $1
                UNION
                SELECT f.id, f.parent_id
                FROM project_{self.project_name}.folders f
                INNER JOIN descendants d ON f.parent_id = d.id
            )
            SELECT id FROM descendants;
        """
        rows = await Postgres.fetch(query, self.id)
        return {row["id"] for row in rows}

    #
    # Properties
    #

    @property
    def label(self) -> str | None:
        """Return the label of the folder."""
        return self._payload.label  # type: ignore

    @label.setter
    def label(self, value):
        """Set the label of the folder."""
        self._payload.label = value  # type: ignore

    @property
    def parent_id(self) -> str | None:
        return self._payload.parent_id  # type: ignore

    @parent_id.setter
    def parent_id(self, value: str) -> None:
        self._payload.parent_id = value  # type: ignore

    @property
    def folder_type(self) -> str | None:
        return self._payload.folder_type  # type: ignore

    @folder_type.setter
    def folder_type(self, value: str) -> None:
        self._payload.folder_type = value  # type: ignore

    @property
    def thumbnail_id(self) -> str | None:
        return self._payload.thumbnail_id  # type: ignore

    @thumbnail_id.setter
    def thumbnail_id(self, value: str) -> None:
        self._payload.thumbnail_id = value  # type: ignore

    #
    # Read only properties
    #

    @property
    def path(self) -> str:
        return self._payload.path  # type: ignore

    @property
    def entity_subtype(self) -> str | None:
        return self.folder_type

    @property
    def has_versions(self) -> bool:
        """Check if the folder has any versions."""
        return self._payload.has_versions  # type: ignore
