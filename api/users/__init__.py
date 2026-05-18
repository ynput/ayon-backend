__all__ = ["router"]

from . import apikeys, avatar, invite, password_reset, permissions, users
from .router import router

_ = (
    apikeys,
    avatar,
    invite,
    password_reset,
    permissions,
    users,
)
