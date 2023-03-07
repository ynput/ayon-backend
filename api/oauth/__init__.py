__all__ = ["router"]

from typing import Any

import httpx
from nxtools import logging, slugify
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


async def check_discord_data(data: OAuth2Data) -> dict[str, Any]:
    result: dict[str, Any] = {}

    if ayonconfig.discord_guilds is not None:
        valid_guilds = [guild.strip() for guild in ayonconfig.discord_guilds.split(",")]

        async with httpx.AsyncClient() as client:
            client.headers["Authorization"] = f"Bearer {data.access_token}"
            res = await client.get("https://discord.com/api/users/@me/guilds")
            res.raise_for_status()
            guilds = res.json()

        # check if user is in any of the guilds
        for guild in guilds:
            if guild["id"] in valid_guilds:
                if "discordGuilds" not in result:
                    result["discordGuilds"] = []
                result["discordGuilds"] = guild

        if not result.get("discordGuilds"):
            if not await oauth2.revoke_token(data.provider, data.access_token):
                logging.warning("Unable to revoke oauth token.")
            raise UnauthorizedException("You are not in any of the required guilds")

    async with httpx.AsyncClient() as client:
        client.headers["Authorization"] = f"Bearer {data.access_token}"
        res = await client.get("https://discord.com/api/users/@me")
        res.raise_for_status()
        profile = res.json()

    result["discordProfile"] = profile

    return result


async def login_callback(data: OAuth2Data) -> LoginResponseModel:

    if data.provider == "discord":
        ex_data = await check_discord_data(data)

        user_name = ex_data["discordProfile"]["username"]
        user_discriminator = ex_data["discordProfile"]["discriminator"]

        avatar_url = "https://cdn.discordapp.com/avatars/"
        avatar_url += ex_data["discordProfile"]["id"]
        avatar_url += f"/{ex_data['discordProfile']['avatar']}.png"

        user_name = slugify(user_name, separator=".")
        ex_name = f"{user_name}.{user_discriminator}"
        ex_attrib = {
            "fullName": user_name,
            "email": ex_data["discordProfile"]["email"],
            "avatarUrl": avatar_url,
        }

    else:
        ex_data = {}
        ex_name = None
        ex_attrib = None

    res = await Postgres.fetch(
        "SELECT * FROM public.users WHERE attrib->>'email' = $1",
        data.user.email,
    )
    if not res:

        if ayonconfig.oauth_create_users:

            nroles = ayonconfig.oauth_create_users.split(",")
            nroles = [role.strip() for role in nroles]
            if "admin" in nroles:
                ex_data["isAdmin"] = True
            if "manager" in nroles:
                ex_data["isManager"] = True
            if "guest" in nroles:
                ex_data["isGuest"] = True

            user = UserEntity(
                payload={
                    "name": ex_name,
                    "attrib": ex_attrib,
                    "data": ex_data,
                }
            )

            await user.save()

        else:
            # TODO: log the email somewhere safe (event payload)
            if not await oauth2.revoke_token(data.provider, data.access_token):
                logging.warning("Unable to revoke oauth token.")
            raise UnauthorizedException("Attempted login with unknown email")

    else:
        user = UserEntity.from_record(res[0])

        # Update the user data with the new data from the provider
        if ex_data:
            user.data.update(ex_data)

        if ex_attrib:
            attrib = user.payload.attrib.dict()
            attrib.update(ex_attrib)
            user.payload.attrib = UserEntity.model.attrib_model(**attrib)
        if ex_data or ex_attrib:
            await user.save()

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
        additional_scopes=["guilds"],
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
