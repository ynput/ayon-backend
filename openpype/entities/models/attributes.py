"""
DEPRECATED. For reference only
"""

from .constants import NAME_REGEX

# Common attributes
# shared by projects, folders and versions

common_attributes = [
    {
        "name": "fps",
        "type": "float",
        "title": "FPS",
        "description": "Frame rate",
        "example": 23.976,
        "gt": 0,
    },
    {
        "name": "resolutionWidth",
        "type": "integer",
        "title": "Width",
        "description": "Horizontal resolution",
        "example": 1920,
        "gt": 0,
    },
    {
        "name": "resolutionHeight",
        "type": "integer",
        "title": "Height",
        "description": "Vertical resoulution",
        "example": 1080,
        "gt": 0,
    },
    {
        "name": "pixelAspect",
        "type": "float",
        "example": 1.0,
    },
    {
        "name": "clipIn",
        "type": "integer",
        "title": "Clip in",
    },
    {
        "name": "clipOut",
        "type": "integer",
        "title": "Clip out",
    },
    {"name": "handles", "type": "integer"},
    {"name": "frameStart", "type": "integer"},
    {"name": "frameEnd", "type": "integer"},
    {"name": "handleStart", "type": "integer"},
    {"name": "handleEnd", "type": "integer"},
]


#
# Entity attribute sets
#

user_attributes = [
    {
        "name": "fullname",
        "type": "string",
    },
    {
        "name": "email",
        "type": "string",
    },
    {
        "name": "avatar_url",
        "type": "string",
    },
]

project_attributes = common_attributes + [
    # project specific attributes
]

folder_attributes = common_attributes + [
    # folder specific attributes
]

task_attributes = common_attributes + [
    # Task specific attributes
]

subset_attributes = [
    {
        "name": "subsetGroup",
        "type": "string",
        "regex": NAME_REGEX,
    }
]


version_attributes = common_attributes + [
    {"name": "intent"},
    {"name": "source"},
    {"name": "comment"},
    {
        "name": "machine",
    },
    {"name": "families", "type": "list_of_strings"},
    {"name": "colorspace", "type": "string", "example": "rec708"},
]


representation_attributes = [{"name": "path"}, {"name": "template"}]
