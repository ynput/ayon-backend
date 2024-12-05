from ayon_server.lib.postgres import Postgres


async def folder_uris(project_name: str, ids: list[str]) -> list[tuple[str, str]]:
    query = f"""
        SELECT id, path FROM project_{project_name}.hierarchy
        WHERE id = ANY($1)
    """
    result = []
    async for row in Postgres.iterate(query, ids):
        id = row["id"].replace("-", "")
        path = row["path"]
        result.append((id, f"ayon+entity://{project_name}/{path}"))
    return result


async def task_uris(project_name: str, ids: list[str]) -> list[tuple[str, str]]:
    query = f"""
        SELECT t.id, t.name, h.path FROM
        project_{project_name}.tasks t
        JOIN project_{project_name}.hierarchy h ON h.id = t.folder_id
        WHERE t.id = ANY($1)
    """
    result = []
    async for row in Postgres.iterate(query, ids):
        id = row["id"].replace("-", "")
        path = row["path"]
        task_name = row["name"]
        result.append((id, f"ayon+entity://{project_name}/{path}?task={task_name}"))
    return result


async def workfile_uris(project_name: str, ids: list[str]) -> list[tuple[str, str]]:
    query = f"""
        SELECT w.id, w.path as wpath, h.path, t.name as task FROM
        project_{project_name}.workfiles w
        JOIN project_{project_name}.tasks t ON t.id = w.task_id
        JOIN project_{project_name}.hierarchy h ON h.id = t.folder_id
        WHERE w.id = ANY($1)
    """
    result = []
    async for row in Postgres.iterate(query, ids):
        id = row["id"].replace("-", "")
        path = row["path"]
        workfile_name = row["wpath"].split("/")[-1]
        task_name = row["task"]
        result.append(
            (
                id,
                f"ayon+entity://{project_name}/{path}?task={task_name}&workfile={workfile_name}",
            )
        )
    return result


async def product_uris(project_name: str, ids: list[str]) -> list[tuple[str, str]]:
    query = f"""
        SELECT p.id, p.name as name, h.path as path FROM
        project_{project_name}.products p
        JOIN project_{project_name}.hierarchy h ON h.id = p.folder_id
        WHERE p.id = ANY($1)
    """
    result = []
    async for row in Postgres.iterate(query, ids):
        id = row["id"].replace("-", "")
        path = row["path"]
        product_name = row["name"]
        result.append(
            (id, f"ayon+entity://{project_name}/{path}?product={product_name}")
        )
    return result


async def version_uris(project_name: str, ids: list[str]) -> list[tuple[str, str]]:
    query = f"""
        SELECT v.id, v.version, h.path, p.name as product FROM
        project_{project_name}.versions v
        JOIN project_{project_name}.products p ON p.id = v.product_id
        JOIN project_{project_name}.hierarchy h ON h.id = p.folder_id
        WHERE v.id = ANY($1)
    """
    result = []
    async for row in Postgres.iterate(query, ids):
        id = row["id"].replace("-", "")
        path = row["path"]
        version = row["version"]
        version_name = f"v{version:03d}"
        uri = f"ayon+entity://{project_name}/{path}?"
        uri += f"product={row['product']}&version={version_name}"
        result.append((id, uri))
    return result


async def representation_uris(
    project_name: str, ids: list[str]
) -> list[tuple[str, str]]:
    query = f"""
        SELECT r.id, r.name as repre, h.path, p.name as product, v.version FROM
        project_{project_name}.representations r
        JOIN project_{project_name}.versions v ON v.id = r.version_id
        JOIN project_{project_name}.products p ON p.id = v.product_id
        JOIN project_{project_name}.hierarchy h ON h.id = p.folder_id
        WHERE r.id = ANY($1)
    """
    result = []
    async for row in Postgres.iterate(query, ids):
        id = row["id"].replace("-", "")
        path = row["path"]
        version = row["version"]
        version_name = f"v{version:03d}"
        uri = f"ayon+entity://{project_name}/{path}"
        uri += f"?product={row['product']}"
        uri += f"&version={version_name}"
        uri += f"&representation={row['repre']}"
        result.append((id, uri))
    return result
