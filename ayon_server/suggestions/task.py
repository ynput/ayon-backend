from ayon_server.entities import TaskEntity

from .models import TaskSuggestionItem, UserSuggestionItem, VersionSuggestionItem

STYPE = list[UserSuggestionItem | VersionSuggestionItem | TaskSuggestionItem]


async def get_task_suggestions(user: str, task: TaskEntity) -> dict[str, STYPE]:
    """
    Assignees: Every assignee in the project, sorted by assignees first.
    Versions: Every version linked to the task.
    Tasks: Direct sibling tasks to the task.
    """
    result: dict[str, STYPE] = {}

    return result
