__all__ = ["Session"]

import time
from typing import AsyncGenerator

from fastapi import Request
from nxtools import logging

from ayon_server.api.clientinfo import ClientInfo, get_client_info, get_real_ip
from ayon_server.entities import UserEntity
from ayon_server.lib.redis import Redis
from ayon_server.types import OPModel
from ayon_server.utils import create_hash, json_dumps, json_loads


class SessionModel(OPModel):
    user: UserEntity.model.main_model  # type: ignore
    token: str
    created: float
    last_used: float
    is_service: bool = False
    client_info: ClientInfo | None = None


class Session:
    ttl = 24 * 3600
    ns = "session"

    @classmethod
    def is_expired(cls, session: SessionModel) -> bool:
        ttl = 600 if session.is_service else cls.ttl
        return time.time() - session.last_used > ttl

    @classmethod
    async def check(cls, token: str, request: Request | None) -> SessionModel | None:
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

        if cls.is_expired(session):
            # TODO: some logging here?
            await Redis.delete(cls.ns, token)
            return None

        if request:
            if (
                not session.client_info
                or session.client_info.site_id != request.headers.get("x-ayon-site-id")
            ):
                session.client_info = get_client_info(request)
                session.last_used = time.time()
                await Redis.set(cls.ns, token, session.json())
            else:
                real_ip = get_real_ip(request)
                if session.client_info.ip != real_ip:
                    logging.warning(
                        "Session IP mismatch. "
                        f"Stored: {session.client_info.ip}, current: {real_ip}"
                    )
                    return None

        # extend normal tokens validity, but not service tokens.
        # they should be validated against db forcefully every 10 minutes or so

        # Extend the session lifetime only if it's in its second half
        # (save update requests).
        # So it doesn't make sense to call the parameter last_used is it?
        # Whatever. Fix later.

        if not session.is_service:
            if time.time() - session.created > cls.ttl / 2:
                session.last_used = time.time()
                await Redis.set(cls.ns, token, json_dumps(session.dict()))

        return session

    @classmethod
    async def create(
        cls,
        user: UserEntity,
        request: Request | None = None,
        token: str | None = None,
    ) -> SessionModel:
        """Create a new session for a given user."""
        is_service = bool(token)
        if token is None:
            token = create_hash()
        session = SessionModel(
            user=user.dict(),
            token=token,
            created=time.time(),
            last_used=time.time(),
            is_service=is_service,
            client_info=get_client_info(request) if request else None,
        )
        await Redis.set(cls.ns, token, session.json())
        return session

    @classmethod
    async def update(
        cls,
        token: str,
        user: UserEntity,
        client_info: ClientInfo | None = None,
    ) -> None:
        """Update a session with new user data."""
        data = await Redis.get(cls.ns, token)
        if not data:
            # TODO: shouldn't be silent!
            return None

        session = SessionModel(**json_loads(data))
        session.user = user.dict()
        if client_info is not None:
            session.client_info = client_info
        session.last_used = time.time()
        await Redis.set(cls.ns, token, session.json())

    @classmethod
    async def delete(cls, token: str) -> None:
        await Redis.delete(cls.ns, token)

    @classmethod
    async def list(
        cls, user_name: str | None = None
    ) -> AsyncGenerator[SessionModel, None]:
        """List active sessions for all or given user

        Additionally, this function also removes expired sessions
        from the database.
        """

        async for session_id, data in Redis.iterate("session"):
            session = SessionModel(**json_loads(data))
            if cls.is_expired(session):
                logging.info(
                    f"Removing expired session for user"
                    f"{session.user.name} {session.token}"
                )
                await Redis.delete(cls.ns, session.token)
                continue

            if user_name is None or session.user.name == user_name:
                yield session
