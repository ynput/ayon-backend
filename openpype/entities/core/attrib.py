import asyncio
import collections
import threading

from typing import Any
from openpype.lib.postgres import Postgres


class AttributeLibrary:
    """Dynamic attributes loader class.

    This is very wrong and i deserve a punishment for this,
    but it works. Somehow. It needs to be initialized when
    this module is loaded and it has to load the attributes
    from the database in blocking mode regardless the running
    event loop. So it connects to the DB independently in a
    different thread and waits until it is finished.

    Attribute list for each entity type may be then accessed
    using __getitem__ method.
    """

    def __init__(self) -> None:
        self.data = collections.defaultdict(list)
        _thread = threading.Thread(target=self.execute)
        _thread.start()
        _thread.join()

    def execute(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.load())
        loop.close()

    async def load(self) -> None:
        query = "SELECT name, scope, data from public.attributes"
        await Postgres.connect()
        async for row in Postgres.iterate(query):
            attrd = {"name": row["name"], **row["data"]}
            for scope in row["scope"]:
                self.data[scope].append(attrd)

    def __getitem__(self, key) -> list[dict[str, Any]]:
        return self.data[key]


attribute_library = AttributeLibrary()
