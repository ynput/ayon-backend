#!/usr/bin/env python3

from pprint import pprint

from ayon_server.addons import AddonLibrary
from ayon_server.initialize import ayon_init
from ayon_server.settings.common import migrate_settings_overrides


async def main():
    await ayon_init(extensions=False)

    source_addon = AddonLibrary.addon("sso", "1.0.5")
    target_addon = AddonLibrary.addon("sso", "1.1.1")

    studio_overrides = await source_addon.get_studio_overrides(variant="staging")
    defaults = await target_addon.get_default_settings()
    assert defaults

    print("Studio overrides:")
    pprint(studio_overrides)

    print("Default settings:")
    pprint(defaults)

    new_overrides = migrate_settings_overrides(
        studio_overrides,
        new_model_class=target_addon.get_settings_model(),
        defaults=defaults.dict(),
    )

    pprint("Migrated overrides:")
    pprint(new_overrides)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
