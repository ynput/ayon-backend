import json
from typing import Annotated

from ayon_server.entities import ProjectEntity
from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.graphql.connections import VersionsConnection
from ayon_server.graphql.edges import VersionEdge
from ayon_server.graphql.nodes.version import VersionNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGHasLinks,
    ARGIds,
    ARGLast,
    ColumnMetadata,
    FieldInfo,
    argdesc,
    create_child_folder_ctes,
    create_folder_access_list,
    get_folder_fields_block,
    get_has_links_conds,
    get_product_fields_block,
    resolve,
    sortdesc,
)
from ayon_server.graphql.resolvers.pagination import create_pagination
from ayon_server.graphql.types import Info
from ayon_server.sqlfilter import QueryFilter, build_filter, filter_columns
from ayon_server.types import (
    validate_name_list,
    validate_status_list,
    validate_user_name_list,
)
from ayon_server.utils import SQLTool, slugify

from .field_stats import (
    MetricTargetInput,
    generate_field_stats,
    generate_specific_stats_columns,
    generate_stats_columns,
)
from .sorting import get_attrib_sort_case, get_status_sort_case

SORT_OPTIONS = {
    "author": "versions.author",
    "version": "versions.version",
    "createdAt": "versions.created_at",
    "updatedAt": "versions.updated_at",
    "createdBy": "versions.created_by",
    "updatedBy": "versions.updated_by",
    "tags": "array_to_string(versions.tags, '')",
    "productType": "products.product_type",
    "productBaseType": "products.product_base_type",
    "productName": "products.name",
    "folderName": "folders.name",
    "folderType": "folders.folder_type",
    "taskName": "tasks.name",
    "taskType": "tasks.task_type",
    "path": "",  # special case handled in the code (is here for docs)
}

# Joins the sortable columns come from. Sort keys that aren't listed here
# (and attrib.* sorting) are columns of the versions table itself.
SORT_JOINS = {
    "productType": ("products",),
    "productBaseType": ("products",),
    "productName": ("products",),
    "folderName": ("folders",),
    "folderType": ("folders",),
    "taskName": ("tasks",),
    "taskType": ("tasks",),
    "path": ("folder_ex", "products"),
}

# Backwards-compat fallback for projects with NULL product_base_type
PRODUCT_BASE_TYPE = "COALESCE(products.product_base_type, products.product_type)"

# Columns of the `filter` argument that don't live on the versions table:
# the expression that provides them, and the join it comes from.
FILTER_COLUMN_SOURCES = {
    "product_type": ("products.product_type", "products"),
    "product_base_type": (PRODUCT_BASE_TYPE, "products"),
    "task_type": ("tasks.task_type", "tasks"),
    "folder_type": ("folders.folder_type", "folders"),
    "hero_version_id": ("hv.hero_version_id", "hv"),
}


def available_joins(project_name: str) -> dict[str, str]:
    """Every join the versions query can use, keyed by its SQL alias.

    Order matters: joins are emitted in the order they are defined here,
    so a join may only reference the versions table or an alias above it.
    """
    return {
        "products": f"""
            INNER JOIN project_{project_name}.products AS products
            ON products.id = versions.product_id
            """,
        "folder_ex": f"""
            INNER JOIN project_{project_name}.exported_attributes AS folder_ex
            ON folder_ex.folder_id = products.folder_id
            """,
        "folders": f"""
            INNER JOIN project_{project_name}.folders AS folders
            ON folders.id = products.folder_id
            """,
        "tasks": f"""
            LEFT JOIN project_{project_name}.tasks AS tasks
            ON tasks.id = versions.task_id
            """,
        # Descendants of folder_ids, resolved by create_child_folder_ctes
        "cfi": """
            INNER JOIN child_folder_ids AS cfi
            ON cfi.id = products.folder_id
            """,
        "gav": """
            INNER JOIN guest_accessible_versions AS gav
            ON gav.entity_id = versions.id
            """,
        # One version per folder, resolved by the latestPerFolder CTE.
        # Looked up via the unique version_creation_order_idx.
        "lvpf": """
            INNER JOIN latest_versions_per_folder AS lvpf
            ON lvpf.creation_order = versions.creation_order
            """,
        # A correlated LATERAL fetch (indexed via activity_origin_desc_idx on
        # entity_type, entity_id, created_at DESC) instead of a CTE that
        # aggregates every version's comments project-wide and then joins
        # that back in: with several other LATERAL joins (rv/lv/ldv/hv)
        # already forcing this query into a nested-loop-heavy plan, postgres
        # was never promoting that join to a hash join, and instead
        # rescanning the whole aggregated comment set per output row.
        "comments": f"""
            LEFT JOIN LATERAL (
                SELECT json_agg(
                    json_build_object(
                        'activity_id', activity_id,
                        'body', body,
                        'author', author,
                        'created_at', created_at
                    )
                    ORDER BY created_at DESC
                ) AS comments
                FROM (
                    SELECT
                        activity_id,
                        body,
                        activity_data->>'author' AS author,
                        created_at
                    FROM project_{project_name}.activity_feed
                    WHERE activity_type = 'comment'
                    AND entity_type = 'version'
                    AND reference_type = 'origin'
                    AND entity_id = versions.id
                    ORDER BY created_at DESC
                    LIMIT 5
                ) x
            ) comments ON true
            """,
        # A correlated LATERAL probe (indexed on activity_references.entity_id)
        # instead of a "reviewables" CTE: the CTE gets referenced twice here
        # (column + filter), which forces postgres to materialize it, i.e.
        # compute reviewable status for every version in the whole project
        # before pagination is applied, rather than per-row on demand.
        "rv": f"""
            LEFT JOIN LATERAL (
                SELECT entity_id AS id
                FROM project_{project_name}.activity_feed
                WHERE entity_type = 'version'
                AND activity_type = 'reviewable'
                AND entity_id = versions.id
                LIMIT 1
            ) rv ON true
            """,
        "lv": f"""
            LEFT JOIN LATERAL (
                SELECT id
                FROM project_{project_name}.versions lv_inner
                WHERE lv_inner.product_id = versions.product_id
                AND lv_inner.version >= 0
                ORDER BY lv_inner.creation_order DESC
                LIMIT 1
            ) lv ON true
            """,
        # Depends on the done_statuses CTE
        "ldv": f"""
            LEFT JOIN LATERAL (
                SELECT v.id
                FROM project_{project_name}.versions v
                WHERE v.product_id = versions.product_id
                AND v.version >= 0
                AND v.status IN (SELECT name FROM done_statuses)
                ORDER BY v.creation_order DESC
                LIMIT 1
            ) ldv ON true
            """,
        "hv": f"""
            LEFT JOIN LATERAL (
                SELECT
                    versions.id AS id,
                    hero_versions.id AS hero_version_id
                FROM project_{project_name}.versions AS hero_versions
                WHERE hero_versions.product_id = versions.product_id
                AND hero_versions.version < 0
                AND ABS(hero_versions.version) = versions.version
                LIMIT 1
            ) hv ON true
            """,
    }


class Joins:
    """Joins used by a single versions query, tracked by what needs them.

    Every join is requested by its SQL alias, along with the reason:

      - `for_filter` - one of the WHERE conditions references it
      - `for_sort`   - one of the ORDER BY expressions references it
      - `for_output` - a requested field needs one of its columns

    The query is built in stages and each stage takes only what it needs:
    latestPerFolder reduces the set to one version per folder using
    `filtering`, the page CTE picks the rows to return using `selecting`,
    and the main query hydrates that page using `all`. That is what keeps
    the LATERALs out of the first two stages - being correlated, they
    would otherwise be evaluated for every version the filters match,
    rather than once per returned row.
    """

    def __init__(self, project_name: str) -> None:
        self._available = available_joins(project_name)
        self._for_filter: set[str] = set()
        self._for_sort: set[str] = set()
        self._for_output: set[str] = set()
        self._extra: list[str] = []

    def for_filter(self, *aliases: str) -> None:
        self._for_filter.update(aliases)

    def for_sort(self, *aliases: str) -> None:
        self._for_sort.update(aliases)

    def for_output(self, *aliases: str) -> None:
        self._for_output.update(aliases)

    def replace_filtering(self, *aliases: str) -> None:
        """Drop the filtering joins in favour of ones that subsume them.

        latestPerFolder bakes every condition - and the joins those
        conditions needed - into a CTE of its own, so from that point on
        joining that CTE is all the filtering the query has left to do.
        """
        self._for_filter = set(aliases)

    def add(self, *sql: str) -> None:
        """Add ready-made joins that only the main query needs.

        Used for the dynamically built folder/product field blocks.
        """
        self._extra.extend(sql)

    def _emit(self, aliases: set[str]) -> list[str]:
        return [sql for alias, sql in self._available.items() if alias in aliases]

    @property
    def filtering(self) -> list[str]:
        """Joins needed to evaluate the WHERE conditions."""
        return self._emit(self._for_filter)

    @property
    def selecting(self) -> list[str]:
        """Joins needed to pick and order the rows of a page."""
        return self._emit(self._for_filter | self._for_sort)

    @property
    def hydrating(self) -> list[str]:
        """Joins of a main query whose rows come from the page CTE.

        The page has already been filtered, so re-joining anything that
        only filters would just give the planner a second, wider way to
        reach the same rows - and a chance to run the LATERALs against
        that one instead of against the page.
        """
        return self._emit(self._for_sort | self._for_output) + self._extra

    @property
    def all(self) -> list[str]:
        """Joins of a main query that filters the rows itself."""
        used = self._for_filter | self._for_sort | self._for_output
        return self._emit(used) + self._extra


async def get_versions(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
    version: int | None = None,
    versions: list[int] | None = None,
    statuses: Annotated[
        list[str] | None, argdesc("List of statuses to filter by")
    ] = None,
    tags: Annotated[
        list[str] | None,
        argdesc("List of tags to filter by"),
    ] = None,
    product_ids: Annotated[
        list[str] | None,
        argdesc("List of parent products IDs"),
    ] = None,
    task_ids: Annotated[
        list[str] | None,
        argdesc("List of parent task IDs"),
    ] = None,
    folder_ids: Annotated[
        list[str] | None,
        argdesc("List of folder IDs to filter by"),
    ] = None,
    include_folder_children: Annotated[
        bool,
        argdesc("Include versions in child folders when folderIds is used"),
    ] = False,
    authors: Annotated[
        list[str] | None,
        argdesc("List of version author user names to filter by."),
    ] = None,
    latest_only: Annotated[
        bool,
        argdesc("DEPRECATED List only latest versions"),
    ] = False,
    hero_only: Annotated[
        bool,
        argdesc("DEPRECATED List only hero versions"),
    ] = False,
    hero_or_latest_only: Annotated[
        bool,
        argdesc("DEPRECATED List hero versions. If hero does not exist, list latest"),
    ] = False,
    has_reviewables: Annotated[
        bool | None,
        argdesc("Filter versions that have reviewables"),
    ] = None,
    has_hero: Annotated[
        bool | None,
        argdesc("Filter versions that have a hero version"),
    ] = None,
    featured_only: Annotated[
        list[str] | None,
        argdesc(
            "List only one version for each product, based on the order of flags, "
            "that can be 'hero', 'latestDone' and 'latest."
            "This is a replacement for the deprecated "
            "heroOnly, latestOnly and heroOrLatestOnly"
        ),
    ] = None,
    featured_only_entity_type: Annotated[
        str,
        argdesc("Deprecated and noop"),
    ] = "product",
    latest_per_folder: Annotated[
        bool,
        argdesc(
            """
            Return only a single version - the latest one (by creation order)
            for each folder that matches all the other given filters.
            The result set is still ordered according to sortBy.
            """
        ),
    ] = False,
    has_links: ARGHasLinks = None,
    search: Annotated[
        str | None,
        argdesc("Fuzzy text search filter"),
    ] = None,
    filter: Annotated[
        str | None,
        argdesc("Filter tasks using QueryFilter"),
    ] = None,
    folder_filter: Annotated[
        str | None,
        argdesc("Filter tasks by their folders using QueryFilter"),
    ] = None,
    task_filter: Annotated[
        str | None,
        argdesc("Filter products by their tasks (via versions) using QueryFilter"),
    ] = None,
    product_filter: Annotated[
        str | None,
        argdesc("Filter versions by their product using QueryFilter"),
    ] = None,
    sort_by: Annotated[
        str | None,
        sortdesc(SORT_OPTIONS),
    ] = None,
    calculate_statistics: Annotated[
        bool, argdesc("Whether to calculate column statistics")
    ] = False,
    calculate_specific_statistics: Annotated[
        list[MetricTargetInput] | None,
        argdesc("Map of attribute names to lists of desired statistical aggregations"),
    ] = None,
) -> VersionsConnection:
    """Return a list of versions."""

    project_name = root.project_name
    project = await ProjectEntity.load(project_name)
    user = info.context["user"]
    fields = FieldInfo(info, ["versions.edges.node", "version"])

    use_folder_query = False

    #
    # SQL
    #

    sql_cte = []
    sql_conditions = []

    joins = Joins(project_name)
    # products is unconditional in both roles: it is the root every
    # folder-side join hangs off (they all match on products.folder_id)
    # and what latestPerFolder groups by, and it supplies output columns.
    joins.for_filter("products", "folder_ex")
    joins.for_output("products", "folder_ex", "folders", "tasks")

    sql_columns = [
        "versions.*",
        "versions.creation_order AS creation_order",
        "folder_ex.path AS _folder_path",
        "products.name AS _product_name",
    ]

    if fields.any_endswith("latestComments"):
        joins.for_output("comments")
        sql_columns.append("comments.comments AS latest_comments")

    if fields.any_endswith("hasReviewables") or (has_reviewables is not None):
        joins.for_output("rv")
        sql_columns.append("rv IS NOT NULL AS has_reviewables")

        if has_reviewables is not None:
            joins.for_filter("rv")
            if has_reviewables:
                sql_conditions.append("rv IS NOT NULL")
            else:
                sql_conditions.append("rv IS NULL")

    #
    # Direct, version-specific filtering
    #

    # Empty overrides. Skip querying
    if ids == ["0" * 32]:
        return VersionsConnection(edges=[])

    if ids is not None:
        if not ids:
            return VersionsConnection()
        sql_conditions.append(f"versions.id IN {SQLTool.id_array(ids)}")

    if version:
        sql_conditions.append(f"versions.version = {version}")

    if versions is not None:
        if not versions:
            return VersionsConnection()
        sql_conditions.append(f"versions.version IN {SQLTool.array(versions)}")

    if authors is not None:
        if not authors:
            return VersionsConnection()
        validate_user_name_list(authors)
        sql_conditions.append(f"versions.author IN {SQLTool.array(authors)}")

    if statuses is not None:
        if not statuses:
            return VersionsConnection()
        validate_status_list(statuses)
        sql_conditions.append(f"versions.status IN {SQLTool.array(statuses)}")

    if tags is not None:
        if not tags:
            return VersionsConnection()
        validate_name_list(tags)
        sql_conditions.append(f"versions.tags @> {SQLTool.array(tags, curly=True)}")

    if product_ids is not None:
        if not product_ids:
            return VersionsConnection()
        sql_conditions.append(f"versions.product_id IN {SQLTool.id_array(product_ids)}")
    elif root.__class__.__name__ == "ProductNode":
        sql_conditions.append(f"versions.product_id = '{root.id}'")

    if task_ids:
        sql_conditions.append(f"versions.task_id IN {SQLTool.id_array(task_ids)}")
    elif root.__class__.__name__ == "TaskNode":
        sql_conditions.append(f"versions.task_id = '{root.id}'")

    if folder_ids is not None:
        if not folder_ids:
            return VersionsConnection()

        if include_folder_children:
            sql_cte.extend(create_child_folder_ctes(project_name, folder_ids))
            # The join itself is the filter
            joins.for_filter("cfi")

        else:
            sql_conditions.append(
                f"products.folder_id IN {SQLTool.id_array(folder_ids)}"
            )

    #
    # Latest / latest done / hero versions logic
    #

    if (
        fields.any_endswith("isLatest")
        or fields.any_endswith("isLatestDone")
        or fields.any_endswith("heroVersionId")
        or latest_only
        or hero_only
        or hero_or_latest_only
        or featured_only
    ):
        sql_cte.append(
            f"""
            done_statuses AS MATERIALIZED (
                SELECT name from project_{project_name}.statuses
                WHERE data->>'state' = 'done'
            )
            """
        )

        joins.for_output("lv", "ldv", "hv")

        sql_columns.extend(
            [
                "hv.hero_version_id AS hero_version_id",
                "lv IS NOT NULL AS is_latest",
                "ldv IS NOT NULL AS is_latest_done",
            ]
        )

    #
    # Filtering by latest / hero versions
    # (deprecated part)
    #

    if latest_only:
        joins.for_filter("lv")
        sql_conditions.append("versions.id = lv.id")

    elif hero_only:
        # This returns actual (negative) hero versions only
        # Not versions that point to hero via hero_versions
        sql_conditions.append("versions.version < 0")

    elif hero_or_latest_only:
        # Same as above, but include latest if no hero exists
        # This is provided mainly for backward compatibility and the pipeline
        # The frontend uses new featuredVersion filter instead
        sql_conditions.append("(versions.version < 0 OR versions.version IS NOT NULL)")

    elif has_hero:
        joins.for_filter("hv")
        sql_conditions.append("hv.id IS NOT NULL")

    #
    # Filtering by featured versions
    #

    if featured_only is not None:
        if not featured_only:
            return VersionsConnection()

        coalesce_args = []
        for flag in featured_only:
            if flag == "hero":
                joins.for_filter("hv")
                coalesce_args.append("hv.id")
            elif flag == "latestDone":
                joins.for_filter("ldv")
                coalesce_args.append("ldv.id")
            elif flag == "latest":
                joins.for_filter("lv")
                coalesce_args.append("lv.id")
            else:
                raise BadRequestException(
                    "Invalid featuredOnly value: "
                    f"'{flag}'. Must be one of 'hero', 'latestDone', 'latest'."
                )

        # versions.id must equal whichever candidate wins by flag priority order
        sql_conditions.append(f"versions.id = COALESCE({', '.join(coalesce_args)})")

    #
    # Filtering by links
    #

    if has_links is not None:
        sql_conditions.extend(
            get_has_links_conds(project_name, "versions.id", has_links)
        )

    #
    # Access control
    #

    if user.is_guest:
        if guest_access := user.data.get("guestAccess"):
            entity_list_ids = [
                ga["id"]
                for ga in guest_access
                if ga.get("projectName") == project_name
                and ga.get("type") == "entityList"
                and ga.get("id")
            ]
            if not entity_list_ids:
                return VersionsConnection()

            sql_cte.append(
                f"""guest_accessible_versions AS (
                    SELECT DISTINCT(entity_id)
                    FROM project_{project_name}.entity_list_items i
                    JOIN project_{project_name}.entity_lists l
                    ON l.id = i.entity_list_id
                    AND l.entity_type = 'version'
                    AND l.id IN {SQLTool.id_array(entity_list_ids)}
                    )
                """
            )
        else:
            sql_cte.append(
                f"""guest_accessible_versions AS (
                    SELECT DISTINCT(entity_id)
                    FROM project_{project_name}.entity_list_items i
                    JOIN project_{project_name}.entity_lists l
                    ON l.id = i.entity_list_id
                    AND l.entity_type = 'version'
                    AND (
                            (l.access->'__guests__')::integer > 0
                            OR (l.access->'guest:{user.attrib.email}')::integer > 0
                        )
                    )
                """
            )
        # The join itself is the filter
        joins.for_filter("gav")

    elif not user.is_manager:
        access_list = await create_folder_access_list(root, info)
        if access_list is not None:
            joins.for_filter("folder_ex")
            sql_conditions.append(
                f"folder_ex.path like ANY ('{{ {','.join(access_list)} }}')"
            )

    #
    # Fuzzy search
    #

    if search:
        joins.for_filter("folder_ex")
        terms = slugify(search, make_set=True, min_length=2, split_chars=" ")

        for term in terms:
            sub_conditions = []
            if term.isdigit():
                sub_conditions.append(f"versions.version = {int(term)}")
            elif term.startswith("v") and term[1:].isdigit():
                sub_conditions.append(f"versions.version = {int(term[1:])}")

            sub_conditions.append(f"products.name ILIKE '%{term}%'")
            sub_conditions.append(f"products.product_type ILIKE '%{term}%'")
            sub_conditions.append(f"folder_ex.path ILIKE '%{term}%'")

            condition = " OR ".join(sub_conditions)
            sql_conditions.append(f"({condition})")

    #
    # Filter
    #

    if filter:
        column_whitelist = [
            "id",
            "version",
            "product_id",
            "task_id",
            "author",
            "status",
            "attrib",
            "data",
            "tags",
            "active",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            # virtual
            "product_type",
            "product_base_type",
            "task_type",
            "folder_type",
            "hero_version_id",
        ]

        fdata = json.loads(filter)
        fq = QueryFilter(**fdata)
        if fcond := build_filter(
            fq,
            column_whitelist=column_whitelist,
            table_prefix="versions",
            column_map={
                column: expression
                for column, (expression, _) in FILTER_COLUMN_SOURCES.items()
            },
        ):
            sql_conditions.append(fcond)
            for column in filter_columns(fq):
                if source := FILTER_COLUMN_SOURCES.get(column):
                    joins.for_filter(source[1])

    if product_filter:
        column_whitelist = [
            "id",
            "name",
            "folder_id",
            "product_type",
            "product_base_type",
            "status",
            "attrib",
            "data",
            "tags",
            "active",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]

        fdata = json.loads(product_filter)
        fq = QueryFilter(**fdata)
        if fcond := build_filter(
            fq,
            column_whitelist=column_whitelist,
            table_prefix="products",
            column_map={
                "product_base_type": PRODUCT_BASE_TYPE,
            },
        ):
            sql_conditions.append(fcond)

    if task_filter:
        column_whitelist = [
            "id",
            "name",
            "label",
            "task_type",
            "assignees",
            "status",
            "attrib",
            "data",
            "tags",
            "active",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]

        fdata = json.loads(task_filter)
        fq = QueryFilter(**fdata)
        if fcond := build_filter(
            fq,
            column_whitelist=column_whitelist,
            table_prefix="tasks",
        ):
            sql_conditions.append(fcond)
            joins.for_filter("tasks")

    if folder_filter:
        column_whitelist = [
            "id",
            "name",
            "folder_type",
            "parent_id",
            "status",
            "attrib",
            "data",
            "tags",
            "active",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]

        fdata = json.loads(folder_filter)
        fq = QueryFilter(**fdata)
        if fcond := build_filter(
            fq,
            column_whitelist=column_whitelist,
            table_prefix="folders",
            column_map={"attrib": "folder_ex.attrib"},
        ):
            sql_conditions.append(fcond)
            joins.for_filter("folders", "folder_ex")
            use_folder_query = True

    #
    # Latest version per folder (from the set matching all filters above)
    #

    if latest_per_folder:
        # creation_order is unique and monotonic within a project, so the
        # highest one in a folder *is* the folder's latest version, and
        # max() over a hash aggregate (one entry per folder) replaces what
        # DISTINCT ON (folder_id) can only do as a full sort of every
        # matching version.
        #
        # joins.filtering keeps out everything the conditions don't need,
        # which matters most for the LATERALs feeding latestComments /
        # isLatest / hasReviewables: they are correlated subqueries, so
        # having them in here means running them once per version in the
        # project rather than once per returned row.
        sql_cte.append(
            f"""
            latest_versions_per_folder AS MATERIALIZED (
                SELECT max(versions.creation_order) AS creation_order
                FROM project_{project_name}.versions AS versions
                {" ".join(joins.filtering)}
                {SQLTool.conditions(sql_conditions)}
                GROUP BY products.folder_id
            )
            """
        )

        # Everything above is now baked into latest_versions_per_folder,
        # so joining it replaces both the conditions and the joins they
        # needed. products stays: the sort and output joins hang off it.
        joins.replace_filtering("products", "lvpf")
        sql_conditions = []

    if any("product" in str(field) for field in fields) or use_folder_query:
        product_columns, product_joins = get_product_fields_block()
        sql_columns.extend(product_columns)
        joins.add(*product_joins)

        # The block reads columns off both, and supplies only the
        # public.projects join itself.
        joins.for_output("folders", "folder_ex")
        folder_columns, folder_joins = get_folder_fields_block(
            project_name, "products.folder_id", sql_joins=joins.all
        )
        sql_columns.extend(folder_columns)
        joins.add(*folder_joins)

    #
    # Pagination
    #

    order_by = ["versions.creation_order"]
    if sort_by is not None:
        joins.for_sort(*SORT_JOINS.get(sort_by, ()))
        if sort_by == "status":
            status_type_case = get_status_sort_case(project, "versions.status")
            order_by.insert(0, status_type_case)
        elif sort_by == "path":
            order_by = ["folder_ex.path", "products.name", "versions.version"]
        elif sort_by in SORT_OPTIONS:
            order_by.insert(0, SORT_OPTIONS[sort_by])
        elif sort_by.startswith("attrib."):
            attr_name = sort_by[7:]
            attr_case = await get_attrib_sort_case(attr_name, "versions.attrib")
            order_by.insert(0, attr_case)
        else:
            raise ValueError(f"Invalid sort_by value: {sort_by}")

    sql_from = f"project_{project_name}.versions AS versions"
    main_joins = joins.all

    ordering = ""
    cursor = "''"
    if not calculate_statistics and not calculate_specific_statistics:
        ordering, paging_conds, cursor = create_pagination(
            order_by,
            first,
            after,
            last,
            before,
        )
        sql_conditions.append(paging_conds)

        # Pick the page first, using only the joins needed to filter and
        # sort, and hydrate those rows below. The main query is a wide one
        # - every LATERAL in it is correlated, and the field blocks join
        # in whole folders and products - and without this it all happens
        # before ORDER BY ... LIMIT, i.e. for every version the filters
        # match. Postgres can't defer it on its own: a LIMIT makes a
        # fast-start nested loop look cheap, so it starts feeding rows
        # through the LATERALs in sort order and hopes to hit the limit
        # early, which never happens when the surviving rows are rare.
        sql_cte.append(
            f"""
            page AS MATERIALIZED (
                SELECT versions.id
                FROM project_{project_name}.versions AS versions
                {" ".join(joins.selecting)}
                {SQLTool.conditions(sql_conditions)}
                {ordering}
            )
            """
        )

        # Rows to return, and nothing else, drive the main query.
        sql_from = f"""
            page
            INNER JOIN project_{project_name}.versions AS versions
            ON versions.id = page.id
            """
        main_joins = joins.hydrating
        sql_conditions = []

    #
    # Query
    #

    if sql_cte:
        cte = ", ".join(sql_cte)
        # RECURSIVE (harmless for the non-recursive CTEs here) is required
        # when folder_ids+includeFolderChildren adds create_child_folder_ctes'
        # self-referencing CTE.
        cte = f"WITH RECURSIVE {cte}"
    else:
        cte = ""

    default_columns_metadata: list[ColumnMetadata] = [
        ColumnMetadata("thumbnail_id", "uuid"),
        ColumnMetadata("active", "bool"),
        ColumnMetadata("status", "string"),
    ]

    stats_select_clause = None
    if calculate_specific_statistics:
        stats_select_clause = generate_specific_stats_columns(
            calculate_specific_statistics
        )
    elif calculate_statistics:
        stats_select_clause = generate_stats_columns(default_columns_metadata)

    raw_data_start = ""
    raw_data_end = ""
    if stats_select_clause:
        # Subtype fields live on joined tables, not versions.* — project them into
        # raw_data so specific-stats distributions (e.g. productType) can GROUP BY them.
        sql_columns.extend(
            [
                "products.product_base_type AS product_base_type",
                "products.product_type AS product_type",
                "folders.folder_type AS folder_type",
                "tasks.task_type AS task_type",
            ]
        )
        cte_prefix = ",\n" if cte else "WITH"
        raw_data_start = f"{cte_prefix} raw_data AS ("
        raw_data_end = f"""
            )
            SELECT
                {stats_select_clause}
            FROM raw_data;
            """

    query = f"""
        {cte}
        {raw_data_start}
        SELECT {cursor}, {", ".join(sql_columns)}
        FROM {sql_from}
        {" ".join(main_joins)}
        {SQLTool.conditions(sql_conditions)}
        {ordering}
        {raw_data_end}
    """

    # print()
    # print("Versions query:")
    # print(query)
    # print()

    if stats_select_clause:
        field_stats = await generate_field_stats(query)

        return VersionsConnection(edges=[], field_stats=field_stats)

    return await resolve(
        VersionsConnection,
        VersionEdge,
        VersionNode,
        query,
        project_name=project_name,
        first=first,
        last=last,
        order_by=order_by,
        context=info.context,
    )


async def get_version(root, info: Info, id: str) -> VersionNode:
    """Return a task node based on its ID"""
    if not id:
        raise BadRequestException("Version ID not specified")
    connection = await get_versions(root, info, ids=[id])
    if not connection.edges:
        raise NotFoundException("Version not found")
    return connection.edges[0].node
