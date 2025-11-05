from urllib.parse import urlparse

from fastapi import Request


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
