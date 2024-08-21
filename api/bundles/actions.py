from ayon_server.entities.user import UserEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import BadRequestException, ForbiddenException
from ayon_server.helpers.project_list import get_project_list

from .models import BundleModel


async def promote_bundle(bundle: BundleModel, user: UserEntity, conn):
    """Promote a bundle to production.

    That includes copying staging settings to production.
    """

    if not user.is_admin:
        raise ForbiddenException("Only admins can promote bundles")

    if not bundle.is_staging:
        raise BadRequestException("Only staging bundles can be promoted")

    if bundle.is_dev:
        raise BadRequestException("Dev bundles cannot be promoted")

    await conn.execute("UPDATE bundles SET is_production = FALSE")
    await conn.execute(
        """
        UPDATE bundles
        SET is_production = TRUE
        WHERE name = $1
        """,
        bundle.name,
    )

    project_list = await get_project_list()

    # Copy staging settings to production

    for addon_name, addon_version in bundle.addons.items():
        sres = await conn.fetch(
            """
            SELECT data FROM settings
            WHERE addon_name = $1 AND addon_version = $2
            AND variant = 'staging'
            """,
            addon_name,
            addon_version,
        )
        if not sres:
            data = {}
        else:
            data = sres[0]["data"]
        await conn.execute(
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

        for project in project_list:
            if not project.active:
                continue

            pres = await conn.fetch(
                f"""
                SELECT data FROM project_{project.name}.settings
                WHERE addon_name = $1 AND addon_version = $2
                AND variant = 'staging'
                """,
                addon_name,
                addon_version,
            )
            if not pres:
                data = {}
            else:
                data = pres[0]["data"]

            await conn.execute(
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

    await EventStream.dispatch(
        "bundle.status_changed",
        user=user.name,
        description=f"Bundle {bundle.name} promoted to production",
        summary={
            "name": bundle.name,
            "status": "production",
        },
        payload=data,
    )
