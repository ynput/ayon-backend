from ayon_server.auth.utils import (
    create_password,
    hash_password,
    needs_rehash,
    verify_password,
)


def test_new_password() -> None:
    stored = create_password("correct horse")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong horse", stored)
    assert not needs_rehash(stored)
    # every password gets its own salt
    assert create_password("correct horse") != stored


def test_legacy_password() -> None:
    """Passwords hashed before scrypt still work and are marked for rehashing."""
    stored = f"{hash_password('correct horse', 'salt')}:salt"
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong horse", stored)
    assert needs_rehash(stored)
