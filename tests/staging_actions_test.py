import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from api.actions.actions import ensure_action_variant_access
from ayon_server.actions import listing
from ayon_server.exceptions import ForbiddenException


def make_user(
    *,
    is_developer: bool = False,
    developer_mode: bool = False,
    allow_staging_mode: bool = False,
):
    return SimpleNamespace(
        is_developer=is_developer,
        name="artist",
        updated_at="2026-06-08T00:00:00Z",
        attrib=SimpleNamespace(
            developerMode=developer_mode,
            allowStagingMode=allow_staging_mode,
        ),
    )


def test_can_access_staging_actions_for_developer_mode():
    user = make_user(is_developer=True, developer_mode=True)

    assert listing.can_access_staging_actions(user) is True


def test_can_access_staging_actions_for_allow_staging_flag():
    user = make_user(allow_staging_mode=True)

    assert listing.can_access_staging_actions(user) is True


def test_sanitize_action_variant_falls_back_to_production():
    user = make_user()

    assert listing.sanitize_action_variant("staging", user) == "production"


def test_ensure_action_variant_access_rejects_unauthorized_staging():
    user = make_user()

    try:
        ensure_action_variant_access(user, "staging")
    except ForbiddenException as exc:
        assert exc.status == 403
        assert "staging actions" in exc.detail
    else:
        raise AssertionError("Expected unauthorized staging access to fail")


def test_ensure_action_variant_access_allows_flagged_user():
    user = make_user(allow_staging_mode=True)

    ensure_action_variant_access(user, "staging")


def test_get_relevant_addons_preserves_staging_for_allowed_user():
    user = make_user(allow_staging_mode=True)
    captured: list[str | None] = []

    async def fake_load_relevant_addons(user_name, variant, is_developer, user_last_modified):
        captured.append(variant)
        return variant or "production", []

    original = listing._load_relevant_addons
    listing._load_relevant_addons = fake_load_relevant_addons
    try:
        variant, addons = asyncio.run(listing.get_relevant_addons("staging", user))
    finally:
        listing._load_relevant_addons = original

    assert variant == "staging"
    assert addons == []
    assert captured == ["staging"]


def test_get_relevant_addons_downgrades_staging_for_unauthorized_user():
    user = make_user()
    captured: list[str | None] = []

    async def fake_load_relevant_addons(user_name, variant, is_developer, user_last_modified):
        captured.append(variant)
        return variant or "production", []

    original = listing._load_relevant_addons
    listing._load_relevant_addons = fake_load_relevant_addons
    try:
        variant, addons = asyncio.run(listing.get_relevant_addons("staging", user))
    finally:
        listing._load_relevant_addons = original

    assert variant == "production"
    assert addons == []
    assert captured == ["production"]
