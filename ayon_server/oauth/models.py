"""OAuth models for AYON Server OAuth provider implementation."""
from datetime import datetime

from pydantic import Field

from ayon_server.types import OPModel


class OAuthClient(OPModel):
    """OAuth client model."""
    client_id: str = Field(..., description="Unique client identifier")
    client_secret: str | None = Field(None, description="Client secret (hashed)")
    client_name: str = Field(..., description="Human-readable client name")
    redirect_uris: list[str] = Field(
        default_factory=list, description="Allowed redirect URIs"
    )
    grant_types: list[str] = Field(
        default_factory=lambda: ["authorization_code", "refresh_token"],
        description="Allowed grant types"
    )
    response_types: list[str] = Field(
        default_factory=lambda: ["code"],
        description="Allowed response types"
    )
    scope: str = Field(default="read", description="Default scope")
    client_type: str = Field(
        default="confidential", description="Client type (public/confidential)"
    )
    is_active: bool = Field(default=True, description="Whether client is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class OAuthClientCreate(OPModel):
    """Model for creating OAuth clients."""
    client_name: str = Field(..., description="Human-readable client name")
    redirect_uris: list[str] = Field(..., description="Allowed redirect URIs")
    grant_types: list[str] = Field(
        default_factory=lambda: ["authorization_code", "refresh_token"],
        description="Allowed grant types"
    )
    response_types: list[str] = Field(
        default_factory=lambda: ["code"],
        description="Allowed response types"
    )
    scope: str = Field(default="read", description="Default scope")
    client_type: str = Field(
        default="confidential", description="Client type (public/confidential)"
    )


class OAuthTokenResponse(OPModel):
    """OAuth token response model."""
    access_token: str = Field(..., description="Access token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int | None = Field(None, description="Token expiration in seconds")
    refresh_token: str | None = Field(None, description="Refresh token")
    scope: str | None = Field(None, description="Granted scope")


class OAuthErrorResponse(OPModel):
    """OAuth error response model."""
    error: str = Field(..., description="Error code")
    error_description: str | None = Field(None, description="Error description")
    error_uri: str | None = Field(None, description="Error URI")
    state: str | None = Field(None, description="State parameter")


class OAuthIntrospectionResponse(OPModel):
    """OAuth token introspection response model."""
    active: bool = Field(..., description="Whether token is active")
    scope: str | None = Field(None, description="Token scope")
    client_id: str | None = Field(None, description="Client identifier")
    username: str | None = Field(None, description="Username")
    token_type: str | None = Field(None, description="Token type")
    exp: int | None = Field(None, description="Expiration timestamp")
    iat: int | None = Field(None, description="Issued at timestamp")
    sub: str | None = Field(None, description="Subject")


class OAuthUserInfoResponse(OPModel):
    """OAuth user info response model."""
    sub: str = Field(..., description="Subject identifier")
    name: str | None = Field(None, description="Full name")
    preferred_username: str | None = Field(None, description="Preferred username")
    email: str | None = Field(None, description="Email address")
    email_verified: bool | None = Field(None, description="Whether email is verified")


class OAuthConsentRequest(OPModel):
    """OAuth consent request model."""
    client_id: str = Field(..., description="Client identifier")
    scope: str | None = Field(None, description="Requested scope")
    approved: bool = Field(..., description="Whether user approved the request")


class JWTTokenResponse(OPModel):
    """JWT token response model."""
    access_token: str = Field(..., description="JWT access token")
    id_token: str | None = Field(None, description="JWT ID token (OIDC)")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(default=3600, description="Token expiration in seconds")
    scope: str = Field(default="read", description="Token scope")


class JWTTokenRequest(OPModel):
    """JWT token request model."""
    token_type: str = Field(
        default="access_token", description="Type of JWT token to generate"
    )
    include_id_token: bool = Field(
        default=False, description="Whether to include ID token"
    )
    expires_in: int = Field(
        default=3600, description="Token expiration in seconds"
    )
    audience: str | None = Field(None, description="Token audience")
