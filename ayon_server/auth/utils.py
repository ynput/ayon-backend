from ayon_server.config import ayonconfig
from ayon_server.exceptions import LowPasswordComplexityException
from ayon_server.utils import create_hash, hash_data


def validate_password(password: str) -> None:
    """
    Simple password policy which checks whether the given password's
    lenght is greater or equal to auth_pass_min_length config value.

    When auth_pass_complex is set to True, the password is also checked
    whether it contains letters, numbers and special characters.

    """
    if len(password) < ayonconfig.auth_pass_min_length:
        raise LowPasswordComplexityException(
            "Password must be at least "
            f"{ayonconfig.auth_pass_min_length} characters long"
        )
    if ayonconfig.auth_pass_complex:
        # Ensure password has digits, letters and special characters
        if not any(c.isalpha() for c in password):
            raise LowPasswordComplexityException("Password must contain letters")
        if not any(c.isdigit() for c in password):
            raise LowPasswordComplexityException("Password must contain digits")
        if not any(c in ".-!@#$%^&*()_+" for c in password):
            raise LowPasswordComplexityException(
                "Password must contain special characters"
            )


def ensure_password_complexity(password: str) -> bool:
    try:
        validate_password(password)
    except LowPasswordComplexityException:
        return False
    return True


def hash_password(password: str, salt: str = "") -> str:
    """Create a hash string from a given password and salt,
    and pepper from the config.
    """
    return hash_data(f"{password}:{salt}:{ayonconfig.auth_pass_pepper}")


def create_password(password: str) -> str:
    """Create a hash:salt string from a given password."""
    salt = create_hash()
    pass_hash = hash_password(password, salt)
    return f"{pass_hash}:{salt}"
