from pydantic import Field

from openpype.settings.common import BaseSettingsModel


class ListPerPlatform(BaseSettingsModel):
    windows: list[str] = Field(default_factory=list)
    linux: list[str] = Field(default_factory=list)
    darwin: list[str] = Field(default_factory=list)


class AppVariant(BaseSettingsModel):
    name: str
    label: str | None = None
    executables: ListPerPlatform = Field(..., title="Executables")
    arguments: ListPerPlatform = Field(..., title="Arguments")
    environment: dict[str, str] = Field(
        default_factory=dict,
        description="App variant environment variables",
    )


class AppVariantWithPython(AppVariant):
    usePython2: bool = Field(False, title="Use Python 2")


class AppGroup(BaseSettingsModel):
    enabled: bool = Field(default=True)
    hostName: str | None
    icon: str | None
    environment: dict[str, str] = Field(
        default_factory=dict,
        description="Application group environment variables",
    )
    variants: list[AppVariant] = Field(
        default_factory=list,
        title="Variants",
        description="Different variants of the applications",
        section="Variants",
    )


class AppGroupWithPython(AppGroup):
    variants: list[AppVariantWithPython] = Field(
        default_factory=list,
        title="Variants",
        description="Different variants of the applications",
        section="Variants",
    )


class Applications(BaseSettingsModel):
    """Applications settings"""

    maya: AppGroupWithPython = Field(..., title="Autodesk Maya")
    flame: AppGroupWithPython = Field(..., title="Autodesk Flame")
    nuke: AppGroupWithPython = Field(..., title="Nuke")
    aftereffects: AppGroup = Field(..., title="Adobe After Effects")
    photoshop: AppGroup = Field(..., title="Adobe Photoshop")
    tvpaint: AppGroup = Field(..., title="TV Paint")
    harmony: AppGroup = Field(..., title="Harmony")
    # additional_apps: AppGroup = Field(..., title="Additional Applications")


class FtrackModule(BaseSettingsModel):
    """Here you can configure the ftrack module in order to ftrack everything."""

    _title: str = "ftrack"
    _isGroup: bool = True
    enabled: bool
    server: str


class Modules(BaseSettingsModel):
    """Modules configuration"""

    addonPaths: ListPerPlatform = Field(
        default_factory=ListPerPlatform,
        title="Addon paths",
        description="Paths where to look for addons",
    )
    ftrack: FtrackModule


def get_coffee_sizes():
    return ["small", "smaller", "smallest"]


def get_milk_options():
    return ["none", "no way", "no"]


class General(BaseSettingsModel):
    """Configure your generals here."""

    artistCount: int = Field(
        ...,
        title="Number of artists",
        description="Number of artists you have in the studio",
    )
    coffeeSize: str = Field(
        ...,
        title="Coffee size",
        description="The size of the coffee you drink",
        section="Beverages",
        enum_resolver=get_coffee_sizes,
    )
    milk: str = Field(
        ...,
        title="Milk",
        description="The kind of milk you drink",
        enum_resolver=get_milk_options,
    )


class SystemSettings(BaseSettingsModel):
    """System settings"""

    _layout: str = "root"
    general: General = Field(..., title="General")
    modules: Modules = Field(..., title="Modules")
    applications: Applications = Field(..., title="Applications")
