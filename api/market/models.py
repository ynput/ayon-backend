from datetime import datetime
from typing import Annotated, Literal

from ayon_server.models import RestField, RestModel


class LinkModel(RestModel):
    """A model representing a link to an external resource.

    Resource is an external website, containing additional information
    about the addon, such as a homepage, GitHub repository or documentation.
    """

    type: Annotated[
        Literal["homepage", "github", "documentation", "license"],
        RestField(
            title="Link type",
            example="github",
        ),
    ] = "homepage"
    label: Annotated[
        str | None,
        RestField(
            title="Link label",
            example="ynput/my-addon",
        ),
    ] = None
    url: Annotated[
        str,
        RestField(
            title="Link URL",
            example="https://github.com/ynput/my-addon",
        ),
    ]


class AddonListItem(RestModel):
    name: Annotated[str, RestField(title="Addon name", example="maya")]
    title: Annotated[str, RestField(title="Addon title", example="Maya")]
    description: Annotated[
        str | None,
        RestField(
            description="Addon description",
            example="Maya is a 3D computer graphics application",
        ),
    ] = None
    org_name: Annotated[
        str | None,
        RestField(
            title="Organization name",
            example="ynput-official",
        ),
    ] = None
    org_title: Annotated[
        str | None,
        RestField(
            title="Organization title",
            example="Ynput",
        ),
    ] = None
    icon: Annotated[
        str | None,
        RestField(
            title="Icon URL",
            example="https://example.com/maya.png",
        ),
    ] = None
    tags: Annotated[
        list[str],
        RestField(title="Tags", default_factory=list),
    ]
    flags: Annotated[
        list[str],
        RestField(title="Flags", default_factory=list),
    ]
    latest_version: Annotated[
        str | None,
        RestField(
            description="Latest version of the addon",
            example="1.0.0",
        ),
    ] = None
    links: Annotated[
        list[LinkModel] | None,
        RestField(
            description="Links to the addon's homepage and GitHub repository",
            example=[
                {"type": "github", "url": "https://github.com/ynput/ayon-maya"},
            ],
        ),
    ] = None
    available: Annotated[
        bool,
        RestField(description="Addon is avaliable for download"),
    ] = True

    # ayon only
    current_production_version: Annotated[
        str | None, RestField(title="Current production version", example="1.0.0")
    ] = None
    current_latest_version: Annotated[
        str | None, RestField(title="Latest installed version", example="1.0.0")
    ] = None
    is_outdated: Annotated[
        bool, RestField(title="Is the current version outdated", example=False)
    ] = False


class AddonList(RestModel):
    addons: Annotated[list[AddonListItem], RestField(default_factory=list)]


class AddonVersionListItem(RestModel):
    version: Annotated[
        str,
        RestField(
            title="Addon version",
            example="1.0.0",
        ),
    ]
    ayon_version: Annotated[
        str | None,
        RestField(
            title="Ayon version",
            description="Required Ayon server version to run the addon",
            example="1.2.0",
        ),
    ] = None
    created_at: Annotated[
        datetime | None, RestField(example="2024-01-01T00:00:00Z")
    ] = None
    updated_at: Annotated[
        datetime | None, RestField(example="2024-01-01T00:00:00Z")
    ] = None

    # ayon only
    is_compatible: Annotated[
        bool | None, RestField(description="Is this version compatible?")
    ] = None
    is_installed: Annotated[
        bool | None, RestField(description="Is this version installed?")
    ] = None
    is_production: Annotated[
        bool | None, RestField(description="Is this version in production?")
    ] = None


class AddonDetail(AddonListItem):
    versions: Annotated[
        list[AddonVersionListItem],
        RestField(
            default_factory=list,
            description="A list of versions of this addon",
        ),
    ]

    # ayon only
    warning: Annotated[
        str | None,
        RestField(description="A warning message to display to the user"),
    ] = None


class AddonVersionDetail(AddonListItem):
    version: Annotated[str, RestField(example="1.0.0")]
    url: Annotated[
        str | None, RestField(example="https://example.com/maya-1.0.0.zip")
    ] = None
    alt_url: Annotated[
        str | None, RestField(example="https://example2.com/maya-1.0.0.zip")
    ] = None
    checksum: Annotated[str | None, RestField(example="a1b2c3d4e5f6g7h8i9j0")] = None
    ayon_version: Annotated[
        str | None,
        RestField(
            description="The version of Ayon this version is compatible with",
            example="1.2.0",
        ),
    ] = None
    created_at: Annotated[
        datetime,
        RestField(
            default_factory=datetime.now,
            description="When this version was created",
            example="2024-01-01T00:00:00Z",
        ),
    ]
    updated_at: Annotated[
        datetime,
        RestField(
            default_factory=datetime.now,
            description="When this version was last updated",
            example="2024-01-01T00:00:00Z",
        ),
    ]

    # ayon only
    is_installed: Annotated[
        bool, RestField(description="Is this version installed?")
    ] = False
    is_production: Annotated[
        bool, RestField(description="Is this version in production?")
    ] = False
    is_compatible: Annotated[
        bool, RestField(description="Is this version compatible?")
    ] = False
