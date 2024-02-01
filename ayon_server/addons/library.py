import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Dict, Optional
import zipfile

from ayon_server.addons.addon import BaseServerAddon
from ayon_server.addons.rezrepo import RezRepo
from ayon_server.addons.utils import classes_from_module, import_module
from ayon_server.config import ayonconfig
from ayon_server.events import update_event
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres

import aiofiles
import httpx
from nxtools import logging, log_traceback, slugify


class AddonLibrary:
    """Class to manage AYON addons.

    Attrs:
        initialized_addons (dict): Addon name and version with the loaded class as value.
        broken_addons (dict): Addon name and version with the reason why they weren't able to be
            loaded.
    """
    _instance = None
    initialized_addons = {}
    broken_addons = {}

    @classmethod
    def get_instance(cls) -> "AddonLibrary":
        if cls._instance is None:
            cls._instance = AddonLibrary()
        return cls._instance

    @classmethod
    def get_addon(cls, addon_name: str, addon_version: str):
        """Attempt to initialize a Rez Package as an AYON Addon.

        Args:
            cls (AddonLibrary): The AddonLibrary.
            addon_name (str): The Addon name.
            addon_version (str): The Addon version.

        Returns:
            addon_class (BaseServerAddon | None): The Addon's main class, if there were no issues
                loading.
        """

        instance = cls.get_instance()

        try:
            # Guard in case we get a version "None"
            addon_version = eval(addon_version)
            if not addon_version:
                return

        except Exception:
            pass

        rezrepo = RezRepo().get_instance()
        addon_class = None

        for addon_version_dict in rezrepo.packages.get(addon_name, {}).get("versions", []):
            rez_package = addon_version_dict.get(addon_version, None)
            addon_name_and_version = slugify(f"{addon_name}-{addon_version}")
            if rez_package:
                logging.debug(f"Initializing Addon {addon_name}-{addon_version}")

                try:
                    addon_class = cls._init_addon_from_rez_package(
                        addon_name_and_version,
                        rez_package
                    )
                    instance.initialized_addons[addon_name_and_version] = addon_class
                except Exception as e:
                    logging.error(f"Unable to initialize Addon {addon_name}-{addon_version}")
                    log_traceback(e)
                    instance.broken_addons[addon_name_and_version] = e
            else:
                instance.broken_addons[addon_name_and_version] = f"No Rez packages found for addon {addon_name_and_version}"
                logging.warning(f"Addon {addon_name}-{addon_version} not found.")

        return addon_class

    @staticmethod
    def delete_addon(addon_name, addon_version=None):
        """Delete an addon from the server rez repo.

        Args:
            addon_name (str): The Addon name.
            addon_version (str | Optional): The Addon version.
        """
        logging.debug(f"Removing Rez Package: {addon_name} Version: {addon_version}")
        RezRepo.remove_addon(
            addon_name,
            addon_version
        )

    @staticmethod
    def get_addons_latest_versions():
        """Find the latest version of an addon, via rez."""
        rezrepo = RezRepo.get_instance()
        latest_addons = {}

        for addon_name in rezrepo.packages:
            latest_version = RezRepo.get_latest_addon_version()

            latest_addons[addon_name] = latest_version

        return latest_addons

    def _init_addon_from_rez_package(module_name, rez_package):
        """Attempt to initialize the Addon's BaseServerAddon sub-class.

        Args:
            module_name (str): The moducle name.
            rez_package (rez.Package): 
        """
        module_init_path = Path(rez_package.base) / "__init__.py"
        try:
            addon_module = import_module(module_name, str(module_init_path))
        except AttributeError as e:
            logging.error(f"Addon {module_name} - {module_init_path} is not a valid Python module.")
            raise e

        # It makes little sense to allow several addons from one init,
        # since they would be separate rez-packages
        addon_class = next(iter(classes_from_module(BaseServerAddon, addon_module)), None)

        if not addon_class:
            raise NotFoundException(
                f"No `BaseServerAddon` subclass found in the package {rez_package}"
            )

        return addon_class(rez_package, rez_package.base)

    @staticmethod
    async def get_enabled_addons(bundle_name=None) -> dict[str, dict[str, Optional[str]]]:
        """ Get the Addons enabled in the Bundles.
        """

        bundles_query = "SELECT name, is_production, is_staging, data->'addons' as addons FROM bundles"

        if bundle_name:
            bundles_query += f" WHERE name = '{bundle_name}'"

        bundles = await Postgres.fetch(bundles_query)
        all_addons: dict[str, dict[str, Optional[str | bool]]] = {}

        for bundle in bundles:
            all_addons[bundle["name"]] = {
                "addons": [],
                "production": bundle["is_production"],
                "staging": bundle["is_staging"],
            }

            for addon_name, addon_version in bundle["addons"].items():
                all_addons[bundle["name"]]["addons"].append((addon_name, addon_version))

        return all_addons

    @staticmethod
    async def get_bundle_addons(bundle_name) -> list[tuple[str, BaseServerAddon]]:
        """ Return all addons in a given Bundle.
        """
        bundle_addons = []

        library = AddonLibrary().get_instance()
        active_versions = await library.get_enabled_addons(bundle_name)

        for active_bundle_name, bundle_dict in active_versions.items():
            for addon in bundle_dict["addons"]:
                addon_name_and_version = slugify(f"{addon[0]}-{addon[1]}")
                addon = library.initialized_addons.get(addon_name_and_version)
                if not addon:
                    # It's a broken addon
                    addon = None

                bundle_addons.append((addon_name_and_version, addon))

        return bundle_addons

    @staticmethod
    async def get_variant_addons(variant=None) -> list[tuple[str, BaseServerAddon]]:
        if variant is None or variant not in ["production", "staging"]:
            variant = "production"

        library = AddonLibrary().get_instance()

        variants_bundle_names = await library.get_variants_bundle_name()
        bundle_name = variants_bundle_names.get(variant)
        if not bundle_name:
            return []

        addons = await library.get_bundle_addons(bundle_name)
        return addons

    @staticmethod
    async def get_variants_bundle_name():
        variants_dict = {"production": None, "staging": None}
        bundles = await Postgres.fetch(
            "SELECT name, is_production, is_staging FROM bundles "
            "WHERE is_production = true OR is_staging = true"
        )
        for bundle in bundles:
            if bundle["is_production"]:
                variants_dict["production"] = bundle["name"]
            elif bundle["is_staging"]:
                variants_dict["staging"] = bundle["name"]

        return variants_dict

    @classmethod
    async def initialize_enabled_addons(cls):
        instance = cls.get_instance()
        enabled_addons_by_bundle = await instance.get_enabled_addons()

        for bundle_name, bundle_dict in enabled_addons_by_bundle.items():
            for addon_name, addon_version in bundle_dict["addons"]:
                instance.get_addon(addon_name, addon_version)

        return instance.initialized_addons, instance.broken_addons

    @staticmethod
    def get_addon_zip_info(path: str) -> tuple[str, str]:
        """Returns the addon name and version from the zip file

        We also perform checks so that the zip is a valid AYON addon.
        """
        with zipfile.ZipFile(path, "r") as zip_ref:
            names = zip_ref.namelist()
            if "package.py" not in names:
                raise RuntimeError("Addon package.py not found in zip file")

            if "rezbuild.py" not in names:
                logging.warning("Addon rezbuild.py not found in zip file, will use default.")

            if "server/__init__.py" not in names:
                raise RuntimeError("Addon __init__.py not found in zip file")

            with zip_ref.open("package.py") as package_manifest:
                package_info: Dict[str, str] = {}
                exec(package_manifest.read(), package_info, package_info)
                addon_name = package_info.get("name")
                addon_version = package_info.get("version")

                if not (addon_name and addon_version):
                    raise RuntimeError("Addon name or version not found in `package.py`")

            return addon_name, addon_version

    @staticmethod
    def install_addon_from_zip(addon_name, zip_path: Path | str) -> None:
        """ Extract zip and rez install the package.
        """
        with tempfile.TemporaryDirectory() as tmpdirname:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                for member in zip_ref.infolist():
                    extracted_path = zip_ref.extract(member, tmpdirname)

                    # Preserve the file permissions
                    original_mode = member.external_attr >> 16
                    if original_mode:
                        os.chmod(extracted_path, original_mode)

            rez_package_py = Path(tmpdirname) / "package.py"
            rez_build_py = Path(tmpdirname) / "rezbuild.py"

            if not rez_package_py.exists():
                raise RuntimeError("Zip {} is missing the `package.py`.")

            if not rez_build_py.exists():
                default_rez_build_py = Path(__file__).parent / "rezbuild.py"
                shutil.copyfile(default_rez_build_py, rez_build_py)

            return RezRepo.install_addon(
                addon_name,
                rez_package_py
            )

    @classmethod
    async def install_addon(
        cls,
        event_id: str,
        zip_path: str,
        addon_name: str,
        addon_version: str,
    ):
        """Unpack the addon from the zip file and install it

        Unpacking is done in a separate thread to avoid blocking the main thread
        (unzipping is a synchronous operation and it is also cpu-bound)

        After the addon is unpacked, the event is finalized and the zip file is removed.
        """

        await update_event(
            event_id,
            description=f"Installing addon {addon_name} {addon_version}",
            status="in_progress",
        )

        loop = asyncio.get_event_loop()
        isntance = cls.get_instance()
        
        try:
            with ThreadPoolExecutor() as executor:
                task = loop.run_in_executor(
                    executor,
                    isntance.install_addon_from_zip,
                    addon_name,
                    zip_path
                )
                rez_package = await asyncio.gather(task)
        except Exception as e:
            logging.error(f"Error while installing addon: {e}")
            log_traceback(e)
            await update_event(
                event_id,
                description=f"Error while installing addon: {e}",
                status="failed",
            )

        try:
            os.remove(zip_path)
        except Exception as e:
            logging.error(f"Error while removing zip file: {e}")
            log_traceback(e)

        await update_event(
            event_id,
            description=f"Addon {addon_name} {addon_version} installed.",
            status="finished",
        )

    @classmethod
    async def install_addon_from_url(cls, event_id: str, url: str) -> None:
        """Download the addon zip file from the URL and install it"""

        await update_event(
            event_id,
            description=f"Downloading addon from URL {url}",
            status="in_progress",
        )

        isntance = cls.get_instance()

        # Download the zip file
        # we do not use download_file() here because using NamedTemporaryFile
        # is much more convenient than manually creating a temporary file

        file_size = 0
        last_time = 0.0

        i = 0
        with tempfile.NamedTemporaryFile() as temporary_file:
            zip_path = temporary_file.name
            async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
                async with client.stream("GET", url) as response:
                    file_size = int(response.headers.get("content-length", 0))
                    async with aiofiles.open(zip_path, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            await f.write(chunk)
                            i += len(chunk)

                            if file_size and (time.time() - last_time > 1):
                                percent = int(i / file_size * 100)
                                await update_event(
                                    event_id,
                                    progress=int(percent / 2),
                                    store=False,
                                )
                                last_time = time.time()

            addon_name, addon_version = isntance.get_addon_zip_info(zip_path)
            isntance.install_addon(event_id, zip_path, addon_name, addon_version)

