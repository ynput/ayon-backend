from datetime import datetime
from typing import TYPE_CHECKING, Any

import strawberry
from strawberry import LazyType

from ayon_server.entities import UserEntity
from ayon_server.graphql.resolvers.tasks import get_tasks
from ayon_server.graphql.types import Info
from ayon_server.graphql.utils import parse_attrib_data, process_attrib_data
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
    access_groups: str
    default_access_groups: list[str]
    is_admin: bool
    is_manager: bool
    is_service: bool
    is_guest: bool
    is_developer: bool
    has_password: bool
    disable_password_login: bool = False
    user_pool: str | None = None
    apiKeyPreview: str | None = None
    deleted: bool = False

    _attrib: strawberry.Private[dict[str, Any]]
    _user: strawberry.Private[UserEntity]

    @strawberry.field
    def attrib(self) -> UserAttribType:
        return parse_attrib_data(
            UserAttribType,
            self._attrib,
            user=self._user,
        )

    @strawberry.field
    def all_attrib(self) -> str:
        return json_dumps(process_attrib_data(None, self._user, self._attrib))

    @strawberry.field
    async def tasks(self, info: Info, project_name: str) -> "TasksConnection":
        root = FakeRoot(project_name)
        return await get_tasks(root, info, assignees=[self.name])


async def user_from_record(
    project_name: str | None, record: dict[str, Any], context: dict[str, Any]
) -> UserNode:
    data = record.get("data", {})
    access_groups = data.get("accessGroups", {})
    is_admin = data.get("isAdmin", False)
    is_service = data.get("isService", False)
    is_developer = data.get("isDeveloper", False)
    is_manager = data.get("isManager", False)
    is_guest = data.get("isGuest", False)
    user_pool = data.get("userPool")
    disable_password_login = data.get("disablePasswordLogin", False)

    name = record["name"]
    attrib = record.get("attrib", {})

    current_user = context["user"]
    if (
        current_user.is_guest
        and current_user.name != name
        and current_user.name != data.get("createdBy")
    ):
        if name != "admin":
            name = get_nickname(name)
        if email := attrib.get("email"):
            attrib["email"] = obscure(email)
        if attrib.get("fullName"):
            attrib["fullName"] = name
        attrib["avatarUrl"] = None

    return UserNode(
        name=name,
        active=record["active"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        access_groups=json_dumps(access_groups),
        is_admin=is_admin,
        is_manager=is_manager,
        is_service=is_service,
        is_guest=is_guest,
        is_developer=is_developer,
        user_pool=user_pool,
        has_password=bool(data.get("password")),
        default_access_groups=data.get("defaultAccessGroups", []),
        disable_password_login=disable_password_login,
        apiKeyPreview=data.get("apiKeyPreview"),
        deleted=record.get("deleted", False),
        _attrib=attrib,
        _user=current_user,
    )


UserNode.from_record = staticmethod(user_from_record)  # type: ignore
