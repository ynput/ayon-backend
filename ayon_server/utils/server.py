import contextlib
import ipaddress
from urllib.parse import urlparse

from fastapi import Request


def is_internal_ip(ip: str) -> bool:
    """Check if the given IP address is internal (private)"""
    with contextlib.suppress(ValueError):
        if ipaddress.IPv4Address(ip).is_private:
            return True

    with contextlib.suppress(ValueError):
        if ipaddress.IPv6Address(ip).is_private:
            return True
    return False


def get_real_ip_from_request(request: Request) -> str:
    """Get the real client IP address from the request, considering possible proxies."""
    if request.client is None:
        return "0.0.0.0"
    xff = request.headers.get("x-forwarded-for", request.client.host)
    return xff.split(",")[0].strip()


def server_url_from_request(request: Request) -> str:
    """Constructs the server URL from the request object."""
    if referer := request.headers.get("referer"):
        parsed_url = urlparse(referer)
        return f"{parsed_url.scheme}://{parsed_url.netloc}"

    elif request.client:
        scheme = request.headers.get("X-Forwarded-Proto", request.url.scheme)
        host = request.headers.get("X-Forwarded-Host", request.client.host)
        port = request.headers.get("X-Forwarded-Port", request.url.port)

        if port and port not in ("80", "443"):
            return f"{scheme}://{host}"

        return f"{scheme}://{host}"

    else:
        return "http://localhost:5000"
