import time
from pathlib import Path

from ayon_server.lib.postgres import Postgres
from ayon_server.logging import critical_error, log_traceback, logger


async def db_migration(has_schema: bool = True) -> int:
    """Migrate the database schema.

    Returns the latest migration version applied
    (or available if db is not initialized).
    That number is then saved in the database.
    """

    # For future use:
    # current_version = 0
    # if has_schema:
    #     res = await Postgres.fetch("SELECT value FROM config WHERE key = 'dbVersion'")
    #     if res:
    #         current_version = int(res[0]["value"])

    migrations_dir = "schemas/migrations"
    available_migrations = sorted(
        (f for f in Path(migrations_dir).glob("*.sql") if f.stem.isdigit()),
        key=lambda x: int(x.stem),
    )

    # We evaluate has_schema here rather than in the main function,
    # because we need to know the latest database version, even if
    # the schema is not present yet.
    if has_schema:
        # logging.debug(f"Current database version: {current_version}")
        logger.debug(f"Applying {len(available_migrations)} database migrations")
        migration_version = 0
        for migration in available_migrations:
            migration_version = int(migration.stem)

            # We still need to apply all migrations to ensure
            # imported project will have the same schema.

            # The following condition may be uncommented,
            # when we switch project backup to json-based,
            # database aware format.

            # Keep in mind that once this is enabled, we'll
            # also be skipping the first (0) migration, that
            # currently handles upgrades from < 1.0.0 era

            # if migration_version <= current_version:
            #    continue
            # logging.info(f"Applying migration {migration_version}")
            start_time = time.monotonic()
            try:
                await Postgres.execute(migration.read_text(), timeout=600)
            except Exception:
                log_traceback(f"Migration {migration.stem} failed")
                critical_error("Database migration failed. Setup cannot continue.")
            elapsed = time.monotonic() - start_time
            if elapsed > 1:
                msg = f"Migration {migration.stem} applied in {elapsed:.2f}s (slow...)"
                logger.debug(msg)
        return migration_version

    return int(available_migrations[-1].stem)
