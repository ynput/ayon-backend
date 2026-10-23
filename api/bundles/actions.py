from ayon_server.entities.user import UserEntity
from ayon_server.exceptions import BadRequestException, ForbiddenException
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres

from .models import BundleModel


async def copy_staging_settings(bundle: BundleModel, user: UserEntity):
    """Copy staging settings of the bundle addons to production.

    This is the first step of the bundle promotion. The bundle itself
    is then set as production using update_bundle.
    """

    assert await Postgres.is_in_transaction(), (
        "copy_staging_settings function must be called within a transaction"
    )

    if not user.is_admin:
        raise ForbiddenException("Only admins can promote bundles")

    if not bundle.is_staging:
        raise BadRequestException("Only staging bundles can be promoted")

    if bundle.is_dev:
        raise BadRequestException("Dev bundles cannot be promoted")

    project_list = await get_project_list()

    # Copy staging settings to production

    for addon_name, addon_version in bundle.addons.items():
        if not addon_version:
            continue

        sres = await Postgres.fetch(
            """
            SELECT data FROM settings
            WHERE addon_name = $1 AND addon_version = $2
            AND variant = 'staging'
            """,
            addon_name,
            addon_version,
        )
        if sres:
            data = sres[0]["data"]
            await Postgres.execute(
                """
                INSERT INTO settings (addon_name, addon_version, variant, data)
                VALUES ($1, $2, 'production', $3)
                ON CONFLICT (addon_name, addon_version, variant)
                DO UPDATE SET data = $3
                """,
                addon_name,
                addon_version,
                data,
            )
        else:
            await Postgres.execute(
                """
                DELETE FROM settings WHERE addon_name = $1 AND addon_version = $2
                AND variant = 'production'
                """,
                addon_name,
                addon_version,
            )

        for project in project_list:
            pres = await Postgres.fetch(
                f"""
                SELECT data FROM project_{project.name}.settings
                WHERE addon_name = $1 AND addon_version = $2
                AND variant = 'staging'
                """,
                addon_name,
                addon_version,
            )
            if pres:
                data = pres[0]["data"]
                await Postgres.execute(
                    f"""
                    INSERT INTO project_{project.name}.settings
                    (addon_name, addon_version, variant, data)
                    VALUES ($1, $2, 'production', $3)
                    ON CONFLICT (addon_name, addon_version, variant)
                    DO UPDATE SET data = $3
                    """,
                    addon_name,
                    addon_version,
                    data,
                )
            else:
                await Postgres.execute(
                    f"""
                    DELETE FROM project_{project.name}.settings
                    WHERE addon_name = $1 AND addon_version = $2
                    AND variant = 'production'
                    """,
                    addon_name,
                    addon_version,
                )
