from typing import Annotated, Any

from ayon_server.types import NAME_REGEX, SEMVER_REGEX, Field, OPModel


class AddonSettingsItemModel(OPModel):
    name: Annotated[
        str,
        Field(
            title="Addon name",
            regex=NAME_REGEX,
            example="my-addon",
        ),
    ]

    version: Annotated[
        str,
        Field(
            title="Addon version",
            regex=SEMVER_REGEX,
            example="1.0.0",
        ),
    ]

    title: Annotated[
        str,
        Field(
            title="Addon title",
            example="My Addon",
        ),
    ]

    has_settings: Annotated[
        bool,
        Field(
            title="Has settings",
            description="Indicates if the addon has editable settings",
        ),
    ] = False

    has_project_settings: Annotated[
        bool,
        Field(
            title="Has project settings",
            description="Indicates if the addon has editable project settings",
        ),
    ] = False

    has_project_site_settings: Annotated[
        bool,
        Field(
            title="Has project site settings",
            description="Indicates if the addon has editable project site settings",
        ),
    ] = False

    has_site_settings: Annotated[
        bool,
        Field(
            title="Has site settings",
            description="Indicates if the addon has editable site settings",
        ),
    ] = False

    #
    # Does the addon have settings edited?
    #

    # None value means that project does not have overrides
    # or project/site was not specified in the request

    has_studio_overrides: Annotated[
        bool | None, Field(title="Has studio overrides")
    ] = None
    has_project_overrides: Annotated[
        bool | None, Field(title="Has project overrides")
    ] = None
    has_project_site_overrides: Annotated[
        bool | None, Field(title="Has project site overrides")
    ] = None

    #
    # Actual settings object
    #

    # Final settings for the addon depending on the request (project, site)
    # it returns either studio, project or project/site settings
    settings: Annotated[
        dict[str, Any],
        Field(
            title="Addon settings",
            default_factory=dict,
            description=(
                "Final settings for the addon depending of "
                "the studio/project/site branch"
            ),
        ),
    ]

    # If site_id is specified and the addon has site settings model,
    # return studio level site settings here
    site_settings: Annotated[
        dict[str, Any] | None,
        Field(
            title="Site settings",
            default_factory=dict,
            description="Site settings for the addon depending of the site branch",
        ),
    ]

    #
    # Debugging
    #

    is_broken: Annotated[
        bool,
        Field(
            title="Is broken",
            description="Indicates if the addon is not properly initialized",
        ),
    ] = False

    reason: Annotated[
        dict[str, str] | None,
        Field(
            title="Reason",
            description="Reason for addon being broken",
        ),
    ] = None


class AllSettingsResponseModel(OPModel):
    bundle_name: Annotated[
        str,
        Field(
            title="Bundle name",
            regex=NAME_REGEX,
        ),
    ]

    addons: Annotated[
        list[AddonSettingsItemModel],
        Field(
            title="Addons",
            default_factory=list,
        ),
    ]

    inherited_addons: Annotated[
        list[str],
        Field(
            title="Inherited addons",
            default_factory=list,
            description=(
                "If a project bundle is used, this field contains alist of addons "
                "that are inherited from the studio bundle"
            ),
        ),
    ]
