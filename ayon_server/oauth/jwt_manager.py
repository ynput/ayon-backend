"""JWT token utilities for OAuth provider."""

import time
from typing import Any

import jwt

from ayon_server.config import ayonconfig
from ayon_server.entities import UserEntity


class JWTTokenManager:
    """Manages JWT token creation and validation."""

    @staticmethod
    def _get_jwt_secret() -> str:
        """Get JWT signing secret."""
        return ayonconfig.auth_pass_pepper

    @staticmethod
    def _get_issuer() -> str:
        """Get JWT issuer."""
        # Use the server URL as the issuer
        return "ayon-server"

    @classmethod
    def create_jwt_access_token(
        cls,
        user: UserEntity,
        client_id: str,
        scope: str = "read",
        expires_in: int = 3600,
        audience: str | None = None
    ) -> str:
        """Create a JWT access token."""
        now = time.time()

        payload = {
            # Standard JWT claims
            "iss": cls._get_issuer(),  # Issuer
            "sub": user.name,          # Subject (user identifier)
            "aud": audience or client_id,  # Audience (client or resource server)
            "exp": int(now + expires_in),  # Expiration time
            "iat": int(now),           # Issued at
            "jti": f"oauth_{int(now)}_{user.name}",  # JWT ID

            # OAuth-specific claims
            "client_id": client_id,
            "scope": scope,
            "token_type": "access_token",

            # User-specific claims
            "username": user.name,
            "email": user.attrib.email,
            "full_name": user.attrib.fullName,
            "is_admin": user.is_admin,
            "is_manager": user.is_manager,
            "is_service": user.is_service,
            "active": user.active,

            # AYON-specific claims
            "access_groups": user.data.get("accessGroups", {}),
        }

        return jwt.encode(payload, cls._get_jwt_secret(), algorithm="HS256")

    @classmethod
    def create_jwt_id_token(
        cls,
        user: UserEntity,
        client_id: str,
        nonce: str | None = None,
        expires_in: int = 3600
    ) -> str:
        """Create an OpenID Connect ID token."""
        now = time.time()

        payload = {
            # Standard OIDC claims
            "iss": cls._get_issuer(),
            "sub": user.name,
            "aud": client_id,
            "exp": int(now + expires_in),
            "iat": int(now),
            "auth_time": int(now),  # Time when user was authenticated

            # User profile claims
            "name": user.attrib.fullName,
            "preferred_username": user.name,
            "email": user.attrib.email,
            "email_verified": bool(user.attrib.email),
            "updated_at": int(
                user.updated_at.timestamp()) if user.updated_at else int(now),

            # AYON-specific claims
            "is_admin": user.is_admin,
            "is_manager": user.is_manager,
            "is_service": user.is_service,
            "active": user.active,
        }

        if nonce:
            payload["nonce"] = nonce

        return jwt.encode(payload, cls._get_jwt_secret(), algorithm="HS256")

    @classmethod
    def decode_jwt_token(cls, token: str) -> dict[str, Any]:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(
                token,
                cls._get_jwt_secret(),
                algorithms=["HS256"],
                issuer=cls._get_issuer()
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {str(e)}")

    @classmethod
    def validate_jwt_access_token(cls, token: str) -> dict[str, Any]:
        """Validate a JWT access token and return claims."""
        payload = cls.decode_jwt_token(token)

        # Verify it's an access token
        if payload.get("token_type") != "access_token":
            raise ValueError("Not an access token")

        return payload
    @classmethod
    def get_jwks(cls) -> dict[str, Any]:
        """Get JSON Web Key Set for token verification."""
        # For symmetric keys (HS256), we don't expose the key
        # In production, you might want to use asymmetric keys (RS256)
        return {
            "keys": [
                {
                    "kty": "oct",  # Key type: octet sequence (symmetric)
                    "alg": "HS256",  # Algorithm
                    "use": "sig",  # Usage: signature
                    "kid": "ayon-oauth-key-1",  # Key ID
                    # Note: We don't include the actual key for security
                }
            ]
        }
