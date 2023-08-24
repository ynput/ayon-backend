from typing import Any

from nxtools import logging

from ayon_server.access.permissions import (
    BasePermissionsModel,
    FolderAccess,
    Permissions,
)
from ayon_server.lib.postgres import Postgres


def normalize_to_dict(s: Any):
    if type(s) is dict:
        return s
    return s.dict()


class AccessGroups:
    access_groups: dict[tuple[str, str], Permissions] = {}

    @classmethod
    async def load(cls) -> None:
        cls.access_groups = {}
        async for row in Postgres.iterate(
            "SELECT name, data FROM public.access_groups"
        ):
            cls.add_access_group(
                row["name"],
                "_",
                Permissions.from_record(row["data"]),
            )
        project_list: list[str] = [
            row["name"] async for row in Postgres.iterate("SELECT name FROM projects")
        ]

        for project_name in project_list:
            async for row in Postgres.iterate(
                f"SELECT name, data FROM project_{project_name}.access_groups"
            ):
                cls.add_access_group(
                    row["name"],
                    project_name,
                    Permissions.from_record(row["data"]),
                )

    @classmethod
    def add_access_group(
        cls, name: str, project_name: str, permissions: Permissions
    ) -> None:
        logging.debug("Adding access_group", name)
        cls.access_groups[(name, project_name)] = permissions

    @classmethod
    def combine(
        cls, access_group_names: list[str], project_name: str = "_"
    ) -> Permissions:
        """Create aggregated permissions object for a given list of access_groups.

        If a project name is specified and there is a project-level override
        for a given access group, it will be used. Ohterwise a "_" (default) access group will
        be used.
        """

        result: Permissions | None = None

        for access_group_name in access_group_names:
            if (access_group_name, project_name) in cls.access_groups:
                access_group = cls.access_groups[(access_group_name, project_name)]
            elif (access_group_name, "_") in cls.access_groups:
                access_group = cls.access_groups[(access_group_name, "_")]
            else:
                continue

            if result is None:
                result = access_group.dict()
                continue

            for perm_name, value in access_group:
                if isinstance(value, BasePermissionsModel):
                    if not value.enabled:
                        result[perm_name] = {"enabled": False}
                        continue
                    elif not result[perm_name]["enabled"]:
                        continue

                if perm_name in ("create", "read", "update", "delete"):
                    # TODO: deduplicate
                    result[perm_name]["access_list"] = list(
                        {
                            FolderAccess(**normalize_to_dict(r))
                            for r in result[perm_name].get("access_list", [])
                        }
                        | set(value.access_list)
                    )

                elif perm_name in ("attrib_read", "attrib_write"):
                    result[perm_name]["attributes"] = list(
                        set(result[perm_name].get("attributes", []))
                        | set(value.attributes)
                    )
                elif perm_name == "endpoints":
                    result[perm_name]["endpoints"] = list(
                        set(result[perm_name].get("endpoints", []))
                        | set(value.endpoints)
                    )

        if not result:
            return Permissions()
        return Permissions(**result)
