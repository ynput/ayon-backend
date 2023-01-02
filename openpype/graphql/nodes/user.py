import strawberry

from openpype.entities import UserEntity
from openpype.graphql.utils import parse_attrib_data
from openpype.utils import get_nickname, json_dumps, obscure


@UserEntity.strawberry_attrib()
class UserAttribType:
    pass


@strawberry.type
class UserNode:
    name: str
    active: bool
    created_at: int
    updated_at: int
    attrib: UserAttribType
    roles: str
    default_roles: list[str]
    is_admin: bool
    is_manager: bool
    is_service: bool
    is_guest: bool
    has_password: bool


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
        and current_user.name != data.created_by
    ):
        name = get_nickname(name)
        if attrib.email:
            attrib.email = obscure(attrib.email)
        if attrib.fullName:
            attrib.fullName = name

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
    )


setattr(UserNode, "from_record", staticmethod(user_from_record))
