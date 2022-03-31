import strawberry

from openpype.entities import UserEntity
from openpype.graphql.utils import parse_attrib_data


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


def user_from_record(record: dict, context: dict) -> UserNode:
    return UserNode(
        name=record["name"],
        active=record["active"],
        attrib=parse_attrib_data(
            UserAttribType, record["attrib"], user=context["user"]
        ),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


setattr(UserNode, "from_record", staticmethod(user_from_record))
