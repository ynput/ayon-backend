from typing import Any

from nxtools import logging

from openpype.access.permissions import Permissions
from openpype.lib.postgres import Postgres


class Roles:
    roles: dict[tuple[str, str], Permissions] = {}

    @classmethod
    async def load(cls):
        cls.roles = {}
        async for row in Postgres.iterate("SELECT * FROM public.roles"):
            cls.add_role(
                row["name"],
                row["project_name"],
                Permissions.from_record(row["data"]),
            )

    @classmethod
    def add_role(cls, name: str, project_name: str, permissions: Permissions):
        logging.debug("Adding role", name)
        cls.roles[(name, project_name)] = permissions

    @classmethod
    def combine(cls, role_names: list[str], project_name: str = "_") -> Permissions:
        """Create aggregated permissions object for a given list of roles.

        If a project name is specified and there is a project-level override
        for a given role, it will be used. Ohterwise a "_" (default) role will
        be used.
        """

        result: dict[str, Any] = {}

        for role_name in role_names:
            if (role_name, project_name) in cls.roles:
                role = cls.roles[(role_name, project_name)]
            elif (role_name, "_") in cls.roles:
                role = cls.roles[(role_name, "_")]
            else:
                continue

            for perm_name, value in role:
                # already have the highest possible setting
                if result.get(perm_name) is True:
                    continue
                elif result.get(perm_name) == "all":
                    continue

                # combine permissions
                if type(value) is bool:
                    result[perm_name] = result.get(perm_name, False) or value

                elif value == "all":
                    result[perm_name] = "all"

                elif type(value) == list:
                    # We already covered 'all' case, so we can
                    # safely assume that value from previously
                    # processed roles is list
                    vals = set(result.get(perm_name, []))
                    for v in value:
                        vals.add(v)
                    result[perm_name] = list(vals)

        return Permissions(**result)
