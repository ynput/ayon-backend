"""OAuth server implementation using oauthlib."""

from typing import Any
from urllib.parse import urlencode, urlparse

from oauthlib.common import Request, generate_token
from oauthlib.oauth2 import RequestValidator, WebApplicationServer
from oauthlib.oauth2.rfc6749.errors import InvalidClientError, OAuth2Error

from ayon_server.auth.utils import hash_password
from ayon_server.entities import UserEntity
from ayon_server.oauth import JWTTokenManager

from .storage import OAuthStorage


class AyonOAuthRequestValidator(RequestValidator):
    """OAuth request validator for AYON server."""

    def authenticate_client(self, request: Request, *args, **kwargs) -> bool:
        """Authenticate the client."""
        if not request.client_id:
            return False

        client = None
        if hasattr(request, '_client'):
            client = request._client
        else:
            # This will be handled in validate_client_id
            pass

        if not client:
            return False

        # For public clients, no secret is required
        if client.client_type == "public":
            return True

        # For confidential clients, check the secret
        if not request.client_secret:
            return False

        # Verify client secret
        hashed_secret = hash_password(request.client_secret)
        return client.client_secret == hashed_secret

    def client_authentication_required(
            self, request: Request, *args, **kwargs) -> bool:
        """Check if client authentication is required."""
        # Authentication is required for confidential clients
        if hasattr(request, '_client') and request._client:
            return request._client.client_type == "confidential"
        return True

    def get_default_scopes(
            self, client_id: str, request, *args, **kwargs) -> list[str]:
        """Get default scopes for client."""
        return ["read"]

    def get_default_redirect_uri(
            self, client_id: str, request) -> str | None:
        """Get default redirect URI for client.

        Args:
            client_id (str): The ID of the OAuth client.
            request: The request object containing client information.

        Returns:
            str | None: The default redirect URI if available, otherwise None.

        """
        if hasattr(request, '_client') and request._client:
            if request._client.redirect_uris:
                return request._client.redirect_uris[0]
        return None

    def invalidate_authorization_code(
            self, client_id: str, code: str, request, *args, **kwargs) -> None:
        """Invalidate authorization code.

        This is already handled in get_authorization_code()

        """
        pass

    def revoke_token(
            self, token: str, request: Request, *args, **kwargs) -> None:
        """Revoke a token."""

        # Try to revoke as access token
        # Try to revoke as refresh token
        pass  # This will be implemented based on token type

    def save_authorization_code(
            self, client_id: str, code: dict, request, *args, **kwargs) -> None:
        """Save authorization code."""
        # This is handled in the authorization endpoint
        pass

    def save_bearer_token(self, token: dict, request, *args, **kwargs) -> None:
        """Save bearer token."""
        # This is handled in the token endpoint
        pass

    def validate_bearer_token(self, token: str, scopes: list[str], request) -> bool:
        """Validate bearer token."""
        # This will be called during token introspection
        return False  # Implemented separately

    def validate_client_id(self, client_id: str, request, *args, **kwargs) -> bool:
        """Validate client ID."""
        # Store client for later use
        if not hasattr(request, '_client') or not request._client:
            return False
        return request._client.is_active

    def validate_code(
            self, client_id: str, code: str, client, request, *args, **kwargs) -> bool:
        """Validate authorization code."""
        # This will be handled in get_authorization_code
        return True

    def validate_grant_type(
            self, client_id: str, grant_type: str,
            client, request, *args, **kwargs) -> bool:
        """Validate grant type."""
        if hasattr(request, '_client') and request._client:
            return grant_type in request._client.grant_types
        return False

    def validate_redirect_uri(
            self, client_id: str, redirect_uri: str,
            request, *args, **kwargs) -> bool:
        """Validate redirect URI."""
        if hasattr(request, '_client') and request._client:
            return redirect_uri in request._client.redirect_uris
        return False

    def validate_response_type(
            self, client_id: str, response_type: str,
            client, request, *args, **kwargs) -> bool:
        """Validate response type."""
        if hasattr(request, '_client') and request._client:
            return response_type in request._client.response_types
        return False

    def validate_scopes(
            self, client_id: str, scopes: list[str], client,
            request, *args, **kwargs) -> bool:
        """Validate scopes."""
        # For now, allow all requested scopes
        return True

    def validate_user(
            self, username: str,
            password: str, client, request, *args, **kwargs) -> bool:
        """Validate user credentials (for password grant)."""
        # This would use the existing password authentication
        return False  # Not implemented for security reasons

    def get_authorization_code(
            self, client_id: str, code: str,
            redirect_uri: str, request) -> dict[str, Any] | None:
        """Get authorization code."""
        # This will be implemented async in the main server
        return None


class OAuthServer:
    """OAuth server implementation."""

    def __init__(self):
        self.validator = AyonOAuthRequestValidator()
        self.server = WebApplicationServer(self.validator)

    async def create_authorization_response(
        self,
        uri: str,
        http_method: str = "GET",
        body: str | None = None,
        headers: dict[str, str] | None = None,
        scopes: list[str] | None = None,
        user_name: str | None = None
    ) -> tuple[dict[str, str], str, int]:
        """Create authorization response."""
        try:
            # Pre-populate client data
            parsed_uri = urlparse(uri)
            from urllib.parse import parse_qs
            query_params = parse_qs(parsed_uri.query)

            client_id = query_params.get('client_id', [None])[0]
            if client_id:
                client = await OAuthStorage.get_client(client_id)
                if client:
                    # Create a mock request object to store client
                    class MockRequest:
                        def __init__(self):
                            self._client = client
                            self.client_id = client_id

                    # Store client for validator
                    self.validator._current_client = client
                else:
                    raise InvalidClientError("Invalid client_id")

            # If user is authenticated, generate code
            if user_name:
                code = generate_token()
                redirect_uri = query_params.get('redirect_uri', [None])[0]
                scope = query_params.get('scope', ['read'])[0]

                # Save authorization code
                await OAuthStorage.save_authorization_code(
                    code=code,
                    client_id=client_id,
                    user_name=user_name,
                    redirect_uri=redirect_uri,
                    scope=scope
                )

                # Build redirect response
                state = query_params.get('state', [None])[0]
                response_params = {"code": code}
                if state:
                    response_params["state"] = state

                redirect_url = f"{redirect_uri}?{urlencode(response_params)}"
                return {}, redirect_url, 302

            # Return authorization page
            return {}, "", 200

        except OAuth2Error as e:
            return {"error": str(e)}, "", 400

    async def create_token_response(
        self,
        uri: str,
        http_method: str = "POST",
        body: str | None = None,
        headers: dict[str, str] | None = None
    ) -> tuple[dict[str, Any], str, int]:
        """Create token response."""
        try:
            # Parse form data
            from urllib.parse import parse_qs
            if body:
                form_data = parse_qs(body)
            else:
                form_data = {}

            grant_type = form_data.get('grant_type', [None])[0]
            # client_id = form_data.get('client_id', [None])[0]

            if grant_type == "authorization_code":
                return await self._handle_authorization_code_grant(form_data)
            elif grant_type == "refresh_token":
                return await self._handle_refresh_token_grant(form_data)
            else:
                return {"error": "unsupported_grant_type"}, "", 400

        except Exception as e:
            return {
                "error": "server_error",
                "error_description": str(e)}, "", 500

    async def _handle_authorization_code_grant(
            self, form_data: dict) -> tuple[dict[str, Any], str, int]:
        """Handle authorization code grant."""
        code = form_data.get('code', [None])[0]
        client_id = form_data.get('client_id', [None])[0]
        redirect_uri = form_data.get('redirect_uri', [None])[0]

        if not code or not client_id:
            return {"error": "invalid_request"}, "", 400

        # Verify client
        client = await OAuthStorage.get_client(client_id)
        if not client:
            return {"error": "invalid_client"}, "", 400

        # Get authorization code
        auth_code = await OAuthStorage.get_authorization_code(code)
        if not auth_code:
            return {"error": "invalid_grant"}, "", 400

        # Verify client matches
        if auth_code["client_id"] != client_id:
            return {"error": "invalid_grant"}, "", 400

        # Verify redirect URI if provided
        if redirect_uri and auth_code.get("redirect_uri") != redirect_uri:
            return {"error": "invalid_grant"}, "", 400

        # Generate tokens
        access_token = generate_token()
        refresh_token = generate_token()
        expires_in = 3600  # 1 hour

        # Save tokens
        await OAuthStorage.save_access_token(
            access_token=access_token,
            client_id=client_id,
            user_name=auth_code["user_name"],
            scope=auth_code.get("scope"),
            expires_in=expires_in
        )

        await OAuthStorage.save_refresh_token(
            refresh_token=refresh_token,
            access_token=access_token,
            client_id=client_id,
            user_name=auth_code["user_name"],
            scope=auth_code.get("scope")
        )

        response = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "refresh_token": refresh_token,
            "scope": auth_code.get("scope", "read")
        }

        # Optionally add JWT tokens if requested
        # This could be controlled by a scope like "jwt" or client configuration
        scope = auth_code.get("scope", "read")
        if "jwt" in scope or "openid" in scope:
            try:
                # Get user entity for JWT creation
                user = await UserEntity.load(auth_code["user_name"])
                if user:
                    # Add JWT access token
                    jwt_access_token = JWTTokenManager.create_jwt_access_token(
                        user=user,
                        client_id=client_id,
                        scope=scope,
                        expires_in=expires_in
                    )
                    response["jwt_access_token"] = jwt_access_token

                    # Add ID token for OpenID Connect
                    if "openid" in scope:
                        id_token = JWTTokenManager.create_jwt_id_token(
                            user=user,
                            client_id=client_id,
                            expires_in=expires_in
                        )
                        response["id_token"] = id_token
            except Exception:
                # JWT creation failed, but continue with regular OAuth tokens
                pass

        return response, "", 200

    async def _handle_refresh_token_grant(
            self, form_data: dict) -> tuple[dict[str, Any], str, int]:
        """Handle refresh token grant."""
        refresh_token = form_data.get('refresh_token', [None])[0]
        client_id = form_data.get('client_id', [None])[0]

        if not refresh_token or not client_id:
            return {"error": "invalid_request"}, "", 400

        # Get refresh token data
        token_data = await OAuthStorage.get_refresh_token(refresh_token)
        if not token_data:
            return {"error": "invalid_grant"}, "", 400

        # Verify client
        if token_data["client_id"] != client_id:
            return {"error": "invalid_grant"}, "", 400

        # Generate new access token
        access_token = generate_token()
        expires_in = 3600  # 1 hour

        # Save new access token
        await OAuthStorage.save_access_token(
            access_token=access_token,
            client_id=client_id,
            user_name=token_data["user_name"],
            scope=token_data.get("scope"),
            expires_in=expires_in
        )

        response = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "scope": token_data.get("scope", "read")
        }

        # Optionally add JWT tokens if requested
        scope = token_data.get("scope", "read")
        if "jwt" in scope or "openid" in scope:
            try:
                # Get user entity for JWT creation
                user = await UserEntity.load(token_data["user_name"])
                if user:
                    # Add JWT access token
                    jwt_access_token = JWTTokenManager.create_jwt_access_token(
                        user=user,
                        client_id=client_id,
                        scope=scope,
                        expires_in=expires_in
                    )
                    response["jwt_access_token"] = jwt_access_token

                    # Add ID token for OpenID Connect
                    if "openid" in scope:
                        id_token = JWTTokenManager.create_jwt_id_token(
                            user=user,
                            client_id=client_id,
                            expires_in=expires_in
                        )
                        response["id_token"] = id_token
            except Exception:
                # JWT creation failed, but continue with regular OAuth tokens
                pass

        return response, "", 200

    async def introspect_token(self, token: str) -> dict[str, Any]:
        """Introspect a token."""
        token_data = await OAuthStorage.get_access_token(token)

        if not token_data:
            return {"active": False}

        return {
            "active": True,
            "client_id": token_data["client_id"],
            "username": token_data["user_name"],
            "scope": token_data.get("scope", "read"),
            "token_type": "Bearer",
            "exp": int(token_data["expires_at"]),
            "iat": int(token_data["created_at"]),
            "sub": token_data["user_name"]
        }
