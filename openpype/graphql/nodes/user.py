from openpype.entities import UserEntity

from ..utils import parse_attrib_data


@UserEntity.strawberry_attrib()
class UserAttribType:
    pass


# Do not inherit from BaseNode, because we don't want to expose the
# project_name field.
@UserEntity.strawberry_entity()
class UserNode:
    pass


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
