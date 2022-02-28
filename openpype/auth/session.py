__all__ = ["Session"]

import time

from pydantic import BaseModel

from openpype.entities import UserEntity
from openpype.lib.redis import Redis
from openpype.utils import create_hash, json_dumps, json_loads


class SessionModel(BaseModel):
    user: UserEntity.model()
    token: str
    created: float
    last_used: float
    ip: str | None = None

    class Config:
        json_loads = json_loads
        json_dumps = json_dumps

    @property
    def user_entity(self):
        return UserEntity(exists=True, **self.user.dict())


class Session:
    ttl = 24 * 3600
    ns = "session"
    model = SessionModel

    @classmethod
    async def check(cls, token: str, ip: str | None) -> SessionModel | None:
        """Return a session corresponding to a given access token.

        Return None if the token is invalid.
        If the session is expired, it will be removed from the database.
        If it's not expired, update the last_used field and extend
        its lifetime.
        """
        data = await Redis.get(cls.ns, token)
        if not data:
            return None

        session = SessionModel(**json_loads(data))
        if time.time() - session.last_used > cls.ttl:
            # TODO: some logging here?
            await Redis.delete(cls.ns, token)
            return None

        if ip and session.ip and session.ip != ip:
            # TODO: log this?
            return None

        # Extend the session lifetime only if it's in its second half
        # (save update requests).
        # So it doesn't make sense to call the parameter last_used is it?
        # Whatever. Fix later.

        if time.time() - session.created > cls.ttl / 2:
            session.last_used = time.time()
            await Redis.set(cls.ns, token, json_dumps(session.dict()))

        return session

    @classmethod
    async def create(cls, user: UserEntity, ip: str = None) -> SessionModel:
        """Create a new session for a given user."""
        token = create_hash()
        session = SessionModel(
            user=user.dict(),
            token=token,
            created=time.time(),
            last_used=time.time(),
            ip=ip,
        )
        await Redis.set(cls.ns, token, session.json())
        return session

    @classmethod
    async def delete(cls, token: str) -> None:
        await Redis.delete(cls.ns, token)
