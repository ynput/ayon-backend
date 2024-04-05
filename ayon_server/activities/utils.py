import re

from .models import ActivityReferenceModel, EntityLinkTuple

LINK_PATTERN = re.compile(r"\[(.*?)\]\((.*?)\)")


def extract_link_tuples(md_text: str) -> list[EntityLinkTuple]:
    links: set[EntityLinkTuple] = set()
    for link in LINK_PATTERN.findall(md_text):
        entity_type, entity_id = link[1].split(":")
        links.add((entity_type, entity_id))
    return list(links)


def extract_mentions(
    md_text: str,
) -> list[ActivityReferenceModel]:
    """Extract entity and user mentions from markdown text.

    Mentions are in the format (label)[entity_type:entity_id],
    label is ignored.
    """

    references: list[ActivityReferenceModel] = []

    for entity_type, entity_id in extract_link_tuples(md_text):
        if entity_type == "user":
            references.append(
                ActivityReferenceModel(
                    entity_name=entity_id,
                    reference_type="mention",
                    entity_type="user",
                    entity_id=None,
                )
            )
        else:
            references.append(
                ActivityReferenceModel(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    entity_name=None,
                    reference_type="mention",
                )
            )
    return references
