from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.attributes.models import AttributeData, AttributeNameModel
from ayon_server.attributes.validate_attribute_data import validate_attribute_data
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger

from .router import router


class EntityListAttributeDefinition(AttributeNameModel):
    data: AttributeData


@router.get("/{list_id}/attributes")
async def get_entity_list_attributes_definition(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
) -> list[EntityListAttributeDefinition]:
    """Return a list of custom attributes for the entity list."""

    query = f"SELECT data FROM project_{project_name}.entity_lists WHERE id = $1"
    res = await Postgres.fetchrow(query, list_id)
    if not res:
        raise NotFoundException("Entity list not found")
    adata = res["data"].get("attributes", [])
    if not adata:
        return []

    assert isinstance(adata, list), "entity_list.data.attributes should be a list"

    result = []
    for attr_definition in adata:
        try:
            attr_definition = EntityListAttributeDefinition(**attr_definition)
        except Exception:
            logger.warning(f"Invalid attribute definition for entity list {list_id}")
            continue
        result.append(attr_definition)

    return result


@router.put("/{list_id}/attributes")
async def set_entity_list_attributes_definition(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    payload: list[EntityListAttributeDefinition],
) -> None:
    payload_list = []
    for attr_definition in payload:
        validate_attribute_data(attr_definition.name, attr_definition.data)
        payload_list.append(attr_definition.dict(exclude_unset=True, exclude_none=True))

    query = f"""
        UPDATE project_{project_name}.entity_lists
        SET data = jsonb_set(data, '{{attributes}}', $1)
        WHERE id = $2
    """
    await Postgres.execute(query, payload_list, list_id)
