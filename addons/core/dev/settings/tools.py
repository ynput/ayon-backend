from pydantic import Field, validator
from openpype.settings import (
    BaseSettingsModel,
    normalize_name,
    ensure_unique_names,
)


class FamiliesSmartSelectModel(BaseSettingsModel):
    _layout = "expanded"
    name: str = Field("", title="Family")
    task_names: list[str] = Field(default_factory=list, title="Task names")

    @validator("name")
    def normalize_value(cls, value):
        return normalize_name(value)


class SubsetNameProfile(BaseSettingsModel):
    _layout = "expanded"
    families: list[str] = Field(default_factory=list, title="Families")
    hosts: list[str] = Field(default_factory=list, title="Hosts")
    task_types: list[str] = Field(default_factory=list, title="Task types")
    tasks: list[str] = Field(default_factory=list, title="Task names")
    template: str = Field("", title="Template")


class CreatorToolModel(BaseSettingsModel):
    # TODO this was dynamic dictionary '{name: task_names}'
    families_smart_select: list[FamiliesSmartSelectModel] = Field(
        default_factory=list,
        title="Families Smart Select"
    )
    subset_name_profiles: list[SubsetNameProfile] = Field(
        default_factory=list,
        title="Subset name profiles"
    )

    @validator("families_smart_select")
    def validate_unique_name(cls, value):
        ensure_unique_names(value)
        return value


class WorkfileTemplateProfile(BaseSettingsModel):
    _layout = "expanded"
    # TODO this should use task types enum
    task_types: list[str] = Field(default_factory=list, title="Task types")
    # TODO this should use hosts enum
    hosts: list[str] = Field(default_factory=list, title="Hosts")
    # TODO this was using project anatomy template name
    workfile_template: str = Field("", title="Workfile template")


class LastWorkfileOnStartupProfile(BaseSettingsModel):
    _layout = "expanded"
    # TODO this should use hosts enum
    hosts: list[str] = Field(default_factory=list, title="Hosts")
    # TODO this should use task types enum
    task_types: list[str] = Field(default_factory=list, title="Task types")
    task_names: list[str] = Field(default_factory=list, title="Task names")
    enabled: bool = Field(True, title="Enabled")
    use_last_published_workfile: bool = Field(
        True, title="Use last published workfile"
    )


class WorkfilesToolOnStartupProfile(BaseSettingsModel):
    _layout = "expanded"
    # TODO this should use hosts enum
    hosts: list[str] = Field(default_factory=list, title="Hosts")
    # TODO this should use task types enum
    task_types: list[str] = Field(default_factory=list, title="Task types")
    task_names: list[str] = Field(default_factory=list, title="Task names")
    enabled: bool = Field(True, title="Enabled")


class ExtraWorkFoldersProfile(BaseSettingsModel):
    _layout = "expanded"
    # TODO this should use hosts enum
    hosts: list[str] = Field(default_factory=list, title="Hosts")
    # TODO this should use task types enum
    task_types: list[str] = Field(default_factory=list, title="Task types")
    task_names: list[str] = Field(default_factory=list, title="Task names")
    folders: list[str] = Field(default_factory=list, title="Folders")


class WorkfilesLockProfile(BaseSettingsModel):
    _layout = "expanded"
    # TODO this should use hosts enum
    host_names: list[str] = Field(default_factory=list, title="Hosts")
    enabled: bool = Field(True, title="Enabled")


class WorkfilesToolModel(BaseSettingsModel):
    workfile_template_profiles: list[WorkfileTemplateProfile] = Field(
        default_factory=list,
        title="Workfile template profiles"
    )
    last_workfile_on_startup: list[LastWorkfileOnStartupProfile] = Field(
        default_factory=list,
        title="Open last workfiles on launch"
    )
    open_workfile_tool_on_startup: list[WorkfilesToolOnStartupProfile] = Field(
        default_factory=list,
        title="Open workfile tool on launch"
    )
    extra_folders: list[ExtraWorkFoldersProfile] = Field(
        default_factory=list,
        title="Extra work folders"
    )
    workfile_lock_profiles: list[WorkfilesLockProfile] = Field(
        default_factory=list,
        title="Workfile lock profiles"
    )


def published_families():
    return [
        "action",
        "animation",
        "assembly",
        "audio",
        "backgroundComp",
        "backgroundLayout",
        "camera",
        "editorial",
        "gizmo",
        "image",
        "layout",
        "look",
        "matchmove",
        "mayaScene",
        "model",
        "nukenodes",
        "plate",
        "pointcache",
        "prerender",
        "redshiftproxy",
        "reference",
        "render",
        "review",
        "rig",
        "setdress",
        "take",
        "usdShade",
        "vdbcache",
        "vrayproxy",
        "workfile",
        "xgen",
        "yetiRig",
        "yeticache"
    ]


class LoaderFamilyFilterProfile(BaseSettingsModel):
    _layout = "expanded"
    # TODO this should use hosts enum
    hosts: list[str] = Field(default_factory=list, title="Hosts")
    # TODO this should use task types enum
    task_types: list[str] = Field(default_factory=list, title="Task types")
    is_include: bool = Field(True, title="Exclude / Include")
    template_publish_families: list[str] = Field(
        default_factory=list,
        enum_resolver=published_families
    )


class LoaderToolModel(BaseSettingsModel):
    family_filter_profiles: list[LoaderFamilyFilterProfile] = Field(
        default_factory=list,
        title="Family filtering"
    )


class PublishTemplateNameProfile(BaseSettingsModel):
    _layout = "expanded"
    families: list[str] = Field(default_factory=list, title="Families")
    # TODO this should use hosts enum
    hosts: list[str] = Field(default_factory=list, title="Hosts")
    # TODO this should use task types enum
    task_types: list[str] = Field(default_factory=list, title="Task types")
    task_names: list[str] = Field(default_factory=list, title="Task names")
    template_name: str = Field("", title="Template name")


class PublishToolModel(BaseSettingsModel):
    template_name_profiles: list[PublishTemplateNameProfile] = Field(
        default_factory=list,
        title="Template name profiles"
    )
    hero_template_name_profiles: list[PublishTemplateNameProfile] = Field(
        default_factory=list,
        title="Hero template name profiles"
    )


class GlobalToolsModel(BaseSettingsModel):
    creator: CreatorToolModel = Field(
        default_factory=CreatorToolModel,
        title="Creator"
    )
    Workfiles: WorkfilesToolModel = Field(
        default_factory=WorkfilesToolModel,
        title="Workfiles"
    )
    loader: LoaderToolModel = Field(
        default_factory=LoaderToolModel,
        title="Loader"
    )
    publish: PublishToolModel = Field(
        default_factory=PublishToolModel,
        title="Publish"
    )


DEFAULT_TOOLS_VALUES = {
    "creator": {
        "families_smart_select": [
            {
                "name": "Render",
                "task_names": [
                    "light",
                    "render"
                ]
            },
            {
                "name": "Model",
                "task_names": [
                    "model"
                ]
            },
            {
                "name": "Layout",
                "task_names": [
                    "layout"
                ]
            },
            {
                "name": "Look",
                "task_names": [
                    "look"
                ]
            },
            {
                "name": "Rig",
                "task_names": [
                    "rigging",
                    "rig"
                ]
            }
        ],
        "subset_name_profiles": [
            {
                "families": [],
                "hosts": [],
                "task_types": [],
                "tasks": [],
                "template": "{family}{variant}"
            },
            {
                "families": [
                    "workfile"
                ],
                "hosts": [],
                "task_types": [],
                "tasks": [],
                "template": "{family}{Task}"
            },
            {
                "families": [
                    "render"
                ],
                "hosts": [],
                "task_types": [],
                "tasks": [],
                "template": "{family}{Task}{Variant}"
            },
            {
                "families": [
                    "renderLayer",
                    "renderPass"
                ],
                "hosts": [
                    "tvpaint"
                ],
                "task_types": [],
                "tasks": [],
                "template": "{family}{Task}_{Renderlayer}_{Renderpass}"
            },
            {
                "families": [
                    "review",
                    "workfile"
                ],
                "hosts": [
                    "aftereffects",
                    "tvpaint"
                ],
                "task_types": [],
                "tasks": [],
                "template": "{family}{Task}"
            },
            {
                "families": ["render"],
                "hosts": [
                    "aftereffects"
                ],
                "task_types": [],
                "tasks": [],
                "template": "{family}{Task}{Composition}{Variant}"
            },
            {
                "families": [
                    "staticMesh"
                ],
                "hosts": [
                    "maya"
                ],
                "task_types": [],
                "tasks": [],
                "template": "S_{asset}{variant}"
            },
            {
                "families": [
                    "skeletalMesh"
                ],
                "hosts": [
                    "maya"
                ],
                "task_types": [],
                "tasks": [],
                "template": "SK_{asset}{variant}"
            }
        ]
    },
    "Workfiles": {
        "workfile_template_profiles": [
            {
                "task_types": [],
                "hosts": [],
                "workfile_template": "work"
            },
            {
                "task_types": [],
                "hosts": [
                    "unreal"
                ],
                "workfile_template": "unreal"
            }
        ],
        "last_workfile_on_startup": [
            {
                "hosts": [],
                "task_types": [],
                "tasks": [],
                "enabled": True,
                "use_last_published_workfile": False
            }
        ],
        "open_workfile_tool_on_startup": [
            {
                "hosts": [],
                "task_types": [],
                "tasks": [],
                "enabled": False
            }
        ],
        "extra_folders": [],
        "workfile_lock_profiles": []
    },
    "loader": {
        "family_filter_profiles": [
            {
                "hosts": [],
                "task_types": [],
                "is_include": True,
                "filter_families": []
            }
        ]
    },
    "publish": {
        "template_name_profiles": [],
        "hero_template_name_profiles": []
    }
}
