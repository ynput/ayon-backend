from ayon_server.entities.user import UserEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import BadRequestException, ForbiddenException

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

    # Get project list
    # statement = await conn.prepare("SELECT name FROM projects")
    # project_names = [row["name"] async for row in statement.cursor()]

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

        # Do the same for every active project settings
        # TODO: Do we want this?
        #
        # for project_name in project_names:

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
