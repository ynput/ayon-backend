from datetime import datetime
from typing import TYPE_CHECKING
from strawberry import LazyType
from strawberry.types import Info

import strawberry

from ayon_server.entities import UserEntity
from ayon_server.graphql.resolvers.tasks import get_tasks
from ayon_server.graphql.utils import parse_attrib_data
from ayon_server.utils import get_nickname, json_dumps, obscure

if TYPE_CHECKING:
    from ayon_server.graphql.connections import TasksConnection
else:
    TasksConnection = LazyType["TasksConnection", "..connections"]


@UserEntity.strawberry_attrib()
class UserAttribType:
    pass


class FakeRoot:
    project_name: str

    def __init__(self, project_name: str):
        self.project_name = project_name


@strawberry.type
class UserNode:
    name: str
    active: bool
    created_at: datetime
    updated_at: datetime
    attrib: UserAttribType
    roles: str
    default_roles: list[str]
    is_admin: bool
    is_manager: bool
    is_service: bool
    is_guest: bool
    has_password: bool
    apiKeyPreview: str | None

    @strawberry.field
    def tasks(self, info: Info, project_name: str) -> "TasksConnection":
        root = FakeRoot(project_name)
        return get_tasks(root, info, assignees=[self.name])


def user_from_record(record: dict, context: dict) -> UserNode:
    data = record["data"]
    roles = data.get("roles", {})
    is_admin = data.get("isAdmin", False)
    is_service = data.get("isService", False)
    is_manager = is_admin or is_service or data.get("isManager", False)
    is_guest = data.get("isGuest", False)

    name = record["name"]
    attrib = parse_attrib_data(UserAttribType, record["attrib"], user=context["user"])

    current_user = context["user"]
    if (
        current_user.is_guest
        and current_user.name != name
        and current_user.name != data.get("createdBy")
    ):
        name = get_nickname(name)
        if attrib.email:
            attrib.email = obscure(attrib.email)
        if attrib.fullName:
            attrib.fullName = name
        attrib.avatarUrl = None

    return UserNode(
        name=name,
        active=record["active"],
        attrib=attrib,
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        roles=json_dumps(roles),
        is_admin=is_admin,
        is_manager=is_manager,
        is_service=is_service,
        is_guest=is_guest,
        has_password=bool(data.get("password")),
        default_roles=data.get("defaultRoles", []),
        apiKeyPreview=data.get("apiKeyPreview"),
    )


setattr(UserNode, "from_record", staticmethod(user_from_record))
