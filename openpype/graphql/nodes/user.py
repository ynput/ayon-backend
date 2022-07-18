import strawberry

from openpype.entities import UserEntity
from openpype.graphql.utils import parse_attrib_data
from openpype.utils import json_dumps


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
    is_admin: bool
    is_manager: bool


def user_from_record(record: dict, context: dict) -> UserNode:
    data = record["data"]
    roles = data.get("roles", {})
    is_admin = data.get("is_admin", False)
    is_manager = is_admin or data.get("is_manager", False)

    return UserNode(
        name=record["name"],
        active=record["active"],
        attrib=parse_attrib_data(
            UserAttribType,
            record["attrib"],
            user=context["user"],
        ),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        roles=json_dumps(roles),
        is_admin=is_admin,
        is_manager=is_manager,
    )


setattr(UserNode, "from_record", staticmethod(user_from_record))
