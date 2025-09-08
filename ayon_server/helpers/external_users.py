# Backward compatibility for old import paths

__all__ = ["ExternalUsers"]

from .guest_users import GuestUsers as ExternalUsers
