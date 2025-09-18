# Backward compatibility for old import paths

__all__ = ["ExternalUsers", "ExternalUserStatus"]

from .guest_users import GuestUsers as ExternalUsers
from .guest_users import GuestUserStatus as ExternalUserStatus
