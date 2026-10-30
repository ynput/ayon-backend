"""Ynput Cloud's server URL wins over the stored one on managed instances."""

from typing import Any

import pytest

from ayon_server.config.serverconfig import ServerConfigModel
from ayon_server.helpers import server_url
from ayon_server.helpers.cloud import CloudUtils, YnputCloudInfoModel


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("stored", "cloud", "managed", "expected", "written"),
    [
        ("https://old.test", "https://new.test/", True, "https://new.test", True),
        ("https://new.test", "https://new.test/", True, "https://new.test", False),
        ("https://old.test", "https://new.test", False, "https://old.test", False),
        ("", None, True, None, False),
    ],
)
async def test_get_server_url(
    monkeypatch: pytest.MonkeyPatch,
    stored: str,
    cloud: str | None,
    managed: bool,
    expected: str | None,
    written: bool,
) -> None:
    updates: list[dict[str, Any]] = []

    async def get_server_config() -> ServerConfigModel:
        return ServerConfigModel(server_url=stored)  # type: ignore[call-arg]

    async def get_cloud_info() -> YnputCloudInfoModel:
        return YnputCloudInfoModel(
            instance_id="test", server_url=cloud, managed=managed
        )  # type: ignore[call-arg]

    async def update_server_config(data: dict[str, Any]) -> None:
        updates.append(data)

    monkeypatch.setattr(server_url, "get_server_config", get_server_config)
    monkeypatch.setattr(server_url, "update_server_config", update_server_config)
    monkeypatch.setattr(CloudUtils, "get_cloud_info", get_cloud_info)

    assert await server_url.get_server_url() == expected
    assert updates == ([{"server_url": expected}] if written else [])
