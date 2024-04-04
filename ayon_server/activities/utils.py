import re

from .models import EntityLinkTuple, EntityReferenceModel, UserReferenceModel

LINK_PATTERN = re.compile(r"\[(.*?)\]\((.*?)\)")


def extract_link_tuples(md_text: str) -> list[EntityLinkTuple]:
    links: set[EntityLinkTuple] = set()
    for link in LINK_PATTERN.findall(md_text):
        entity_type, entity_id = link[1].split(":")
        links.add((entity_type, entity_id))
    return list(links)


def extract_mentions(
    md_text: str,
) -> tuple[list[EntityReferenceModel], list[UserReferenceModel]]:
    """Extract entity and user mentions from markdown text.

    Mentions are in the format (label)[entity_type:entity_id],
    label is ignored.

    Returns a tuple of entity references and user references.
    """

    entity_references: list[EntityReferenceModel] = []
    user_references: list[UserReferenceModel] = []
    for entity_type, entity_id in extract_link_tuples(md_text):
        if entity_type == "user":
            user_references.append(
                UserReferenceModel(
                    user_name=entity_id,
                    reference_type="mention",
                )
            )
        else:
            entity_references.append(
                EntityReferenceModel(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    reference_type="mention",
                )
            )
    return entity_references, user_references
