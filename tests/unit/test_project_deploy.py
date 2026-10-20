import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from api.projects.deploy import deploy_project
from ayon_server.exceptions import ConflictException


def test_deploy_project_reports_duplicate_code() -> None:
    payload = SimpleNamespace(name="Test_1", code="Tes", skeleton=False)
    existing_project = SimpleNamespace(name="Test", code="Tes", skeleton=False)
    user = SimpleNamespace(check_permissions=Mock())

    with patch(
        "api.projects.deploy.get_project_info",
        new=AsyncMock(return_value=existing_project),
    ):
        with pytest.raises(ConflictException) as exc_info:
            asyncio.run(deploy_project(payload, user))

    assert str(exc_info.value) == "Project with code Tes already exists"
