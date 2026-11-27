"""Platform filter of simple actions (`SimpleActionManifest.platforms`)."""

import asyncio

import pytest
from pydantic import ValidationError

from ayon_server.actions.context import ActionContext
from ayon_server.actions.listing import evaluate_simple_action
from ayon_server.actions.manifest import SimpleActionManifest


def _action(platforms: list[str] | None, entity_type: str | None = "folder"):
    return SimpleActionManifest(
        identifier="test.action",
        label="Test action",
        entity_type=entity_type,
        platforms=platforms,
    )


def _folder_context(platform: str | None) -> ActionContext:
    return ActionContext(
        project_name="test_project",
        entity_type="folder",
        entity_ids=["1a3bfe331b1b4b1b8b1b1b1b1b1b1b1b"],
        platform=platform,
    )


def _evaluate(action: SimpleActionManifest, context: ActionContext) -> bool:
    return asyncio.run(evaluate_simple_action(action, context))


@pytest.mark.parametrize(
    "platforms, platform, expected",
    [
        # no filter: every platform
        (None, "windows", True),
        ([], "darwin", True),
        # filter matches
        (["windows", "linux"], "linux", True),
        # filter doesn't match
        (["windows", "linux"], "darwin", False),
        # client doesn't send its platform: not filtered
        (["windows"], None, True),
    ],
)
def test_platform_filter(platforms, platform, expected):
    assert _evaluate(_action(platforms), _folder_context(platform)) is expected


def test_platform_filter_on_project_actions():
    # project actions skip the entity checks, but not the platform filter
    action = _action(["windows"], entity_type="project")
    linux = ActionContext(
        project_name="test_project", entity_type="project", platform="linux"
    )
    windows = ActionContext(
        project_name="test_project", entity_type="project", platform="windows"
    )
    assert _evaluate(action, linux) is False
    assert _evaluate(action, windows) is True


def test_platform_filter_on_global_actions():
    action = _action(["darwin"], entity_type=None)
    assert _evaluate(action, ActionContext(platform="windows")) is False
    assert _evaluate(action, ActionContext(platform="darwin")) is True


def test_unknown_platform_is_rejected():
    with pytest.raises(ValidationError):
        _action(["android"])
    with pytest.raises(ValidationError):
        ActionContext(platform="android")


def test_platforms_survive_cache_roundtrip():
    # SimpleActionCache stores model_dump() and rebuilds the manifest
    action = _action(["windows", "linux"])
    assert SimpleActionManifest(**action.model_dump()).platforms == [
        "windows",
        "linux",
    ]
