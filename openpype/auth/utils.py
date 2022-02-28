from openpype.utils import create_hash, hash_data
from openpype.config import pypeconfig


def ensure_password_complexity(password: str) -> bool:
    """
    Ensure password complexity.

    This is a very simple password policy.
    """
    if len(password) < pypeconfig.auth_pass_min_length:
        return False
    if pypeconfig.auth_pass_complex:
        # Ensure password has digits, letters and special characters
        if not any(c.isalnum() for c in password):
            return False
        if not any(c in ".-!@#$%^&*()_+" for c in password):
            return False
    return True


def hash_password(password: str, salt: str) -> str:
    return hash_data(f"{password}:{salt}:{pypeconfig.auth_pass_pepper}")


def create_password(password: str) -> str:
    """Create a hash:salt string from a given password."""
    salt = create_hash()
    pass_hash = hash_password(password, salt)
    return f"{pass_hash}:{salt}"
