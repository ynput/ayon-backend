"""Teams of a user (UserEntity.get_teams)"""

from types import SimpleNamespace
from typing import Any

from ayon_server.entities import UserEntity


def project(name: str, teams: dict[str, list[str]]) -> Any:
    return SimpleNamespace(
        name=name,
        data={
            "teams": [
                {"name": team, "members": [{"name": member} for member in members]}
                for team, members in teams.items()
            ]
        },
    )


def test_teams_per_project():
    user = UserEntity({"name": "artist", "data": {}}, True)
    project_a = project("project_a", {"lighting": ["artist"], "comp": ["other"]})
    project_b = project("project_b", {"lighting": ["other"], "fx": ["artist"]})

    assert user.get_teams(project_a) == {"lighting"}
    assert user.get_teams(project_b) == {"fx"}
    assert user.get_teams(project_a) == {"lighting"}
