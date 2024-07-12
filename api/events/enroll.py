from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.events.enroll import EnrollResponseModel, enroll_job
from ayon_server.exceptions import ForbiddenException
from ayon_server.sqlfilter import Filter
from ayon_server.types import TOPIC_REGEX, Field, OPModel

from .router import router

#
# Enroll (get a new job)
#


class EnrollRequestModel(OPModel):
    source_topic: str = Field(
        ...,
        title="Source topic",
        example="ftrack.update",
        regex=TOPIC_REGEX,
    )
    target_topic: str = Field(
        ...,
        title="Target topic",
        example="ftrack.sync_to_ayon",
        regex=TOPIC_REGEX,
    )
    sender: str = Field(
        ...,
        title="Sender",
        example="workerservice01",
    )
    description: str | None = Field(
        None,
        title="Description",
        description="Short, human readable description of the target event",
        example="Sync Ftrack project to Ayon",
    )
    sequential: bool = Field(
        False,
        title="Sequential",
        description="Ensure events are processed in sequential order",
        example=True,
    )
    filter: Filter | None = Field(
        None, title="Filter", description="Filter source events"
    )
    max_retries: int = Field(3, title="Max retries", example=3)
    debug: bool = False


# response model must be here
@router.post("/enroll", response_model=EnrollResponseModel)
async def enroll(
    payload: EnrollRequestModel,
    current_user: CurrentUser,
) -> EnrollResponseModel | EmptyResponse:
    """Enroll for a new job.

    Enroll for a new job by providing a source topic and target topic.
    Used by workers to get a new job to process. If there is no job
    available, request returns 204 (no content).

    Non-error response is returned because having nothing to do is not an error
    and we don't want to spam the logs.
    """

    assert "*" not in payload.target_topic, "Target topic must not contain wildcards"
    source_topic = payload.source_topic.replace("*", "%")

    if not current_user.is_service:
        raise ForbiddenException("Only services can enroll for jobs")

    user_name = current_user.name

    res = await enroll_job(
        source_topic,
        payload.target_topic,
        sender=payload.sender,
        user_name=user_name,
        description=payload.description,
        sequential=payload.sequential,
        filter=payload.filter,
        max_retries=payload.max_retries,
    )

    if res is None:
        return EmptyResponse()

    return res
