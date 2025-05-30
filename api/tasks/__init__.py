__all__ = ["router"]

from . import tasks
from .router import router

_ = tasks  # Importing to ensure they are registered with the router
