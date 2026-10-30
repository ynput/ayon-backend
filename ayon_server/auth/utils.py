import hashlib
import hmac
import secrets

from ayon_server.config import ayonconfig
from ayon_server.exceptions import LowPasswordComplexityException
from ayon_server.utils import hash_data

SCRYPT_PREFIX = "scrypt:"


def validate_password(password: str) -> None:
    """
    Simple password policy which checks whether the given password's
    lenght is greater or equal to auth_pass_min_length config value.

    When auth_pass_complex is set to True, the password is also checked
    whether it contains letters, numbers and special characters.

    """
    problems = []
    misses = []

    if len(password) < ayonconfig.auth_pass_min_length:
        problems.append(f"be at least {ayonconfig.auth_pass_min_length} characters")
    if ayonconfig.auth_pass_complex:
        # Ensure password has digits, letters and special characters
        if not any(c.isalpha() for c in password):
            misses.append("letters")
        if not any(c.isdigit() for c in password):
            misses.append("digits")
        if not any(c in ".-!@#$%^&*()_+" for c in password):
            misses.append("special characters")

    if misses:
        if len(misses) == 1:
            problems.append(f"contain {misses[0]}")
        else:
            problems.append("contain " + ", ".join(misses[:-1]) + f" and {misses[-1]}")
    if problems:
        message = "Password must " + " and ".join(problems) + "."
        raise LowPasswordComplexityException(message)
    return


def hash_password(password: str, salt: str = "") -> str:
    """Create a fast SHA-256 hash of a secret, salt and the pepper.

    Used for API keys (random, so a slow hash is not needed, and looked up
    by the hash) and to verify passwords stored in the legacy format.
    """
    return hash_data(f"{password}:{salt}:{ayonconfig.auth_pass_pepper}")


def _scrypt(password: str, salt: str) -> str:
    secret = f"{password}:{ayonconfig.auth_pass_pepper}".encode()
    return hashlib.scrypt(secret, salt=salt.encode(), n=2**14, r=8, p=1).hex()


def create_password(password: str) -> str:
    """Create a stored password string ("scrypt:hash:salt")."""
    salt = secrets.token_hex(16)
    return f"{SCRYPT_PREFIX}{_scrypt(password, salt)}:{salt}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a create_password result or a legacy hash:salt."""
    if stored.startswith(SCRYPT_PREFIX):
        pass_hash, salt = stored.removeprefix(SCRYPT_PREFIX).split(":")
        expected = _scrypt(password, salt)
    else:
        pass_hash, salt = stored.split(":")
        expected = hash_password(password, salt)
    return hmac.compare_digest(pass_hash, expected)


def needs_rehash(stored: str) -> bool:
    """Return True for passwords stored in the legacy (fast hash) format."""
    return not stored.startswith(SCRYPT_PREFIX)
