"""The client IP is taken only from X-Forwarded-For entries added by our proxies."""

import pytest
from starlette.requests import Request

from ayon_server.config import ayonconfig
from ayon_server.utils.server import get_real_ip_from_request


def make_request(xff: str | None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    scope = {"type": "http", "headers": headers, "client": ("10.0.0.2", 1234)}
    return Request(scope)


@pytest.mark.parametrize(
    ("hops", "xff", "expected"),
    [
        (0, "1.1.1.1", "10.0.0.2"),  # no proxy: the header is ignored
        (1, None, "10.0.0.2"),
        (1, "1.1.1.1", "1.1.1.1"),
        (1, "6.6.6.6, 1.1.1.1", "1.1.1.1"),  # client sent a fake entry
        (1, "10.0.0.1, 1.1.1.1", "1.1.1.1"),  # fake internal IP doesn't help
        (2, "6.6.6.6, 1.1.1.1, 2.2.2.2", "1.1.1.1"),
        (2, "1.1.1.1", "1.1.1.1"),  # fewer entries than hops
    ],
)
def test_real_ip(
    monkeypatch: pytest.MonkeyPatch, hops: int, xff: str | None, expected: str
) -> None:
    monkeypatch.setattr(ayonconfig, "trusted_proxy_hops", hops)
    assert get_real_ip_from_request(make_request(xff)) == expected
