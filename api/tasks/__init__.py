__all__ = ["router"]

from . import grouping, tasks
from .router import router

_ = tasks, grouping  # Importing to ensure they are registered with the router
