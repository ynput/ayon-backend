import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from api.links.links import _can_delete_foreign_link
from ayon_server.access.access_groups import AccessGroups
from ayon_server.access.permissions import Permissions


class TestLinkPermissions:
    def setup_method(self):
        AccessGroups.access_groups = {}

    def test_combine_merges_link_delete_permission_and_types(self):
        AccessGroups.add_access_group(
            "artists",
            "_",
            Permissions(
                links={
                    "enabled": True,
                    "link_types": ["reference|folder|version"],
                }
            ),
        )
        AccessGroups.add_access_group(
            "reviewers",
            "_",
            Permissions(
                links={
                    "enabled": True,
                    "delete_others": True,
                    "link_types": ["breakdown|folder|folder"],
                }
            ),
        )

        permissions = AccessGroups.combine(["artists", "reviewers"])

        assert permissions.links.delete_others is True
        assert set(permissions.links.link_types) == {
            "reference|folder|version",
            "breakdown|folder|folder",
        }

    def test_delete_foreign_link_requires_explicit_permission(self):
        permissions = Permissions()

        assert (
            _can_delete_foreign_link(permissions, "reference|folder|version") is False
        )

    def test_delete_foreign_link_respects_link_restrictions(self):
        permissions = Permissions(
            links={
                "enabled": True,
                "delete_others": True,
                "link_types": ["reference|folder|version"],
            }
        )

        assert (
            _can_delete_foreign_link(permissions, "reference|folder|version") is True
        )
        assert _can_delete_foreign_link(permissions, "breakdown|folder|folder") is False

    def test_delete_foreign_link_can_apply_to_all_link_types(self):
        permissions = Permissions(
            links={
                "delete_others": True,
            }
        )

        assert _can_delete_foreign_link(permissions, "reference|folder|version") is True
