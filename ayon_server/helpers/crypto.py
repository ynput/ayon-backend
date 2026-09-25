import json
import time
import zlib
from typing import Any
from urllib.parse import quote, unquote

from cryptography.fernet import Fernet
from pydantic import BaseModel

from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.utils import hash_data

FERNET_KEY_SECRET_NAME = "_fernet_key"


async def get_fernet_key() -> bytes:
    cached = await Redis.get("global", "fernet-key")
    if cached:
        return cached

    query = "SELECT value FROM secrets WHERE name = $1"
    result = await Postgres.fetchrow(query, FERNET_KEY_SECRET_NAME)

    if result is None:
        key = Fernet.generate_key()
        query = "INSERT INTO secrets (name, value) VALUES ($1, $2)"
        await Postgres.execute(query, FERNET_KEY_SECRET_NAME, key.decode())
    else:
        key = result["value"].encode()

    await Redis.set("global", "fernet-key", key.decode())

    return key


class EncryptedData(BaseModel):
    token: str
    data: dict[str, Any]
    timestamp: int

    async def set_nonce(self, ttl: int = 3600 * 24) -> None:
        """Set the nonce to disallow replay attacks."""
        nonce = hash_data(self.token)
        await Redis.set("fernet-nonce", nonce, str(self.timestamp), ttl=ttl)

    async def validate_nonce(self) -> bool:
        """Validate the nonce to prevent replay attacks."""
        nonce = hash_data(self.token)
        stored_timestamp = await Redis.get("fernet-nonce", nonce)
        await Redis.delete("fernet-nonce", nonce)  # Clean up after validation
        if stored_timestamp is None:
            return False
        try:
            return stored_timestamp.decode() == str(self.timestamp)
        except ValueError:
            return False

    @property
    def quoted_token(self) -> str:
        """Return the token in a URL-safe format."""
        return quote(self.token)


async def encrypt_json_urlsafe(data: dict[str, Any]) -> EncryptedData:
    key = await get_fernet_key()
    fernet = Fernet(key)
    json_bytes = json.dumps(data).encode("utf-8")
    compressed = zlib.compress(json_bytes)
    now = int(time.time())
    encrypted = fernet.encrypt_at_time(compressed, now)
    return EncryptedData(token=encrypted.decode(), data=data, timestamp=now)


async def decrypt_json_urlsafe(token: str) -> EncryptedData:
    key = await get_fernet_key()
    fernet = Fernet(key)
    encrypted = unquote(token).encode("utf-8")
    compressed = fernet.decrypt(encrypted)
    json_bytes = zlib.decompress(compressed)
    data = json.loads(json_bytes.decode("utf-8"))
    timestamp = fernet.extract_timestamp(encrypted)
    return EncryptedData(token=token, data=data, timestamp=timestamp)
