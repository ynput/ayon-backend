# This is for testing purposes
import json

from .project_storage import ProjectStorage
from .s3 import S3Config

test_s3_config = json.load(open("/storage/s3_test.json"))

PROJECT_STORAGE_OVERRIDES = {
    "demo_Commercial": ProjectStorage(
        "demo_Commercial",
        "s3",
        "media/{instance_id}/server/projects",
        bucket_name="ayon-media",
        s3_config=S3Config(**test_s3_config),
    ),
}


class Storages:
    @classmethod
    async def project(cls, project_name: str) -> ProjectStorage:
        storage = PROJECT_STORAGE_OVERRIDES.get(project_name)
        if storage:
            return storage
        return ProjectStorage.default(project_name)
