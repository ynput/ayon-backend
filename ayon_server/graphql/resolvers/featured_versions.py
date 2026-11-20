"""Featured version of a product: hero, latest done or latest.

The versions resolver picks the featured version with LATERAL joins that are
built into its staged query. Entity list items need the same answer for
versions that are already selected by the list, so this module gives it as
one SQL expression that can be used as a column.
"""

from ayon_server.exceptions import BadRequestException

FEATURED_VERSION_FLAGS = ("hero", "latestDone", "latest")


def _flag_subquery(project_name: str, flag: str, version_alias: str) -> str:
    schema = f"project_{project_name}"
    product_id = f"{version_alias}.product_id"

    if flag == "hero":
        # The version a hero version of the product points to
        return f"""(
            SELECT v.id
            FROM {schema}.versions AS v
            INNER JOIN {schema}.versions AS h
            ON h.product_id = v.product_id
            AND h.version < 0
            AND ABS(h.version) = v.version
            WHERE v.product_id = {product_id}
            LIMIT 1
        )"""

    if flag == "latestDone":
        # The newest version whose status has the "done" state
        return f"""(
            SELECT v.id
            FROM {schema}.versions AS v
            WHERE v.product_id = {product_id}
            AND v.version >= 0
            AND v.status IN (
                SELECT name FROM {schema}.statuses
                WHERE data->>'state' = 'done'
            )
            ORDER BY v.creation_order DESC
            LIMIT 1
        )"""

    if flag == "latest":
        return f"""(
            SELECT v.id
            FROM {schema}.versions AS v
            WHERE v.product_id = {product_id}
            AND v.version >= 0
            ORDER BY v.creation_order DESC
            LIMIT 1
        )"""

    raise BadRequestException(
        f"Invalid featuredOnly value: '{flag}'. "
        f"Must be one of {', '.join(repr(f) for f in FEATURED_VERSION_FLAGS)}."
    )


def featured_version_id_expression(
    project_name: str,
    flags: list[str],
    version_alias: str,
) -> str:
    """SQL expression for the id of the featured version of a product.

    `version_alias` names a versions row in the surrounding query; the
    expression returns the featured version of that row's product, trying
    the flags in the given order (the first one that exists wins), the same
    as `featuredOnly` of the versions query. NULL when none of them exists.
    """
    if not flags:
        raise BadRequestException("featuredOnly needs at least one value")
    subqueries = [_flag_subquery(project_name, f, version_alias) for f in flags]
    if len(subqueries) == 1:
        return subqueries[0]
    return f"COALESCE({', '.join(subqueries)})"
