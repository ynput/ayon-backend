"""
 Rez implementation of the Addons logic
 * Addon Library (`library.py`): A Class that manages addons server definitions.
 * Addon Server Definition (`definition.py`): A Class that manages addon's versions.
 * Addon Definition (`addon.py`): A Class representing a specific **version** of an addon,

 Library -> Rez Repo
 ServerDefinition -> RezFamily
 Addon Definition -> BaseServerAddon
"""
from pathlib import Path
import shutil

from ayon_server.config import ayonconfig
from ayon_server.version import __version__ as ayon_server_version

from nxtools import logging, log_traceback
from rez.exceptions import PackageFamilyNotFoundError
from rez.packages import get_package
from rez.developer_package import DeveloperPackage
from rez.build_process import create_build_process
from rez.build_system import create_build_system
from rez.package_maker import make_package
# from rez.package_repository import PackageRepository
from rez.packages import get_latest_package
from rez.package_search import get_plugins
from rez.package_remove import remove_package, remove_package_family
from rez.serialise import load_from_file, FileFormat
from rez.utils.resources import ResourcePool
from rezplugins.package_repository.filesystem import FileSystemPackageRepository


class RezRepo(FileSystemPackageRepository):
    _instance = None
    rez_repo_path = ayonconfig.addons_dir

    @classmethod
    def get_instance(cls) -> "RezRepo":
        if cls._instance is None:
            cls._instance = RezRepo()
        return cls._instance

    def __init__(self) -> None:
        self.restart_requested = False
        self.packages = {}

        # Using `super` won't work correctly
        FileSystemPackageRepository.__init__(self, self.rez_repo_path, ResourcePool())

        # AYON server rez meta package
        ayon_server_package = get_package(
            "ayon_server", ayon_server_version, paths=[self.rez_repo_path]
        )

        if not ayon_server_package:
            self._create_ayon_server_package()

        # Find all AYON plugins
        self.packages = self._find_ayon_addons()

        if not self.packages:
            logging.info("No addons found for 'ayon_server'")

    def _create_ayon_server_package(self):
        from rez.package_maker import make_package

        with make_package("ayon_server", self.rez_repo_path) as pkg:
            pkg.authors = ["Ynput"]
            pkg.description = "Meta package that any Addon has to specify as plugin of."
            pkg.has_plugins = True
            pkg.version = ayon_server_version

        # We need to restart everytime we install a new package
        self.restart_requested = True

    def _find_ayon_addons(self):
        """Find Rez packages that are plugins of the `ayon_server` package."""
        ayon_addons = {}

        try:
            ayon_server_plugins = get_plugins("ayon_server", [self.rez_repo_path])
        except PackageFamilyNotFoundError as e:
            logging.warning(f"Missing 'ayon_server' package in '{self.rez_repo_path}'")
            log_traceback(e)
            return

        for addon_name in ayon_server_plugins:
            package_family = self.get_package_family(addon_name)

            if package_family is None:
                print("No package family found")
                continue

            ayon_addons[package_family.name] = {
                "family": package_family,
                "versions": [],
            }
            package_versions = ayon_addons[package_family.name]["versions"]
            # The `FileSystemPackageFamilyResource` does not hold the packages
            # So we iterate over them and get the actual `Package` object.
            for package in package_family.iter_packages():
                package = get_package(
                    package.name, package.version, paths=[self.rez_repo_path]
                )
                package_versions.append({str(package.version): package})

        logging.info(f"Found {len(ayon_addons)} 'ayon_server' plugin(s) Rez packages.")
        return ayon_addons

    @classmethod
    def install_addon(cls, addon_name, package_definition_path):
        package_definition_path = Path(package_definition_path)

        if not package_definition_path.exists():
            logging.error(
                f"Missing `package.py` in: {package_definition_path}"
            )
            return

        working_dir = package_definition_path.parent
        ayon_build = Path(__file__).parent / "rezbuild.py"
        shutil.copy(ayon_build, working_dir / "rezbuild.py")

        package = DeveloperPackage.from_path(working_dir, format=FileFormat.py)
        if getattr(package, "build_command", None) is None:
            # If no command is specified we fallback to AYON rezbuild
            logging.debug("Setting Package `build_command` to `rezbuild.py`")
            package.build_command = "python {root}/rezbuild.py"

        logging.debug(f"Found {package} in {working_dir}")
        build_system = create_build_system(
            working_dir,
            package=package,
            buildsys_type="custom",
        )

        # create and execute build process
        builder = create_build_process(
            "local",
            working_dir,
            build_system=build_system,
        )

        try:
            builder.build(install_path=cls.rez_repo_path, install=True)
        except Exception as e:
            logging.error(f"Unable to install {package_definition_path}")
            log_traceback(e)

    @classmethod
    def remove_addon(cls, addon_name, addon_version=None):
        if addon_version:
            remove_package_family(addon_name, cls.rez_repo_path, force=True)
        else:
            remove_package(addon_name, addon_version, cls.rez_repo_path)

    @classmethod
    def get_latest_addon_version(cls, addon_name):
        return get_latest_package(addon_name, paths=[cls.rez_repo_path])

