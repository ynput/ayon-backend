import pytest
from pydantic import ValidationError

from ayon_server.settings.anatomy import Anatomy
from ayon_server.settings.anatomy.folder_types import FolderType
from ayon_server.settings.anatomy.statuses import Status
from ayon_server.settings.anatomy.tags import Tag
from ayon_server.settings.anatomy.task_types import TaskType


class TestOriginalName:
    """original_name is used to detect renames of anatomy items"""

    @pytest.mark.parametrize("model", [FolderType, TaskType, Tag, Status])
    def test_defaults_to_name(self, model):
        assert model(name="Shot").original_name == "Shot"

    @pytest.mark.parametrize("model", [FolderType, TaskType, Tag, Status])
    def test_explicit_value_is_kept(self, model):
        assert model(name="Shot", original_name="Scene").original_name == "Scene"

    def test_invalid_name_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            FolderType(name="")

    def test_same_value_with_and_without_cache(self):
        # Project anatomy is extracted from the project (items without
        # original_name) or loaded from the cache (model_dump of it)
        extracted = Anatomy(folder_types=[{"name": "Shot"}])
        cached = Anatomy(**extracted.model_dump())
        assert extracted.folder_types[0].original_name == "Shot"
        assert cached.folder_types[0].original_name == "Shot"
