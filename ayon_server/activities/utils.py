import re
from typing import get_args

from nxtools import logging

from .models import ActivityReferenceModel, EntityLinkTuple, ReferencedEntityType

MAX_BODY_LENGTH = 2000

# extract links, but not images
LINK_PATTERN = re.compile(r"(?<!\!)\[(.*?)\]\((.*?)\)")
# LINK_PATTERN = re.compile(r"\[(.*?)\]\((.*?)\)")


def extract_link_tuples(md_text: str) -> list[EntityLinkTuple]:
    links: set[EntityLinkTuple] = set()
    for link in LINK_PATTERN.findall(md_text):
        try:
            entity_type, entity_id = link[1].split(":")
            links.add((entity_type, entity_id))
            if entity_type not in get_args(ReferencedEntityType):
                raise ValueError(f"Invalid referenced entity type: {entity_type}")
        except ValueError:
            logging.debug("Invalid reference link format")
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
