from typing import TYPE_CHECKING, Literal

from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import SQLTool

if TYPE_CHECKING:
    from ayon_server.access.permissions import FolderAccessList
    from ayon_server.entities import UserEntity
    from ayon_server.types import AccessType, ProjectLevelEntityType


def path_to_paths(
    path: str,
    include_parents: bool = False,
    include_self: bool = True,
) -> list[str]:
    """Convert a path to a list of paths

    If include_parents is True, the result will include all parent folders,
    if include_self is True, the result will include the path itself.

    The result is a list of strings, each string is a path WITHOUT a trailing slash,
    in order to be used directly in an SQL query.

    Bottom-level path conains a trailing wildcard, so it can be used in a LIKE query,
    and will match all subfolders.
    """
    path = path.strip().strip("/")
    pelms = path.split("/")
    result = [f'"{path}/%"']
    if include_parents:
        for i in range(len(pelms)):
            result.append(f"\"{'/'.join(pelms[0:i+1])}\"")
    if include_self:
        slf = "/".join(pelms)
        result.append(f'"{slf}"')
    return result


async def parse_permset(
    user: "UserEntity",
    project_name: str,
    access_type: "AccessType",
    permset: "FolderAccessList",
    no_parents: bool = False,
) -> list[str] | None:
    """Convert a permission set to a list of paths"""
    if not permset.enabled:
        return None

    # TODO: Enable caching when we figure out how to invalidate it
    # ns = "folder-access-list"
    # key = f"{project_name}:{user.name}:{access_type}"
    # if (cached := await Redis.get_json(ns, key)) is not None:
    #     return cached

    fpaths = set()
    for perm in permset.access_list:
        if perm.access_type == "hierarchy":
            assert perm.path is not None, "Path is required for hierarchy access"
            for path in path_to_paths(
                perm.path,
                # Read access implies reading parent folders
                include_parents=access_type == "read" and not no_parents,
            ):
                fpaths.add(path)

        elif perm.access_type == "children":
            assert perm.path is not None, "Path is required for children access"
            for path in path_to_paths(
                perm.path,
                include_parents=access_type == "read" and not no_parents,
                include_self=False,
            ):
                fpaths.add(path)

        elif perm.access_type == "assigned":
            query = f"""
                SELECT
                    h.path
                FROM
                    project_{project_name}.hierarchy as h
                INNER JOIN
                    project_{project_name}.tasks as t
                    ON h.id = t.folder_id
                WHERE
                    '{user.name}' = ANY (t.assignees)
                """
            async for record in Postgres.iterate(query):
                for path in path_to_paths(
                    record["path"],
                    include_parents=access_type == "read" and not no_parents,
                ):
                    fpaths.add(path)
    folder_list = list(fpaths)
    # logger.trace(
    #     f"Caching {user.name} {project_name} {access_type} "
    #     f"access: {', '.join(folder_list)}"
    # )
    # await Redis.set_json(ns, key, folder_list)
    return folder_list


async def folder_access_list(
    user: "UserEntity",
    project_name: str,
    access_type: "AccessType" = "read",
    no_parents: bool = False,
) -> list[str] | None:
    """Return a list of paths user has access to

    Result is either a list of strings or None,
    if there's no access limit, so if the result is not none,
    user has access to all folders in the list.

    Multiple access types can be specified, in which case
    the result is a union of all access types.

    Requires folowing columns to be selected:
        - hierarchy.path AS path

    Raises ForbiddenException in case it is obvious the user
    does not have rights to access any of the folders in the project.

    The list is returned as a list of strings WITHOUT leading slash,
    so it can be used directly in an SQL query.

    WARNING: The result uses SQL syntax and paths are enclosed in double quotes.
    % is used as a wildcard. If you need to check the folder access outside of SQL,
    use AccessChecker class.
    """

    if user.is_manager:
        return None

    if user.path_access_cache is None:
        user.path_access_cache = {}
    if (
        plist := user.path_access_cache.get(project_name, {}).get(access_type)
    ) is not None:
        if not plist:
            raise ForbiddenException(
                f"User {user.name} does not have access "
                f"to any folders in project {project_name}"
            )
        return plist

    perms = user.permissions(project_name)
    assert perms is not None, "folder_access_list without selected project"

    permset = perms.__getattribute__(access_type)

    path_list = await parse_permset(
        user,
        project_name,
        access_type,
        permset,
        no_parents=no_parents,
    )
    if path_list is None:
        return None

    # cache the result for the lifetime of the request
    if project_name not in user.path_access_cache:
        user.path_access_cache[project_name] = {}
    user.path_access_cache[project_name][access_type] = path_list

    if not path_list:
        raise ForbiddenException(
            f"{access_type.capitalize()} access denied "
            f"for {user.name} in project {project_name}"
        )

    return path_list


async def ensure_entity_access(
    user: "UserEntity",
    project_name: str,
    entity_type: "ProjectLevelEntityType",
    entity_id: str | None,
    access_type: "AccessType" = "read",
) -> Literal[True]:
    """Check whether the user has access to a given entity.

    Warning: THIS IS SLOW. DO NOT USE IN BATCHES!
    """

    access_list = await folder_access_list(
        user,
        project_name,
        access_type=access_type,
    )
    if access_list is None:
        return True

    if entity_id is None:
        raise ForbiddenException("Limited access to project")

    conditions = [f"hierarchy.path like ANY ('{{{', '.join(access_list)}}}')"]
    joins = []

    if entity_type in ("product", "version", "representation"):
        joins.append(
            f"""
            INNER JOIN project_{project_name}.products
            ON products.folder_id = hierarchy.id
            """
        )
        if entity_type in ("version", "representation"):
            joins.append(
                f"""
                INNER JOIN project_{project_name}.versions
                ON versions.product_id = products.id
                """
            )
            if entity_type == "representation":
                joins.append(
                    f"""
                    INNER JOIN project_{project_name}.representations
                    ON representations.version_id = versions.id
                    """
                )

    elif entity_type in ("task", "workfile"):
        joins.append(
            f"""
            INNER JOIN project_{project_name}.tasks
            ON tasks.folder_id = hierarchy.id
            """
        )

        if entity_type == "workfile":
            joins.append(
                f"""
                INNER JOIN project_{project_name}.workfiles
                ON workfiles.task_id = tasks.id
                """
            )

    if entity_type == "folder":
        conditions.append(f"hierarchy.id = '{entity_id}'")
    else:
        conditions.append(f"{entity_type}s.id = '{entity_id}'")

    query = f"""
        SELECT hierarchy.id FROM project_{project_name}.hierarchy
        {" ".join(joins)}
        {SQLTool.conditions(conditions)}
    """

    if await Postgres.fetchrow(query):
        return True

    raise ForbiddenException("Entity access denied")


class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_end = False

    def __repr__(self):
        return f"TrieNode(end={self.is_end}, children={list(self.children.keys())})"


class AccessChecker:
    """
    AccessChecker is used to determine if a user has access
    to specific paths within a project.

    This class builds a trie (prefix tree) structure to efficiently
    check if a given path is accessible based on the user's permissions.
    It also supports exact path matching and wildcard path matching.

    Usage:
        access_checker = AccessChecker()
        await access_checker.load(user, project_name, access_type)
        has_access = access_checker["some/path"]

    Attributes:
        root (TrieNode): The root node of the trie.
        exact_paths (set): A set of exact paths the user has access to.
        is_none (bool): A flag indicating if the user has unrestricted access.
    """

    def __init__(self):
        self.root = TrieNode()
        self.exact_paths = set()
        self.is_none = False

    def __getitem__(self, path: str) -> bool:
        """
        Check if the user has access to the given path.

        Args:
            path (str): The path to check access for.

        Returns:
            bool: True if the user has access, False otherwise.
        """
        if self.is_none:
            return True
        if path in self.exact_paths:
            return True
        return self.search(path)

    def search(self, path: str) -> bool:
        """
        Search the trie to determine if the path is accessible.

        Args:
            path (str): The path to search for in the trie.

        Returns:
            bool: True if the path is accessible, False otherwise.
        """
        node = self.root
        for char in path.split("/"):
            if char in node.children:
                node = node.children[char]
            else:
                return False
            if node.is_end:
                return True
        return node.is_end

    async def load(
        self,
        user: "UserEntity",
        project_name: str,
        access_type: "AccessType" = "read",
    ) -> None:
        """
        Load the user's access permissions into the trie structure.

        Args:
            user (UserEntity): The user whose permissions are being loaded.
            project_name (str): The name of the project.
            access_type (AccessType): The type of access to check (default is "read").

        Returns:
            None
        """
        fal = await folder_access_list(user, project_name, access_type)
        if fal is None:
            self.is_none = True
            return

        for row in fal:
            path = row.strip('"')
            if path.endswith("/%"):
                node = self.root
                for char in path[:-2].split("/"):
                    if char not in node.children:
                        node.children[char] = TrieNode()
                    node = node.children[char]
                node.is_end = True
            else:
                self.exact_paths.add(path)
