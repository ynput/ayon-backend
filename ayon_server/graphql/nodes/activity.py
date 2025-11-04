from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

import strawberry
from strawberry import LazyType

from ayon_server.activities.activity_categories import ActivityCategories
from ayon_server.exceptions import ForbiddenException
from ayon_server.graphql.types import Info
from ayon_server.utils import json_dumps, json_loads, slugify

if TYPE_CHECKING:
    from ayon_server.graphql.nodes.user import UserNode
    from ayon_server.graphql.nodes.version import VersionNode
else:
    UserNode = LazyType["UserNode", ".user"]
    VersionNode = LazyType["VersionNode", ".version"]


@strawberry.type
class ActivityOriginNode:
    id: str = strawberry.field()
    type: str = strawberry.field()
    subtype: str | None = strawberry.field(default=None)
    name: str = strawberry.field(default=None)
    label: str | None = strawberry.field(default=None)

    @property
    def markdownlink(self) -> str:
        return f"[{self.name}]({self.type}:{self.id})"

    @strawberry.field
    def link(self) -> str:
        return self.markdownlink


@strawberry.type
class ActivityFileNode:
    id: str = strawberry.field()
    size: str = strawberry.field()  # str, because int limit is 2^31-1
    author: str | None = strawberry.field()
    name: str | None = strawberry.field()
    mime: str | None = strawberry.field()
    created_at: datetime = strawberry.field()
    updated_at: datetime = strawberry.field()


@strawberry.type
class ActivityReactionNode:
    user_name: str = strawberry.field()
    full_name: str | None = strawberry.field()
    reaction: str = strawberry.field()
    timestamp: datetime = strawberry.field()


@strawberry.type
class ActivityCategory:
    name: str = strawberry.field()
    color: str = strawberry.field()


@strawberry.type
class ActivityNode:
    project_name: str = strawberry.field()

    reference_id: str = strawberry.field()
    activity_id: str = strawberry.field()
    reference_type: str = strawberry.field()
    activity_type: str = strawberry.field()

    entity_type: str = strawberry.field()  # TODO. use literal?
    entity_id: str | None = strawberry.field()
    entity_name: str | None = strawberry.field()
    entity_path: str | None = strawberry.field()

    created_at: datetime = strawberry.field()
    updated_at: datetime = strawberry.field()
    creation_order: int = strawberry.field()

    body: str = strawberry.field()
    tags: list[str] = strawberry.field()
    category: ActivityCategory | None = strawberry.field()
    activity_data: str = strawberry.field()
    reference_data: str = strawberry.field()
    active: bool = strawberry.field(default=True)
    read: bool = strawberry.field(default=False)  # for inbox

    origin: ActivityOriginNode | None = strawberry.field()
    parents: list[ActivityOriginNode] = strawberry.field()
    reactions: list[ActivityReactionNode] = strawberry.field()

    @strawberry.field
    async def author(self, info: Info) -> UserNode | None:
        data = json_loads(self.activity_data)
        if "author" in data:
            author = data["author"]
            if author.startswith("guest."):
                if "project" not in info.context:
                    # in inbox, we don't have project context
                    record = {
                        "name": author,
                        "attrib": {
                            "email": author,
                            "fullName": author,
                        },
                        "active": True,
                        "deleted": True,
                        "created_at": "1970-01-01T00:00:00Z",
                        "updated_at": "1970-01-01T00:00:00Z",
                    }
                    return await info.context["user_from_record"](
                        None, record, info.context
                    )
                else:
                    guest_users = info.context["project"].data.get("guestUsers", {})
                    for email, payload in guest_users.items():
                        candidate_name = slugify(f"guest.{email}", separator=".")
                        if candidate_name != author:
                            continue
                        full_name = payload.get("fullName", email)
                        record = {
                            "name": author,
                            "attrib": {
                                "email": email,
                                "fullName": full_name,
                            },
                            "active": True,
                            "deleted": True,
                            "created_at": "1970-01-01T00:00:00Z",
                            "updated_at": "1970-01-01T00:00:00Z",
                        }
                        return await info.context["user_from_record"](
                            None, record, info.context
                        )

            loader = info.context["user_loader"]
            record = await loader.load(author)
            if not record:
                record = {
                    "name": author,
                    "attrib": {
                        "fullName": author,
                    },
                    "active": False,
                    "deleted": True,
                    "created_at": "1970-01-01T00:00:00Z",
                    "updated_at": "1970-01-01T00:00:00Z",
                }
            return await info.context["user_from_record"](None, record, info.context)
        return None

    @strawberry.field
    async def assignee(self, info: Info) -> UserNode | None:
        data = json_loads(self.activity_data)
        if "assignee" in data:
            assignee = data["assignee"]
            loader = info.context["user_loader"]
            record = await loader.load(assignee)
            return await info.context["user_from_record"](None, record, info.context)
        return None

    @strawberry.field
    async def version(self, info: Info) -> Optional["VersionNode"]:
        if self.activity_type not in ["version.publish", "reviewable"]:
            return None

        data = json_loads(self.activity_data)
        version_id = data.get("origin", {}).get("id")
        if not version_id:
            return None

        loader = info.context["version_loader"]
        record = await loader.load((self.project_name, version_id))
        if record is None:
            return None
        return await info.context["version_from_record"](
            self.project_name, record, info.context
        )

    @strawberry.field
    async def files(self, info: Info) -> list[ActivityFileNode]:
        """List of files attached to the activity."""

        data = json_loads(self.activity_data)
        files = data.get("files", [])
        result = []
        for file in files:
            result.append(
                ActivityFileNode(
                    id=file.get("id"),
                    name=file.get("filename"),
                    size=str(file.get("size", "0")),
                    author=file.get("author"),
                    mime=file.get("mime"),
                    created_at=file["created_at"],
                    updated_at=file["updated_at"],
                )
            )
        return result


def replace_reference_body(node: ActivityNode) -> ActivityNode:
    if not node.origin:
        return node  # should not happen

    if node.reference_type == "mention":
        node.body = (
            f"mentioned in a {node.activity_type} " f"on {node.origin.markdownlink}"
        )
        return node

    if node.reference_type == "relation":
        if node.activity_type == "comment":
            r = "commented on"
        elif node.activity_type == "status_change":
            r = "changed status of"
        node.body = f"{r} a related {node.origin.markdownlink}"

        return node
    return node


async def activity_from_record(
    project_name: str | None,
    record: dict[str, Any],
    context: dict[str, Any],
) -> ActivityNode:
    """Construct a folder node from a DB row.

    project name can be None for inbox. In that case,
    project_name is populated from the record.
    """

    record = dict(record)
    record.pop("cursor", None)

    project_name = record.pop("project_name", project_name)
    assert project_name, "project_name is required"
    activity_data = record.pop("activity_data", {})
    reference_data = record.pop("reference_data", {})
    tags = record.pop("tags", [])
    category = None
    if category_name := activity_data.get("category"):
        # use get here - inbox won't have categories in context
        cdata = context.get("activity_categories", {}).get(category_name)
        category = ActivityCategory(
            name=category_name,
            color=cdata.get("color") if cdata else "#999999",
        )

        if "inboxAccessibleCategories" in context:
            # but inbox has a map of accessible categories
            accessible_cats = context["inboxAccessibleCategories"]
            if project_name not in accessible_cats:
                accessible_cats[
                    project_name
                ] = await ActivityCategories.get_accessible_categories(
                    context["user"], project_name=project_name
                )
            if category_name not in accessible_cats[project_name]:
                raise ForbiddenException()

    origin_data = activity_data.get("origin")
    if origin_data:
        origin = ActivityOriginNode(**origin_data)
    else:
        origin = None

    if parents_data := activity_data.get("parents"):
        parents = [ActivityOriginNode(**parent) for parent in parents_data]
    else:
        parents = []

    body = record.pop("body")
    if context.get("inbox"):
        body = body.replace("\n", " ")
        if len(body) == 200:
            # 200 characters is the inbox limit defined in the database
            body += "..."

    reactions: list[ActivityReactionNode] = []
    if reactions_data := activity_data.get("reactions"):
        for reaction in reactions_data:
            reactions.append(
                ActivityReactionNode(
                    user_name=reaction["userName"],
                    full_name=reaction["fullName"],
                    reaction=reaction["reaction"],
                    timestamp=datetime.fromisoformat(reaction["timestamp"]),
                )
            )

    node = ActivityNode(
        project_name=project_name,
        reference_id=record.pop("reference_id"),
        activity_id=record.pop("activity_id"),
        reference_type=record.pop("reference_type"),
        activity_type=record.pop("activity_type"),
        entity_type=record.pop("entity_type"),
        entity_id=record.pop("entity_id", None),
        entity_name=record.pop("entity_name", None),
        entity_path=record.pop("entity_path", None),
        created_at=record.pop("created_at"),
        updated_at=record.pop("updated_at"),
        creation_order=record.pop("creation_order"),
        body=body,
        tags=tags,
        category=category,
        activity_data=json_dumps(activity_data),
        reference_data=json_dumps(reference_data),
        active=record.pop("active", True),
        read=reference_data.pop("read", False),
        origin=origin,
        parents=parents,
        reactions=reactions,
    )
    # probably won't be used
    # node = replace_reference_body(node)
    return node


ActivityNode.from_record = staticmethod(activity_from_record)  # type: ignore
