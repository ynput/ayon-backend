__all__ = ["router"]

from . import (
    activity,
    activity_categories,
    reactions,
    suggest,
    watchers,
)
from .router import router

_ = activity, activity_categories, reactions, suggest, watchers
