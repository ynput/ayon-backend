__all__ = ["router"]

from nxtools import logging
from yaoauth2 import OAuth2Data, YAOAuth2

from ayon_server.auth.session import Session
from ayon_server.config import ayonconfig
from ayon_server.entities import UserEntity
from ayon_server.exceptions import UnauthorizedException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import OPModel


class LoginResponseModel(OPModel):
    detail: str = "Logged in as NAME"
    token: str = "ACCESS_TOKEN"
    user: UserEntity.model.main_model  # type: ignore


async def login_callback(data: OAuth2Data) -> LoginResponseModel:
    res = await Postgres.fetch(
        """
        SELECT * FROM public.users WHERE attrib->>'email' = $1
        """,
        data.user.email,
    )
    if not res:
        # TODO: log the email somewhere safe (event payload)
        raise UnauthorizedException("Attempted login with unknown email")

    user = UserEntity.from_record(res[0])

    # User is authorized, so we may revoke the token again
    # In the future, we may want to store the token in the session
    # and revoke it only when the user logs out.

    if not await oauth2.revoke_token(data.provider, data.access_token):
        logging.warning("Unable to revoke oauth token.")

    session = await Session.create(user)
    return LoginResponseModel(
        detail=f"Logged in as {user.name}", token=session.token, user=session.user
    )


#
# Configure OAuth2 providers
#

oauth2 = YAOAuth2()
oauth2.config.login_callback = login_callback
oauth2.config.login_response_model = LoginResponseModel
oauth2.config.enable_redirect_endpoint = False


if ayonconfig.discord_client_id:
    oauth2.add_provider(
        name="discord",
        client_id=ayonconfig.discord_client_id,
        client_secret=ayonconfig.discord_client_secret,
    )

if ayonconfig.google_client_id:
    oauth2.add_provider(
        name="google",
        client_id=ayonconfig.google_client_id,
        client_secret=ayonconfig.google_client_secret,
    )

#
# Create router
#

router = oauth2.create_router(tags=["Authentication"], prefix="/oauth2")
