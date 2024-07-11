import aiocache

from ayon_server.addons import AddonLibrary


@aiocache.cached(ttl=60)
async def is_transcoder_available() -> bool:
    library = AddonLibrary.getinstance()
    transcoder = await library.get_addon_by_variant("transcoder", "production")
    if transcoder is None:
        return False
    return True
