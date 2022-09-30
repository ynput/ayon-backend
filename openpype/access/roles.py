from typing import Any

from nxtools import logging

from openpype.access.permissions import BasePermissionsModel, FolderAccess, Permissions
from openpype.lib.postgres import Postgres


def normalize_to_dict(s: Any):
    if type(s) is dict:
        return s
    return s.dict()


class Roles:
    roles: dict[tuple[str, str], Permissions] = {}

    @classmethod
    async def load(cls) -> None:
        cls.roles = {}
        async for row in Postgres.iterate("SELECT name, data FROM public.roles"):
            cls.add_role(
                row["name"],
                "_",
                Permissions.from_record(row["data"]),
            )
        project_list: list[str] = [
            row["name"] async for row in Postgres.iterate("SELECT name FROM projects")
        ]

        for project_name in project_list:
            async for row in Postgres.iterate(
                f"SELECT name, data FROM project_{project_name}.roles"
            ):
                cls.add_role(
                    row["name"],
                    project_name,
                    Permissions.from_record(row["data"]),
                )

    @classmethod
    def add_role(cls, name: str, project_name: str, permissions: Permissions) -> None:
        logging.debug("Adding role", name)
        cls.roles[(name, project_name)] = permissions

    @classmethod
    def combine(cls, role_names: list[str], project_name: str = "_") -> Permissions:
        """Create aggregated permissions object for a given list of roles.

        If a project name is specified and there is a project-level override
        for a given role, it will be used. Ohterwise a "_" (default) role will
        be used.
        """

        result: Permissions | None = None

        for role_name in role_names:
            if (role_name, project_name) in cls.roles:
                role = cls.roles[(role_name, project_name)]
            elif (role_name, "_") in cls.roles:
                role = cls.roles[(role_name, "_")]
            else:
                continue

            if result is None:
                result = role.dict()
                continue

            for perm_name, value in role:
                if isinstance(value, BasePermissionsModel):
                    if not value.enabled:
                        result[perm_name] = {"enabled": False}
                        continue
                    elif not result[perm_name]["enabled"]:
                        continue

                if perm_name in ("create", "read", "update", "delete"):
                    # TODO: deduplicate
                    result[perm_name]["access_list"] = list(
                        set(
                            FolderAccess(**normalize_to_dict(r))
                            for r in result[perm_name].get("access_list", [])
                        )
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

        assert result is not None
        return Permissions(**result)
