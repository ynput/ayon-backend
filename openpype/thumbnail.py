import httpx

from openpype.lib.postgres import Postgres


class Thumbnail:
    @classmethod
    def store(cls, mime: str, data: bytes) -> int:
        pass

    @classmethod
    def get(cls, id: int) -> tuple[str, bytes]:
        return ("image/jpeg", b"")
