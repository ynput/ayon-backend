from ayon_server.types import ProjectLevelEntityType


class EntityOperations:
    def __init__(self, project_name: str):
        self.project_name = project_name

    def create(self, entity_type: ProjectLevelEntityType, **kwargs):
        pass
