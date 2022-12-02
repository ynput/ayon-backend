from pydantic import Field, validator
from openpype.settings import (
    BaseSettingsModel,
    normalize_name,
    ensure_unique_names,
)


class MultiplatformStr(BaseSettingsModel):
    windows: str = Field("", title="Windows")
    linux: str = Field("", title="Linux")
    darwin: str = Field("", title="MacOS")


class ValidateBaseModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = Field(True)
    optional: bool = Field(True, title="Optional")
    active: bool = Field(True, title="Active")


class CollectAnatomyInstanceDataModel(BaseSettingsModel):
    _isGroup = True
    follow_workfile_version: bool = Field(
        True, title="Collect Anatomy Instance Data"
    )


class CollectAudioModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = Field(True)
    audio_subset_name: str = Field(
        "", title="Name of audio variant"
    )


class CollectSceneVersionModel(BaseSettingsModel):
    _isGroup = True
    hosts: list[str] = Field(
        default_factory=list,
        title="Host names"
    )
    skip_hosts_headless_publish: list[str] = Field(
        default_factory=list,
        title="Skip for host if headless publish"
    )


class ValidateIntentProfile(BaseSettingsModel):
    _layout = "expanded"
    hosts: list[str] = Field(default_factory=list, title="Host names")
    task_types: list[str] = Field(default_factory=list, title="Task types")
    tasks: list[str] = Field(default_factory=list, title="Task names")
    # TODO This was 'validate' in v3
    validate_intent: bool = Field(True, title="Validate")


class ValidateIntentModel(BaseSettingsModel):
    """Validate if Publishing intent was selected.

    It is possible to disable validation for specific publishing context
    with profiles.
    """

    _isGroup = True
    enabled: bool = Field(False)
    profiles: list[ValidateIntentProfile] = Field(default_factory=list)


class ExtractThumbnailFFmpegModel(BaseSettingsModel):
    _layout = "expanded"
    input: list[str] = Field(
        default_factory=list,
        title="FFmpeg input arguments"
    )
    output: list[str] = Field(
        default_factory=list,
        title="FFmpeg input arguments"
    )


class ExtractThumbnailModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = Field(True)
    ffmpeg_args: ExtractThumbnailFFmpegModel = Field(
        default_factory=ExtractThumbnailFFmpegModel
    )


# --- [START] Extract Review ---
class ExtractReviewFFmpegModel(BaseSettingsModel):
    video_filters: list[str] = Field(
        default_factory=list,
        title="Video filters"
    )
    audio_filters: list[str] = Field(
        default_factory=list,
        title="Audio filters"
    )
    input: list[str] = Field(
        default_factory=list,
        title="Input arguments"
    )
    output: list[str] = Field(
        default_factory=list,
        title="Output arguments"
    )


def extract_review_filter_enum():
    return [
        {
            "value": "everytime",
            "label": "Always"
        },
        {
            "value": "single_frame",
            "label": "Only if input has 1 image frame"
        },
        {
            "value": "multi_frame",
            "label": "Only if input is video or sequence of frames"
        }
    ]


class ExtractReviewFilterModel(BaseSettingsModel):
    families: list[str] = Field(default_factory=list, title="Families")
    subsets: list[str] = Field(default_factory=list, title="Subsets")
    custom_tags: list[str] = Field(default_factory=list, title="Custom Tags")
    single_frame_filter: str = Field(
        "everytime",
        description=(
            "Use output <b>always</b> / only if input <b>is 1 frame</b>"
            " image / only if has <b>2+ frames</b> or <b>is video</b>"
        ),
        enum_resolver=extract_review_filter_enum
    )


class ExtractReviewLetterBox(BaseSettingsModel):
    enabled: bool = Field(True)
    ratio: float = Field(
        0.0,
        title="Ratio",
        ge=0.0,
        le=10000.0
    )
    # TODO color should have alpha
    fill_color: str = Field(
        "",
        title="Fill Color",
        widget="color",
    )
    line_thickness: int = Field(
        0,
        title="Line Thickness",
        ge=0,
        le=1000
    )
    # TODO color should have alpha
    line_color: str = Field(
        "",
        title="Line Color",
        widget="color"
    )


class ExtractReviewOutputDefModel(BaseSettingsModel):
    _layout = "expanded"
    name: str = Field("", title="Name")
    ext: str = Field("", title="Output extension")
    # TODO use some different source of tags
    tags: list[str] = Field(default_factory=list, title="Tags")
    burnins: list[str] = Field(
        default_factory=list, title="Link to a burnin by name"
    )
    ffmpeg_args: ExtractReviewFFmpegModel = Field(
        default_factory=ExtractReviewFFmpegModel,
        title="FFmpeg arguments"
    )
    filter: ExtractReviewFilterModel = Field(
        default_factory=ExtractReviewFilterModel,
        title="Additional output filtering"
    )
    overscan_crop: str = Field(
        "",
        title="Overscan crop",
        description=(
            "Crop input overscan. See the documentation for more information."
        )
    )
    overscan_color: str = Field(
        "",
        title="Overscan color",
        widget="color",
        description=(
            "Overscan color is used when input aspect ratio is not"
            " same as output aspect ratio."
        )
    )
    output_width: int = Field(
        0,
        ge=0,
        le=100000,
        title="Output width",
        description=(
            "Width and Height must be both set to higher"
            " value than 0 else source resolution is used."
        )
    )
    output_height: int = Field(
        0,
        title="Output height",
        ge=0,
        le=100000,
    )
    scale_pixel_aspect: bool = Field(
        True,
        title="Scale pixel aspect",
        description=(
            "Rescale input when it's pixel aspect ratio is not 1."
            " Usefull for anamorph reviews."
        )
    )
    bg_color: str = Field(
        "",
        widget="color",
        description=(
            "Background color is used only when input have transparency"
            " and Alpha is higher than 0."
        ),
        title="Background color",
    )
    letter_box: ExtractReviewLetterBox = Field(
        default_factory=ExtractReviewLetterBox,
        title="Letter Box"
    )

    @validator("name")
    def validate_name(cls, value):
        """Ensure name does not contain weird characters"""
        return normalize_name(value)


class ExtractReviewProfileModel(BaseSettingsModel):
    _layout = "expanded"
    families: list[str] = Field(
        default_factory=list, title="Families"
    )
    # TODO use hosts enum
    hosts: list[str] = Field(
        default_factory=list, title="Host names"
    )
    outputs: list[ExtractReviewOutputDefModel] = Field(
        default_factory=list, title="Output Definitions"
    )

    @validator("outputs")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


class ExtractReviewModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = Field(True)
    profiles: list[ExtractReviewProfileModel] = Field(
        default_factory=list,
        title="Profiles"
    )
# --- [END] Extract Review ---


# --- [Start] Extract Burnin ---
class ExtractBurninOptionsModel(BaseSettingsModel):
    font_size: int = Field(0, ge=0, title="Font size")
    font_color: str = Field(
        "",
        widget="color",
        title="Font color"
    )
    bg_color: str = Field(
        "",
        widget="color",
        title="Background color"
    )
    x_offset: int = Field(0, title="X Offset")
    y_offset: int = Field(0, title="Y Offset")
    bg_padding: int = Field(0, title="Padding around text")
    font_filepath: MultiplatformStr = Field(
        default_factory=MultiplatformStr,
        title="Font file path"
    )


class ExtractBurninDefFilter(BaseSettingsModel):
    families: list[str] = Field(
        default_factory=list,
        title="Families"
    )
    tags: list[str] = Field(
        default_factory=list,
        title="Tags"
    )


class ExtractBurninDef(BaseSettingsModel):
    _isGroup = True
    _layout = "expanded"
    name: str = Field("")
    TOP_LEFT: str = Field("", topic="Top Left")
    TOP_CENTERED: str = Field("", topic="Top Centered")
    TOP_RIGHT: str = Field("", topic="Top Right")
    BOTTOM_LEFT: str = Field("", topic="Bottom Left")
    BOTTOM_CENTERED: str = Field("", topic="Bottom Centered")
    BOTTOM_RIGHT: str = Field("", topic="Bottom Right")
    filter: ExtractBurninDefFilter = Field(
        default_factory=ExtractBurninDefFilter,
        title="Additional filtering"
    )

    @validator("name")
    def validate_name(cls, value):
        """Ensure name does not contain weird characters"""
        return normalize_name(value)


class ExtractBurninProfile(BaseSettingsModel):
    _layout = "expanded"
    families: list[str] = Field(
        default_factory=list,
        title="Families"
    )
    hosts: list[str] = Field(
        default_factory=list,
        title="Host names"
    )
    burnins: list[ExtractBurninDef] = Field(
        default_factory=list,
        title="Burnins"
    )

    @validator("burnins")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)

        return value


class ExtractBurninModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = Field(True)
    options: ExtractBurninOptionsModel = Field(
        default_factory=ExtractBurninOptionsModel,
        title="Burnin formatting options"
    )
    profiles: list[ExtractBurninProfile] = Field(
        default_factory=list,
        title="Profiles"
    )
# --- [END] Extract Burnin ---


class PreIntegrateThumbnailsProfile(BaseSettingsModel):
    _isGroup = True
    families: list[str] = Field(
        default_factory=list,
        title="Families",
    )
    hosts: list[str] = Field(
        default_factory=list,
        title="Hosts",
    )
    task_types: list[str] = Field(
        default_factory=list,
        title="Task types",
    )
    subsets: list[str] = Field(
        default_factory=list,
        title="Subsets",
    )
    integrate_thumbnail: bool = Field(True)


class PreIntegrateThumbnailsModel(BaseSettingsModel):
    """Explicitly set if Thumbnail representation should be integrated.

    If no matching profile set, existing state from Host implementation is kept.
    """

    _isGroup = True
    enabled: bool = Field(True)
    integrate_profiles: list[PreIntegrateThumbnailsProfile] = Field(
        default_factory=list,
        title="Integrate profiles"
    )


class IntegrateSubsetGroupProfile(BaseSettingsModel):
    families: list[str] = Field(default_factory=list, title="Families")
    hosts: list[str] = Field(default_factory=list, title="Hosts")
    task_types: list[str] = Field(default_factory=list, title="Task types")
    tasks: list[str] = Field(default_factory=list, title="Task names")
    template: str = Field("", title="Template")


class IntegrateSubsetGroupModel(BaseSettingsModel):
    """Group published subsets by filtering logic.

    Set all published instances as a part of specific group named according
     to 'Template'.

    Implemented all variants of placeholders '{task}', '{family}', '{host}',
    '{subset}', '{renderlayer}'.
    """

    _isGroup = True
    subset_grouping_profiles: list[IntegrateSubsetGroupProfile] = Field(
        default_factory=list,
        title="Subset group profiles"
    )


class IntegrateHeroVersionModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = Field(True)
    optional: bool = Field(False, title="Optional")
    active: bool = Field(True, title="Active")
    families: list[str] = Field(default_factory=list, title="Families")
    # TODO this has been removed as is marked as deprecated
    # template_name_profiles: list[str] = Field(
    #     default_factory=list,
    #     title="Template name profiles"
    # )


class CleanUpModel(BaseSettingsModel):
    _isGroup = True
    patterns: list[str] = Field(
        default_factory=list,
        title="Patterns (regex)"
    )
    remove_temp_renders: bool = Field(False, title="Remove Temp renders")


class CleanUpFarmModel(BaseSettingsModel):
    _isGroup = True
    enabled: bool = Field(True)


class PublishPuginsModel(BaseSettingsModel):
    CollectAnatomyInstanceData: CollectAnatomyInstanceDataModel = Field(
        default_factory=CollectAnatomyInstanceDataModel,
        title="Collect Anatomy Instance Data"
    )
    CollectAudio: CollectAudioModel = Field(
        default_factory=CollectAudioModel,
        title="Collect Audio"
    )
    CollectSceneVersion: CollectSceneVersionModel = Field(
        default_factory=CollectSceneVersionModel,
        title="Collect Version from Workfile"
    )
    ValidateEditorialAssetName: ValidateBaseModel = Field(
        default_factory=ValidateBaseModel,
        title="Validate Editorial Asset Name"
    )
    ValidateVersion: ValidateBaseModel = Field(
        default_factory=ValidateBaseModel,
        title="Validate Version"
    )
    ValidateIntent: ValidateIntentModel = Field(
        default_factory=ValidateIntentModel,
        title="Validate Intent"
    )
    ExtractThumbnail: ExtractThumbnailModel = Field(
        default_factory=ExtractThumbnailModel,
        title="Extract Thumbnail"
    )
    ExtractReview: ExtractReviewModel = Field(
        default_factory=ExtractReviewModel,
        title="Extract Review"
    )
    ExtractBurnin: ExtractBurninModel = Field(
        default_factory=ExtractBurninModel,
        title="Extract Burnin"
    )
    IntegrateSubsetGroup: IntegrateSubsetGroupModel = Field(
        default_factory=IntegrateSubsetGroupModel,
        title="Integrate Subset Group"
    )
    # TODO these keys have been removed
    # IntegrateAssetNew
    # IntegrateAsset
    IntegrateHeroVersion: IntegrateHeroVersionModel = Field(
        default_factory=IntegrateHeroVersionModel,
        title="Integrate Hero Version"
    )
    CleanUp: CleanUpModel = Field(
        default_factory=CleanUpModel,
        title="Clean Up"
    )
    CleanUpFarm: CleanUpFarmModel = Field(
        default_factory=CleanUpFarmModel,
        title="Clean Up Farm"
    )


DEFAULT_PUBLISH_VALUES = {
    "CollectAnatomyInstanceData": {
        "follow_workfile_version": False
    },
    "CollectAudio": {
        "enabled": False,
        "audio_subset_name": "audioMain"
    },
    "CollectSceneVersion": {
        "hosts": [
            "aftereffects",
            "blender",
            "celaction",
            "fusion",
            "harmony",
            "hiero",
            "houdini",
            "maya",
            "nuke",
            "photoshop",
            "resolve",
            "tvpaint"
        ],
        "skip_hosts_headless_publish": []
    },
    "ValidateEditorialAssetName": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateVersion": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateIntent": {
        "enabled": False,
        "profiles": []
    },
    "ExtractThumbnail": {
        "enabled": True,
        "ffmpeg_args": {
            "input": [
                "-apply_trc gamma22"
            ],
            "output": []
        }
    },
    "ExtractReview": {
        "enabled": True,
        "profiles": [
            {
                "families": [],
                "hosts": [],
                "outputs": [
                    {
                        "name": "png",
                        "ext": "png",
                        "tags": [
                            "ftrackreview"
                        ],
                        "burnins": [],
                        "ffmpeg_args": {
                            "video_filters": [],
                            "audio_filters": [],
                            "input": [],
                            "output": []
                        },
                        "filter": {
                            "families": [
                                "render",
                                "review",
                                "ftrack"
                            ],
                            "subsets": [],
                            "custom_tags": [],
                            "single_frame_filter": "single_frame"
                        },
                        "overscan_crop": "",
                        "overscan_color": "#000000",
                        "width": 1920,
                        "height": 1080,
                        "scale_pixel_aspect": True,
                        "bg_color": "#000000",
                        "letter_box": {
                            "enabled": False,
                            "ratio": 0.0,
                            "fill_color": "#000000",
                            "line_thickness": 0,
                            "line_color": "#ff0000"
                        }
                    },
                    {
                        "name": "h264",
                        "ext": "mp4",
                        "tags": [
                            "burnin",
                            "ftrackreview"
                        ],
                        "burnins": [],
                        "ffmpeg_args": {
                            "video_filters": [],
                            "audio_filters": [],
                            "input": [
                                "-apply_trc gamma22"
                            ],
                            "output": [
                                "-pix_fmt yuv420p",
                                "-crf 18",
                                "-intra"
                            ]
                        },
                        "filter": {
                            "families": [
                                "render",
                                "review",
                                "ftrack"
                            ],
                            "subsets": [],
                            "custom_tags": [],
                            "single_frame_filter": "multi_frame"
                        },
                        "overscan_crop": "",
                        "overscan_color": "#000000",
                        "width": 0,
                        "height": 0,
                        "scale_pixel_aspect": True,
                        "bg_color": "#000000",
                        "letter_box": {
                            "enabled": False,
                            "ratio": 0.0,
                            "fill_color": "#000000",
                            "line_thickness": 0,
                            "line_color": "#ff0000"
                        }
                    }
                ]
            }
        ]
    },
    "ExtractBurnin": {
        "enabled": True,
        "options": {
            "font_size": 42,
            "font_color": "#ffffff",
            "bg_color": "#000000",
            "x_offset": 5,
            "y_offset": 5,
            "bg_padding": 5,
            "font_filepath": {
                "windows": "",
                "darwin": "",
                "linux": ""
            }
        },
        "profiles": [
            {
                "families": [],
                "hosts": [],
                "burnins": [
                    {
                        "name": "burnin",
                        "TOP_LEFT": "{yy}-{mm}-{dd}",
                        "TOP_CENTERED": "",
                        "TOP_RIGHT": "{anatomy[version]}",
                        "BOTTOM_LEFT": "{username}",
                        "BOTTOM_CENTERED": "{asset}",
                        "BOTTOM_RIGHT": "{frame_start}-{current_frame}-{frame_end}",
                        "filter": {
                            "families": [],
                            "tags": []
                        }
                    }
                ]
            }
        ]
    },
    "PreIntegrateThumbnails": {
        "enabled": True,
        "integrate_profiles": []
    },
    "IntegrateSubsetGroup": {
        "subset_grouping_profiles": [
            {
                "families": [],
                "hosts": [],
                "task_types": [],
                "tasks": [],
                "template": ""
            }
        ]
    },
    "IntegrateHeroVersion": {
        "enabled": True,
        "optional": True,
        "active": True,
        "families": [
            "model",
            "rig",
            "look",
            "pointcache",
            "animation",
            "setdress",
            "layout",
            "mayaScene",
            "simpleUnrealTexture"
        ]
    },
    "CleanUp": {
        "paterns": [],
        "remove_temp_renders": False
    },
    "CleanUpFarm": {
        "enabled": False
    }
}