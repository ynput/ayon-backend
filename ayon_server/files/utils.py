from collections.abc import AsyncGenerator

import aiofiles.os


async def list_local_files(root: str) -> AsyncGenerator[str, None]:
    records = await aiofiles.os.scandir(root)
    for rec in records:
        if rec.is_dir():
            async for file in list_local_files(rec.path):
                yield file
        else:
            yield rec.name
