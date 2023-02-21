from ayon_server.types import Field, OPModel


class TeamMemberModel(OPModel):
    name: str = Field(..., title="User's name")
    leader: bool = Field(False, title="Is user a leader")
    roles: list[str] = Field(default_factory=list, title="User's role")


class TeamPutModel(OPModel):
    members: list[TeamMemberModel] = Field(..., title="Team members")


class TeamModel(OPModel):
    name: str = Field(..., description="Team name")
    members: list[TeamMemberModel] = Field(
        default_factory=list,
        description="Team members",
    )


class TeamListItemModel(OPModel):
    name: str = Field(..., description="Team name")
    member_count: int = Field(..., description="Number of members in the team")
    leaders: list[TeamMemberModel] = Field(
        default_factory=list,
        description="Team leaders",
    )
