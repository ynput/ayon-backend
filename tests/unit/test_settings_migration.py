from ayon_server.settings import BaseSettingsModel, SettingsField
from ayon_server.settings.common import migrate_settings_overrides
from ayon_server.settings.pydantic_compat import validator


class Sub(BaseSettingsModel):
    name: str = SettingsField("")
    limit: int = SettingsField(1, ge=0, le=10)


class Settings(BaseSettingsModel):
    s: str = SettingsField("")
    ls: list[str] = SettingsField(default_factory=list)
    n: int = SettingsField(0, ge=0, le=10)
    f: int = SettingsField(0)
    b: str = SettingsField("")
    code: str = SettingsField("abc", regex="^[a-z]+$")
    sub: Sub = SettingsField(default_factory=Sub)
    items: list[Sub] = SettingsField(default_factory=list)
    even: int = SettingsField(0)
    keep: str = SettingsField("")

    @validator("even")
    def check_even(cls, value):
        if value % 2:
            raise ValueError("must be even")
        return value


def migrate(old_data):
    return migrate_settings_overrides(old_data, Settings, Settings().model_dump())


class TestMigrateSettingsOverrides:
    def test_lax_coercion(self):
        """Values are converted the same way the model converts them"""
        result = migrate({"s": 5, "ls": [1, 2], "f": 2.5, "b": True, "keep": "x"})
        assert result == {"s": "5", "ls": ["1", "2"], "f": 2, "b": "True", "keep": "x"}

    def test_field_constraints(self):
        """Values violating the field constraints are dropped"""
        result = migrate({"n": 50, "code": "ABC", "sub": {"name": 7, "limit": 99}})
        assert result == {"sub": {"name": "7"}}

    def test_field_validators(self):
        """Values rejected by field validators are dropped"""
        assert migrate({"even": 3, "keep": "x"}) == {"keep": "x"}
        assert migrate({"even": 4}) == {"even": 4}

    def test_removed_fields(self):
        assert migrate({"removed": 1, "keep": "x"}) == {"keep": "x"}

    def test_list_of_submodels(self):
        result = migrate({"items": [{"name": 1, "limit": 3}]})
        assert result == {"items": [{"name": "1", "limit": 3}]}

    def test_result_is_valid(self):
        old_data = {
            "s": 5,
            "n": 50,
            "code": "ABC",
            "sub": {"name": 7, "limit": 99},
            "items": [{"name": "a", "limit": 3}],
            "even": 3,
            "removed": 1,
        }
        result = migrate(old_data)
        Settings.model_validate(result)
