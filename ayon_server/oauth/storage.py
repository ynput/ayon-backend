"""OAuth storage implementation using PostgreSQL and Redis."""

import time
from typing import Any

from ayon_server.auth.utils import hash_password
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.utils import create_hash, create_uuid

from .models import OAuthClient, OAuthClientCreate


class OAuthStorage:
    """OAuth storage implementation."""

    @staticmethod
    async def get_client(client_id: str, active: bool = True) -> OAuthClient | None:
        """Get OAuth client by ID.

        Args:
            client_id (str): The ID of the OAuth client.
            active (bool): Whether to filter by active clients only. Defaults to True.

        Returns:
            OAuthClient | None: The OAuth client if found, otherwise None.

        """
        query = """
        SELECT client_id, client_secret, client_name, redirect_uris,
               grant_types, response_types, scope, client_type,
               is_active, created_at, updated_at
        FROM oauth_clients
        WHERE client_id = $1 AND is_active = $2
        """
        result = await Postgres.fetch(query, client_id, active)
        if not result:
            return None

        return OAuthClient(**result[0])

    @staticmethod
    async def get_clients(active: bool = True) -> list[OAuthClient]:
        """Get all active OAuth clients.

        Args:
            active (bool): Whether to filter by active clients only. Defaults to True.

        Returns:
            list[OAuthClient]: List of OAuth clients.

        """
        query = """
        SELECT client_id, client_secret, client_name, redirect_uris,
               grant_types, response_types, scope, client_type,
               is_active, created_at, updated_at
        FROM oauth_clients
        WHERE is_active = $1
        """
        results = await Postgres.fetch(query, active)
        return [OAuthClient(**row) for row in results] if results else []

    @staticmethod
    async def create_client(client_data: OAuthClientCreate) -> OAuthClient:
        """Create a new OAuth client."""
        client_id = create_uuid()
        client_secret = create_hash()
        hashed_secret = hash_password(client_secret)
        now = time.time()

        client = OAuthClient(
            client_id=client_id,
            client_secret=hashed_secret,
            client_name=client_data.client_name,
            redirect_uris=client_data.redirect_uris,
            grant_types=client_data.grant_types,
            response_types=client_data.response_types,
            scope=client_data.scope,
            client_type=client_data.client_type,
            is_active=True,
            created_at=now,
            updated_at=now
        )

        query = """
        INSERT INTO oauth_clients (
            client_id, client_secret, client_name, redirect_uris,
            grant_types, response_types, scope, client_type,
            is_active, created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """

        await Postgres.execute(
            query,
            client.client_id,
            client.client_secret,
            client.client_name,
            client.redirect_uris,
            client.grant_types,
            client.response_types,
            client.scope,
            client.client_type,
            client.is_active,
            client.created_at,
            client.updated_at
        )

        # Return client with plain secret for initial response
        result_client = client.copy()
        result_client.client_secret = client_secret
        return result_client

    @staticmethod
    async def delete_client(client_id: str) -> None:
        """Delete an OAuth client by ID.

        Args:
            client_id (str): The ID of the OAuth client to delete.

        """
        query = "DELETE FROM oauth_clients WHERE client_id = $1"
        await Postgres.execute(query, client_id)

    @staticmethod
    async def save_authorization_code(
        code: str,
        client_id: str,
        user_name: str,
        redirect_uri: str | None = None,
        scope: str | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        expires_in: int = 600  # 10 minutes
    ) -> None:
        """Save authorization code to Redis."""
        data = {
            "client_id": client_id,
            "user_name": user_name,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "created_at": time.time(),
            "expires_at": time.time() + expires_in
        }
        await Redis.set_json("oauth_codes", code, data, ttl=expires_in)

    @staticmethod
    async def get_authorization_code(code: str) -> dict[str, Any] | None:
        """Get and consume authorization code from Redis."""
        data = await Redis.get_json("oauth_codes", code)
        if data:
            # Delete the code after retrieving (single use)
            await Redis.delete("oauth_codes", code)

            # Check if expired
            if time.time() > data.get("expires_at", 0):
                return None

        return data

    @staticmethod
    async def save_access_token(
        access_token: str,
        client_id: str,
        user_name: str,
        scope: str | None = None,
        expires_in: int = 3600  # 1 hour
    ) -> None:
        """Save access token to Redis."""
        data = {
            "client_id": client_id,
            "user_name": user_name,
            "scope": scope,
            "token_type": "Bearer",
            "created_at": time.time(),
            "expires_at": time.time() + expires_in
        }
        await Redis.set_json("oauth_tokens", access_token, data, ttl=expires_in)

    @staticmethod
    async def get_access_token(access_token: str) -> dict[str, Any] | None:
        """Get access token from Redis."""
        data = await Redis.get_json("oauth_tokens", access_token)
        if data:
            # Check if expired
            if time.time() > data.get("expires_at", 0):
                await Redis.delete("oauth_tokens", access_token)
                return None
        return data

    @staticmethod
    async def save_refresh_token(
        refresh_token: str,
        access_token: str,
        client_id: str,
        user_name: str,
        scope: str | None = None,
        expires_in: int | None = None  # Refresh tokens can be long-lived
    ) -> None:
        """Save refresh token to Redis."""
        data = {
            "access_token": access_token,
            "client_id": client_id,
            "user_name": user_name,
            "scope": scope,
            "created_at": time.time()
        }

        if expires_in:
            data["expires_at"] = time.time() + expires_in

        ttl = expires_in if expires_in else None
        await Redis.set_json("oauth_refresh_tokens", refresh_token, data, ttl=ttl)

    @staticmethod
    async def get_refresh_token(refresh_token: str) -> dict[str, Any] | None:
        """Get refresh token from Redis."""
        data = await Redis.get_json("oauth_refresh_tokens", refresh_token)
        if data:
            # Check if expired (if expiration is set)
            expires_at = data.get("expires_at")
            if expires_at and time.time() > expires_at:
                await Redis.delete("oauth_refresh_tokens", refresh_token)
                return None
        return data

    @staticmethod
    async def revoke_refresh_token(refresh_token: str) -> None:
        """Revoke a refresh token."""
        await Redis.delete("oauth_refresh_tokens", refresh_token)

    @staticmethod
    async def revoke_access_token(access_token: str) -> None:
        """Revoke an access token."""
        await Redis.delete("oauth_tokens", access_token)
