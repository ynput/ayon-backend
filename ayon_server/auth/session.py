__all__ = ["Session"]

import asyncio
import secrets
import time
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Request

from ayon_server.api.clientinfo import ClientInfo, get_client_info
from ayon_server.config import ayonconfig
from ayon_server.entities import UserEntity
from ayon_server.entities.models.user import UserModel
from ayon_server.events import EventStream
from ayon_server.exceptions import UnauthorizedException
from ayon_server.helpers.auth_utils import AuthUtils
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.models.attrib_values import STORED_VALUES_CONTEXT
from ayon_server.types import OPModel
from ayon_server.utils import create_background_task, json_loads
from ayon_server.utils.server import get_real_ip_from_request, is_internal_ip


def is_local_ip(ip: str) -> bool:
    # Deprecated, but still used for backward compatibility.
    return is_internal_ip(ip)


class DelegatedAccess(OPModel):
    """Access an application was given to act as the user.

    A session with delegated access differs from a login:

    - it is not bound to the IP address of its client: applications run
      anywhere and change addresses,
    - it ends at `expires`, however much it is used,
    - with `paths` set, it is accepted only for requests to these paths
      and below them (and not by the websocket); a `*` stands for any
      one segment, as in `/api/addons/mcp/*/mcp`,
    - it does not count towards the limit of concurrent sessions and is
      not reported as a login or a logout.

    `scope` is what the user approved, for whoever issued the session:
    the server itself does not interpret it.
    """

    client_id: str
    client_name: str
    expires: float
    paths: list[str] | None = None
    scope: str | None = None

    def allows_path(self, path: str) -> bool:
        if self.paths is None:
            return True
        segments = path.split("/")
        for allowed in self.paths:
            pattern = allowed.rstrip("/").split("/")
            if len(segments) < len(pattern):
                continue
            if all(p in ("*", s) for p, s in zip(pattern, segments)):
                return True
        return False

    @property
    def remaining(self) -> int:
        """Seconds until the end, for the lifetime of the stored session."""
        return max(int(self.expires - time.time()) + 1, 1)


class SessionModel(OPModel):
    user: UserModel
    token: str
    created: float = 0
    last_used: float = 0
    is_service: bool = False
    is_api_key: bool = False
    client_info: ClientInfo | None = None
    delegated: DelegatedAccess | None = None

    @property
    def user_entity(self) -> UserEntity:
        return UserEntity(
            payload=self.user.model_dump(),
            exists=True,
        )

    @property
    def ttl(self) -> int:
        return 600 if self.is_service else ayonconfig.session_ttl

    @property
    def is_expired(self) -> bool:
        if self.delegated:
            return time.time() > self.delegated.expires
        return time.time() - self.last_used > self.ttl


class Session:
    ns = "session"

    @classmethod
    async def store(cls, session: SessionModel) -> None:
        """Store the session. A delegated one is dropped at its end."""
        ttl = session.delegated.remaining if session.delegated else 0
        await Redis.set(cls.ns, session.token, session.model_dump_json(), ttl=ttl)

    @classmethod
    def is_expired(cls, session: SessionModel) -> bool:
        return session.is_expired

    @classmethod
    async def check(cls, token: str, request: Request | None) -> SessionModel | None:
        """Return a session corresponding to a given access token.

        Return None if the token is invalid.
        If the session is expired, it will be removed from the database.
        If it's not expired, update the last_used field and extend
        its lifetime.
        """
        data = await Redis.get_json(cls.ns, token)
        if not data:
            logger.trace(f"Session {token} not found")
            return None

        if data.get("isInvalid", False):
            # if a session is marked as invalid, raise Unauthorized immediately
            # without giving the user a chance to refresh the token.
            await asyncio.sleep(0.2)
            raise UnauthorizedException("Invalid session")

        # Cached user attributes are not validated again: they may not match
        # changed attribute definitions until the session is refreshed
        session = SessionModel.model_validate(data, context=STORED_VALUES_CONTEXT)

        if session.is_expired:
            await cls.delete(token, "Session expired")
            return None

        if request and not session.delegated:
            if not session.client_info:
                session.client_info = get_client_info(request)
                session.last_used = time.time()
                await cls.store(session)
            else:
                if not ayonconfig.disable_check_session_ip:
                    real_ip = get_real_ip_from_request(request)
                    if not is_internal_ip(real_ip):
                        if session.client_info.ip != real_ip:
                            r = f"Stored: {session.client_info.ip}, current: {real_ip}"
                            await cls.delete(token, f"Client IP mismatch: {r}")
                            return None

                # Site ID change refreshes client metadata,
                # but must never rebind the session to a new IP
                site_id = request.headers.get("x-ayon-site-id")
                if session.client_info.site_id != site_id:
                    client_info = get_client_info(request)
                    client_info.ip = session.client_info.ip
                    client_info.location = session.client_info.location
                    session.client_info = client_info
                    session.last_used = time.time()
                    await cls.store(session)

        # extend normal tokens validity, but not service tokens.
        # they should be validated against db forcefully every 10 minutes or so
        # (a delegated session records the use, but still ends at its time)

        if not session.is_service:
            remaining_ttl = ayonconfig.session_ttl - (time.time() - session.last_used)
            if remaining_ttl < ayonconfig.session_ttl - 120:
                session.last_used = time.time()
                try:
                    await cls.on_extend(session)
                except UnauthorizedException as e:
                    await cls.delete(token, f"Session extension failed: {e}")
                    return None
                await cls.store(session)

        return session

    @classmethod
    async def on_extend(cls, session: SessionModel) -> None:
        pass

    @classmethod
    async def mark_invalid(cls, token: str) -> None:
        """Mark a session as invalid without deleting it.

        This is used to cache invalid API keys and prevent repeated
        database lookups for them.
        """
        data = {"isInvalid": True}
        await Redis.set_json(cls.ns, token, data, ttl=60)

    @classmethod
    async def create(
        cls,
        user: UserEntity,
        request: Request | None = None,
        token: str | None = None,
        message: str = "User logged in",
        event_payload: dict[str, Any] | None = None,
        is_api_key: bool = False,
        delegated: DelegatedAccess | None = None,
    ) -> SessionModel:
        """Create a new session for a given user.

        With `delegated`, the session is for an application acting as
        the user (see DelegatedAccess). Whoever creates it reports it:
        no login event is dispatched.
        """
        if delegated and (token or is_api_key):
            raise ValueError("Delegated session cannot use a given token")
        is_service = bool(token)
        if token is None:
            token = secrets.token_hex(32)
        client_info = get_client_info(request) if request and not delegated else None

        if user.exists and not user.data.get("isGuest", False):
            await AuthUtils.ensure_can_login(user, client_info)

        session = SessionModel(
            user=user.dict(),
            token=token,
            created=time.time(),
            last_used=time.time(),
            is_service=is_service,
            is_api_key=is_api_key,
            client_info=client_info,
            delegated=delegated,
        )
        event_summary = client_info.model_dump() if client_info else {}
        await cls.store(session)
        if delegated:
            return session

        if not user.is_service:
            await EventStream.dispatch(
                "auth.login",
                description=message,
                user=user.name,
                summary=event_summary,
                payload=event_payload,
            )

        # invalidate least used session if user reached the limit
        # as a background task

        if not user.is_service:
            create_background_task(cls.invalidate_least_used(user.name))

        if user.data.get("inviteRequest"):
            del user.data["inviteRequest"]
            user.data["inviteAcceptedAt"] = time.time()
            await user.save()

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
            logger.trace(f"Trying to update non-existing session {token}")
            return None

        session = SessionModel(**json_loads(data))
        session.user = user._payload.model_copy()
        if client_info is not None:
            session.client_info = client_info
        session.last_used = time.time()
        await cls.store(session)

    @classmethod
    async def delete(cls, token: str, message: str = "User logged out") -> None:
        data = await Redis.get(cls.ns, token)
        if data:
            session = SessionModel(**json_loads(data))
            if not session.is_api_key and not session.delegated:
                await EventStream.dispatch(
                    "auth.logout",
                    summary={"token": token},
                    description=message,
                    user=session.user.name,
                )
        await Redis.delete(cls.ns, token)

    @classmethod
    async def list(
        cls,
        user_name: str | None = None,
    ) -> AsyncGenerator[SessionModel]:
        """List active sessions for all or given user

        Additionally, this function also removes expired sessions
        from the database.
        """

        async for _, data in Redis.iterate("session"):
            if data is None:
                continue  # this should never happen, but keeps mypy happy

            payload = json_loads(data)
            if payload.get("isInvalid", False):
                # skip invalid sessions
                continue
            session = SessionModel(**payload)
            if cls.is_expired(session):
                await cls.delete(session.token, message="Session expired")
                continue

            if user_name is None or session.user.name == user_name:
                yield session

    @classmethod
    async def invalidate_least_used(cls, user_name: str) -> None:
        """
        Check whether the user reached the limit set in the configuration
        and invalidate the least used sessions.
        """

        max_sessions = ayonconfig.max_concurent_user_sessions
        if not max_sessions:
            # 0 or None means no limit
            return

        sessions = []
        async for session in cls.list(user_name):
            if session.is_api_key or session.delegated:
                continue
            sessions.append(session)

        if len(sessions) <= max_sessions:
            return

        sessions.sort(key=lambda s: s.last_used)
        for session in sessions[: len(sessions) - max_sessions]:
            msg = "Too many concurrent sessions"
            await cls.delete(session.token, message=msg)

            msg += f" ({user_name} {session.token})"
            logger.debug(msg)

    @classmethod
    async def logout_user(cls, user_name: str, message: str | None = None) -> None:
        """Logout all user sessions."""
        logged_out = False
        async for session in cls.list(user_name):
            token = session.token
            await Redis.delete(cls.ns, token)
            logged_out = True

        if logged_out:
            message = message or f"User {user_name} logged out from all sessions"
            await EventStream.dispatch(
                "auth.logout",
                description=message,
                user=user_name,
            )

    @classmethod
    async def user_save_hook(cls, user: UserEntity, *args) -> None:
        """This is called when user is saved.

        Update all user sessions with new user data. If user was deactivated,
        log them out.
        """

        try:
            await AuthUtils.ensure_can_login(user, post_save=True)
        except UnauthorizedException as e:
            logger.trace(f"User cannot log in after save: {e}")
            await cls.logout_user(user.name)
        else:
            logger.trace(f"Updating user {user.name} sessions after save")
            async for session in Session.list(user.name):
                if session.is_service:
                    await Session.delete(session.token, message="Service session reset")
                else:
                    await Session.update(session.token, user)


UserEntity.save_hooks.append(Session.user_save_hook)
