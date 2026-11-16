import re

import pytest
from pydantic import ValidationError

from ayon_server.entity_lists.models import EntityListMultiPatchItemModel
from ayon_server.operations.project_level.models import OperationModel
from ayon_server.types import ENTITY_ID_REGEX
from ayon_server.utils import create_uuid

INVALID_IDS = ["undefined", "Z" * 32, "?" * 32, "A" * 32, "a" * 31]


@pytest.mark.parametrize("value", INVALID_IDS)
def test_invalid_entity_ids_are_rejected(value: str) -> None:
    assert not re.match(ENTITY_ID_REGEX, value)
    with pytest.raises(ValidationError):
        OperationModel(type="update", entity_type="folder", entity_id=value)
    with pytest.raises(ValidationError):
        EntityListMultiPatchItemModel(id=None, entity_id=value)


def test_valid_entity_ids_are_accepted() -> None:
    entity_id = create_uuid()
    assert re.match(ENTITY_ID_REGEX, entity_id)
    OperationModel(type="update", entity_type="folder", entity_id=entity_id)
    OperationModel(type="create", entity_type="folder")
    EntityListMultiPatchItemModel(id=None, entity_id=entity_id)
