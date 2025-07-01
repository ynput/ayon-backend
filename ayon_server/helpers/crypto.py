import json
import zlib
from urllib.parse import quote, unquote

from cryptography.fernet import Fernet

from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis

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


async def encrypt_json_urlsafe(data: dict) -> str:
    key = await get_fernet_key()
    fernet = Fernet(key)
    json_bytes = json.dumps(data).encode("utf-8")
    compressed = zlib.compress(json_bytes)
    encrypted = fernet.encrypt(compressed)
    return quote(encrypted.decode())


async def decrypt_json_urlsafe(token: str) -> dict:
    key = await get_fernet_key()
    fernet = Fernet(key)
    encrypted = unquote(token).encode("utf-8")
    compressed = fernet.decrypt(encrypted)
    json_bytes = zlib.decompress(compressed)
    return json.loads(json_bytes.decode("utf-8"))
