from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres


async def get_roots_for_projects(
    user_name: str,
    site_id: str | None,
    projects: list[str],
    platform: str | None = None,
) -> dict[str, dict[str, str]]:
    # platform specific roots for each requested project
    # e.g. roots[project][root_name] = root_path

    if not (site_id or platform):
        raise BadRequestException(detail="Either site_id or platform must be provided")

    roots: dict[str, dict[str, str]] = {}

    if site_id:
        site_res = await Postgres.fetch(
            "SELECT data->>'platform' as platform FROM public.sites WHERE id = $1",
            site_id,
            timeout=5,
        )
        if site_res:
            platform = site_res[0]["platform"]
        elif not platform:
            raise BadRequestException(detail="Site not found and platform not provided")

    # get roots from project anatomies

    result = await Postgres.fetch(
        "SELECT name, config FROM public.projects WHERE name = ANY($1)",
        projects,
        timeout=5,
    )
    for row in result:
        _project_name = row["name"]
        _roots = row["config"].get("roots", {})
        roots[_project_name] = {}
        for _root_name, _root_paths in _roots.items():
            roots[_project_name][_root_name] = _root_paths[platform]

    # root project overrides

    if site_id:
        for project_name in projects:
            query = f"""
                SELECT data FROM project_{project_name}.custom_roots
                WHERE user_name = $1 AND site_id = $2
            """
            result = await Postgres.fetch(query, user_name, site_id, timeout=5)
            for row in result:
                roots[project_name].update({k: v for k, v in row["data"].items() if v})

    return roots
