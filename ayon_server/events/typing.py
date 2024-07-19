from ayon_server.types import NAME_REGEX, TOPIC_REGEX, Field

TOPIC_FIELD = Field(
    ...,
    title="Topic",
    description="Topic of the event",
    example="media.import",
    regex=TOPIC_REGEX,
)

SENDER_FIELD = Field(
    None,
    title="Sender",
    description="Identifier of the process that sent the event.",
    example="service-processor-01",
)

HASH_FIELD = Field(
    None,
    title="Hash",
    description="Deterministic hash of the event topic and summary/payload",
)

PROJECT_FIELD = Field(
    None,
    title="Project name",
    description="Name of the project if the event belong to one.",
    example="MyProject",
    regex=NAME_REGEX,
)

DEPENDS_ON_FIELD = Field(
    None,
    title="Depends on",
    description="ID of the event this event depends on.",
    min_length=32,
    max_length=32,
    example="69dd9b85a522fcedc14203ea95f54f52",
)

DESCRIPTION_FIELD = Field(
    None,
    title="Description",
    description="Short, human-readable description of the event and its state",
    example="Importing file 3 of 10",
)

SUMMARY_FIELD = Field(
    default_factory=dict,
    title="Summary",
    description="Arbitrary topic-specific data sent to clients in real time",
)

PAYLOAD_FIELD = Field(
    default_factory=dict,
    title="Payload",
    description="Full event payload. Only avaiable in REST endpoint.",
)

USER_FIELD = Field(
    None,
    title="User name",
    example="admin",
)

PROGRESS_FIELD = Field(
    None,
    title="Progress",
    example=42,
    ge=0,
    le=100,
    description="Percentage of progress. Transmitted to clients in real time.",
)

RETRIES_FIELD = Field(
    None,
    title="Retries",
    description="Force number of attempted retries",
    example=1,
)

ID_FIELD = Field(
    ...,
    min_length=32,
    max_length=32,
    title="Event ID",
    description="ID of the created event.",
    example="c14203ea95f54f569dd9b85a522fced2",
)
