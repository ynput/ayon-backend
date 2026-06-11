import strawberry


@strawberry.type
class EntityComment:
    activity_id: str = strawberry.field()
    body: str = strawberry.field()
    author: str | None = strawberry.field(default=None)
    created_at: str = strawberry.field()
