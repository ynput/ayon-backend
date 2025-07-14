"""OAuth provider endpoints for AYON Server."""

from typing import Any
from urllib.parse import urlencode

from fastapi import Form, Query, Request
from fastapi.responses import RedirectResponse

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.oauth import JWTTokenManager
from ayon_server.oauth.models import (
    JWTTokenResponse,
    OAuthClient,
    OAuthClientCreate,
    OAuthErrorResponse,
    OAuthIntrospectionResponse,
    OAuthTokenResponse,
    OAuthUserInfoResponse,
)
from ayon_server.oauth.server import OAuthServer
from ayon_server.oauth.storage import OAuthStorage

from .router import router

# Initialize OAuth server
oauth_server = OAuthServer()


@router.get("/clients")
async def list_oauth_clients(current_user: CurrentUser) -> list[OAuthClient]:
    """List active OAuth clients (admin only)."""
    if not current_user.is_admin:
        raise ForbiddenException("Admin access required")

    return await OAuthStorage.get_clients(active=True)


@router.post("/clients")
async def create_oauth_client(
    current_user: CurrentUser,
    client_data: OAuthClientCreate
) -> OAuthClient:
    """Create a new OAuth client (admin only)."""
    if not current_user.is_admin:
        raise ForbiddenException("Admin access required")

    return await OAuthStorage.create_client(client_data)


@router.get("/clients/{client_id}")
async def get_oauth_client(
    current_user: CurrentUser,
    client_id: str
) -> OAuthClient:
    """Get OAuth client by ID (admin only)."""
    if not current_user.is_admin:
        raise ForbiddenException("Admin access required")

    client = await OAuthStorage.get_client(client_id)
    if not client:
        raise NotFoundException("Client not found")

    return client


@router.delete("/clients/{client_id}")
async def delete_oauth_client(
    current_user: CurrentUser,
    client_id: str
) -> EmptyResponse:
    """Delete OAuth client (admin only)."""
    if not current_user.is_admin:
        raise ForbiddenException("Admin access required")

    await OAuthStorage.delete_client(client_id)
    return EmptyResponse()

@router.get("/authorize", response_model=None)
async def authorize_endpoint(
    request: Request,
    current_user: CurrentUser,
    response_type: str = Query(..., description="Response type"),
    client_id: str = Query(..., description="Client ID"),
    redirect_uri: str = Query(None, description="Redirect URI"),
    scope: str = Query("read", description="Requested scope"),
    state: str = Query(None, description="State parameter"),
    code_challenge: str = Query(None, description="PKCE code challenge"),
    code_challenge_method: str = Query(None, description="PKCE method"),
) -> Any:
    """OAuth authorization endpoint."""

    # Validate client
    client = await OAuthStorage.get_client(client_id)
    if not client:
        error_params = {
            "error": "invalid_client",
            "error_description": "Invalid client_id"
        }
        if state:
            error_params["state"] = state
        if redirect_uri:
            return RedirectResponse(
                f"{redirect_uri}?{urlencode(error_params)}"
            )
        raise BadRequestException("Invalid client_id")

    # Validate redirect_uri
    if redirect_uri and redirect_uri not in client.redirect_uris:
        raise BadRequestException("Invalid redirect_uri")

    if not redirect_uri:
        redirect_uri = client.redirect_uris[0] if client.redirect_uris else None

    if not redirect_uri:
        raise BadRequestException("No valid redirect_uri")

    # Validate response_type
    if response_type not in client.response_types:
        error_params = {
            "error": "unsupported_response_type",
            "error_description": f"Response type '{response_type}' not supported"
        }
        if state:
            error_params["state"] = state
        return RedirectResponse(f"{redirect_uri}?{urlencode(error_params)}")

    # If user is not authenticated, redirect to login
    if not current_user:
        # Store authorization request and redirect to login
        login_url = f"/auth/login?next={request.url}"
        return RedirectResponse(login_url)

    # Generate authorization code and redirect
    headers, redirect_url, status = await oauth_server.create_authorization_response(
        uri=str(request.url),
        user_name=current_user.name
    )

    if status == 302:
        return RedirectResponse(redirect_url)
    else:
        # redirect to user consent page
        # TODO: Implement user consent page in frontend
        return RedirectResponse(
            f"/consent?client_name={client.client_name}&"
            f"client_id={client.client_id}&"
            f"response_type={response_type}&"
            f"redirect_uri={redirect_uri}&"
            f"scope={scope}&"
            f"state={state or ''}&"
            f"code_challenge={code_challenge or ''}&"
            f"code_challenge_method={code_challenge_method or ''}"
        )


@router.post("/consent")
async def consent_endpoint(
    request: Request,
    current_user: CurrentUser,
    client_id: str = Form(...),
    response_type: str = Form(...),
    redirect_uri: str = Form(...),
    scope: str = Form("read"),
    state: str = Form(None),
    code_challenge: str = Form(None),
    code_challenge_method: str = Form(None),
    approved: str = Form(...),
) -> RedirectResponse:
    """Handle OAuth consent."""

    if approved.lower() != "true":
        # User denied access
        error_params = {
            "error": "access_denied",
            "error_description": "User denied access"
        }
        if state:
            error_params["state"] = state
        return RedirectResponse(f"{redirect_uri}?{urlencode(error_params)}")

    # User approved, generate authorization code
    auth_url = (
        f"{request.url.scheme}://{request.url.netloc}/oauth/authorize?"
        f"response_type={response_type}&client_id={client_id}&"
        f"redirect_uri={redirect_uri}&scope={scope}"
    )
    if state:
        auth_url += f"&state={state}"
    if code_challenge:
        auth_url += f"&code_challenge={code_challenge}"
    if code_challenge_method:
        auth_url += f"&code_challenge_method={code_challenge_method}"

    headers, redirect_url, status = await oauth_server.create_authorization_response(
        uri=auth_url,
        user_name=current_user.name
    )

    return RedirectResponse(redirect_url)


@router.post("/token")
async def token_endpoint(
    grant_type: str = Form(...),
    code: str = Form(None),
    redirect_uri: str = Form(None),
    client_id: str = Form(None),
    client_secret: str = Form(None),
    refresh_token: str = Form(None),
    scope: str = Form(None),
    code_verifier: str = Form(None),
) -> OAuthTokenResponse | OAuthErrorResponse:
    """OAuth token endpoint."""

    # Create form body for server
    form_data = {
        "grant_type": grant_type,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    if code:
        form_data["code"] = code
    if redirect_uri:
        form_data["redirect_uri"] = redirect_uri
    if refresh_token:
        form_data["refresh_token"] = refresh_token
    if scope:
        form_data["scope"] = scope
    if code_verifier:
        form_data["code_verifier"] = code_verifier

    # Convert to URL-encoded string
    from urllib.parse import urlencode
    body = urlencode({k: v for k, v in form_data.items() if v is not None})

    response_data, response_body, status_code = (
        await oauth_server.create_token_response(uri="", body=body)
    )

    if status_code == 200:
        return OAuthTokenResponse(**response_data)
    else:
        return OAuthErrorResponse(**response_data)


@router.post("/jwt")
async def jwt_token_endpoint(
    current_user: CurrentUser,
    include_id_token: bool = Form(default=False),
    expires_in: int = Form(default=3600),
    audience: str = Form(None),
) -> JWTTokenResponse | OAuthErrorResponse:
    """Generate JWT tokens from OAuth access token.

    This endpoint generates JWT access and ID tokens based on the authenticated user.
    It can be used to provide JWT tokens for clients that require them, such as
    those using OpenID Connect or other JWT-based authentication mechanisms.

    Todo:
        - Implement proper OAuth token validation
        - Handle client_id and scope extraction from OAuth token

    """

    try:
        # This is a placeholder for OAuth token validation.
        client_id = "default"
        scope = "read"

        # Generate JWT access token
        jwt_access_token = JWTTokenManager.create_jwt_access_token(
            user=current_user,
            client_id=client_id,
            scope=scope,
            expires_in=expires_in,
            audience=audience
        )

        # Generate ID token if requested (OpenID Connect)
        jwt_id_token = None
        if include_id_token:
            jwt_id_token = JWTTokenManager.create_jwt_id_token(
                user=current_user,
                client_id=client_id,
                expires_in=expires_in
            )

        return JWTTokenResponse(
            access_token=jwt_access_token,
            id_token=jwt_id_token,
            token_type="Bearer",
            expires_in=expires_in,
            scope=scope
        )

    except Exception as e:
        return OAuthErrorResponse(
            error="server_error",
            error_description=f"Failed to generate JWT token: {str(e)}"
        )


@router.post("/jwt/exchange")
async def jwt_exchange_endpoint(
    request: Request,
    include_id_token: bool = Form(default=False),
    expires_in: int = Form(default=3600),
    audience: str = Form(None),
) -> JWTTokenResponse | OAuthErrorResponse:
    """Exchange OAuth access token for JWT tokens."""

    # Get access token from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return OAuthErrorResponse(
            error="invalid_request",
            error_description="Missing or invalid Authorization header"
        )

    access_token = auth_header[7:]  # Remove "Bearer " prefix

    try:
        # Introspect the OAuth token to get user and client info
        introspection_result = await oauth_server.introspect_token(access_token)

        if not introspection_result.get("active"):
            return OAuthErrorResponse(
                error="invalid_token",
                error_description="Token is not active"
            )

        # Get user information
        username = introspection_result.get("username")
        if not username:
            return OAuthErrorResponse(
                error="invalid_token",
                error_description="Token does not contain user information"
            )

        # Get user entity
        from ayon_server.entities import UserEntity
        user = await UserEntity.load(username)
        if not user:
            return OAuthErrorResponse(
                error="invalid_token",
                error_description="User not found"
            )

        # Extract client and scope information
        client_id = introspection_result.get("client_id", "unknown")
        scope = introspection_result.get("scope", "read")

        # Generate JWT access token
        jwt_access_token = JWTTokenManager.create_jwt_access_token(
            user=user,
            client_id=client_id,
            scope=scope,
            expires_in=expires_in,
            audience=audience
        )

        # Generate ID token if requested (OpenID Connect)
        jwt_id_token = None
        if include_id_token:
            jwt_id_token = JWTTokenManager.create_jwt_id_token(
                user=user,
                client_id=client_id,
                expires_in=expires_in
            )

        return JWTTokenResponse(
            access_token=jwt_access_token,
            id_token=jwt_id_token,
            token_type="Bearer",
            expires_in=expires_in,
            scope=scope
        )

    except Exception as e:
        return OAuthErrorResponse(
            error="server_error",
            error_description=f"Failed to exchange token: {str(e)}"
        )


@router.post("/introspect")
async def introspect_endpoint(
    token: str = Form(...),
    token_type_hint: str = Form(None),
) -> OAuthIntrospectionResponse:
    """OAuth token introspection endpoint."""

    result = await oauth_server.introspect_token(token)
    return OAuthIntrospectionResponse(**result)


@router.get("/userinfo")
async def userinfo_endpoint(current_user: CurrentUser) -> OAuthUserInfoResponse:
    """OAuth user info endpoint."""

    return OAuthUserInfoResponse(
        sub=current_user.name,
        name=current_user.attrib.get("fullName"),
        preferred_username=current_user.name,
        email=current_user.attrib.get("email"),
        email_verified=bool(current_user.attrib.get("email")),
    )

@router.get("/validate")
async def validate_jwt_endpoint(
    token: str = Query(..., description="JWT token to validate")
) -> dict[str, Any]:
    """Validate a JWT token and return its claims."""

    try:
        payload = JWTTokenManager.validate_jwt_access_token(token)
        return {
            "valid": True,
            "claims": payload
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }
