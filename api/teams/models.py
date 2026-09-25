from ayon_server.types import USER_NAME_REGEX, Field, OPModel


class TeamMemberModel(OPModel):
    name: str = Field(..., title="User's name", regex=USER_NAME_REGEX)
    leader: bool = Field(False, title="Is user a leader")
    roles: list[str] = Field(default_factory=list, title="User's role")


class TeamPutModel(OPModel):
    members: list[TeamMemberModel] = Field(..., title="Team members")


class TeamModel(OPModel):
    name: str = Field(..., description="Team name", min_length=2, max_length=64)
    members: list[TeamMemberModel] = Field(
        default_factory=list,
        description="Team members",
    )


class TeamListItemModel(OPModel):
    name: str = Field(..., description="Team name", min_length=2, max_length=64)
    member_count: int = Field(..., description="Number of members in the team")
    members: list[TeamMemberModel] | None = Field(None, description="Team members")
    leaders: list[TeamMemberModel] = Field(
        default_factory=list,
        description="Team leaders",
    )
