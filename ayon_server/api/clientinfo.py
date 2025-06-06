import contextlib
import ipaddress
import os

import geoip2
import geoip2.database
import user_agents
from fastapi import Request
from pydantic import BaseModel, Field

from ayon_server.config import ayonconfig


class LocationInfo(BaseModel):
    country: str | None = Field(None, title="Country")
    subdivision: str | None = Field(None, title="Subdivision")
    city: str | None = Field(None, title="City")


class AgentInfo(BaseModel):
    platform: str | None = Field(None, title="Platform")
    client: str | None = Field(None, title="Client")
    device: str | None = Field(None, title="Device")


class ClientInfo(BaseModel):
    ip: str
    languages: list[str] = Field(default_factory=list)
    location: LocationInfo | None = Field(None)
    agent: AgentInfo | None = Field(None)
    site_id: str | None = Field(None)


def get_real_ip(request: Request) -> str:
    if request.client is None:
        return "0.0.0.0"
    xff = request.headers.get("x-forwarded-for", request.client.host)
    return xff.split(",")[0].strip()


def geo_lookup(ip: str):
    if not os.path.exists(ayonconfig.geoip_db_path):
        return None

    with geoip2.database.Reader(ayonconfig.geoip_db_path) as reader:
        try:
            response = reader.city(ip)
        except geoip2.errors.AddressNotFoundError:
            return None

    return LocationInfo(
        country=response.country.name,
        subdivision=response.subdivisions.most_specific.name,
        city=response.city.name,
    )


def is_internal_ip(ip: str) -> bool:
    with contextlib.suppress(ValueError):
        if ipaddress.IPv4Address(ip).is_private:
            return True

    with contextlib.suppress(ValueError):
        if ipaddress.IPv6Address(ip).is_private:
            return True
    return False


def parse_ayon_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {}
    result: dict[str, str] = {}
    for header in ["x-ayon-platform", "x-ayon-version", "x-ayon-hostname"]:
        value = request.headers.get(header)
        if value:
            headers[header] = value

    if headers.get("x-ayon-platform"):
        result["platform"] = headers["x-ayon-platform"]
    if headers.get("x-ayon-version"):
        result["client"] = f"Ayon client {headers['x-ayon-version']}"
    if headers.get("x-ayon-hostname"):
        result["device"] = headers["x-ayon-hostname"]
    if headers.get("x-ayon-site-id"):
        result["site_id"] = headers["x-ayon-site-id"]
    return result


def get_ua_data(request) -> AgentInfo | None:
    if ayon_headers := parse_ayon_headers(request):
        return AgentInfo(**ayon_headers)

    elif ua_string := request.headers.get("user-agent"):
        ua = user_agents.parse(ua_string)
        if "mac" in ua_string.lower():
            platform = "darwin"
        elif "windows" in ua_string.lower():
            platform = "windows"
        elif "linux" in ua_string.lower():
            platform = "linux"
        else:
            platform = ua_string.lower()
        return AgentInfo(
            platform=platform,
            client=ua.browser.family,
            device=ua.device.family,
        )
    return None


def get_preferred_languages(request: Request) -> list[str]:
    languages = []
    if accept_language := request.headers.get("Accept-Language"):
        try:
            for lang_token in accept_language.split(";"):
                lang = lang_token.split(",")[-1]
                if len(lang) == 2:
                    languages.append(lang)
        except Exception:
            return ["en"]
    else:
        languages = ["en"]
    return languages


def get_client_info(request: Request) -> ClientInfo:
    ip = get_real_ip(request)
    if is_internal_ip(ip):
        location = None
    else:
        location = geo_lookup(ip)
    return ClientInfo(
        ip=ip,
        agent=get_ua_data(request),
        location=location,
        languages=get_preferred_languages(request),
    )
