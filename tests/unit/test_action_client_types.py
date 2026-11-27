"""Client type filter of simple actions (`SimpleActionManifest.client_types`)."""

import asyncio

import pytest
from pydantic import ValidationError

from ayon_server.actions.context import ActionContext
from ayon_server.actions.listing import evaluate_simple_action
from ayon_server.actions.manifest import SimpleActionManifest


def _action(client_types: list[str] | None, entity_type: str | None = "folder"):
    return SimpleActionManifest(
        identifier="test.action",
        label="Test action",
        entity_type=entity_type,
        client_types=client_types,
    )


def _folder_context(client_type: str | None) -> ActionContext:
    return ActionContext(
        project_name="test_project",
        entity_type="folder",
        entity_ids=["1a3bfe331b1b4b1b8b1b1b1b1b1b1b1b"],
        client_type=client_type,
    )


def _evaluate(action: SimpleActionManifest, context: ActionContext) -> bool:
    return asyncio.run(evaluate_simple_action(action, context))


@pytest.mark.parametrize(
    "client_types, client_type, expected",
    [
        # no filter: every client
        (None, "web", True),
        ([], "desktop", True),
        # filter matches
        (["desktop"], "desktop", True),
        (["web", "desktop"], "web", True),
        # filter doesn't match
        (["desktop"], "web", False),
        # client doesn't send its type: not filtered
        (["desktop"], None, True),
    ],
)
def test_client_type_filter(client_types, client_type, expected):
    assert _evaluate(_action(client_types), _folder_context(client_type)) is expected


def test_client_type_filter_on_project_actions():
    # project actions skip the entity checks, but not the client type filter
    action = _action(["desktop"], entity_type="project")
    web = ActionContext(
        project_name="test_project", entity_type="project", client_type="web"
    )
    desktop = ActionContext(
        project_name="test_project", entity_type="project", client_type="desktop"
    )
    assert _evaluate(action, web) is False
    assert _evaluate(action, desktop) is True


def test_client_type_filter_on_global_actions():
    action = _action(["web"], entity_type=None)
    assert _evaluate(action, ActionContext(client_type="desktop")) is False
    assert _evaluate(action, ActionContext(client_type="web")) is True


def test_client_type_is_kept_for_global_actions():
    # project-only fields are dropped without a project, client_type is not
    assert ActionContext(client_type="desktop").client_type == "desktop"


def test_client_type_from_camel_case_payload():
    context = ActionContext(**{"projectName": "test_project", "clientType": "web"})
    assert context.client_type == "web"


def test_client_type_changes_context_hash():
    web = ActionContext(project_name="test_project", client_type="web")
    desktop = ActionContext(project_name="test_project", client_type="desktop")
    assert web != desktop


def test_unknown_client_type_is_rejected():
    with pytest.raises(ValidationError):
        _action(["launcher"])
    with pytest.raises(ValidationError):
        ActionContext(client_type="launcher")


def test_client_types_survive_cache_roundtrip():
    # SimpleActionCache stores model_dump() and rebuilds the manifest
    action = _action(["web", "desktop"])
    assert SimpleActionManifest(**action.model_dump()).client_types == [
        "web",
        "desktop",
    ]
