import strawberry


@strawberry.type
class BaseNode:
    project_name: str = strawberry.field()
