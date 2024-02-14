""" AYON Rez Builder

This expects a certain folder structure:
├── client
│   └── <client module name>  # Example: ayon_core
├── package.py
└── server

Other folders might or might not be present, but they are essentially ignored.

Will zip up the `client/<client module name>` and place it into `private/client.zip`
and copy the contents of `server` into the root of the package.

<package root>
├── frontend
│   ├── dist
├── server
│   ├── __init__.py
│   └── settings
├── private
│   ├── client.zip
│   └── pyproject.toml
├── package.py
└── build.rtx

MIght be worth checking in the future https://gitlab.com/Pili-Pala/rezbuild
"""
import os
from pathlib import Path
import shutil

SRC_DIR = Path(os.environ["REZ_BUILD_SOURCE_PATH"])
DEST_DIR = Path(os.environ["REZ_BUILD_INSTALL_PATH"])


def _recursive_copy(src, dst):
    """ Recursively travers a directory and copy the contents to destination

    For soem reason `shutil.copytree` refuses to work, so I had to implement.
    """
    for child in src.iterdir():
        if child.is_dir():
            _recursive_copy(child, dst / child.stem)
        elif child.is_file():
            dst_file = dst / child.relative_to(src)
            print(f"Copying {child} -> {dst_file}")
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(
                child,
                dst_file
            )


def install_addon():
    server_dir = SRC_DIR / "server"

    # Copy "server" to "addon"
    if server_dir.is_dir():
        print(f"Copying `server` directory contents to {DEST_DIR}")
        _recursive_copy(server_dir, DEST_DIR)

    # Zip up the `client`` dir which might not be present
    client_dir = SRC_DIR / "client"

    if not client_dir.exists():
        return DEST_DIR

    client_zip_dest_dir = DEST_DIR / "private" / "client"
    client_zip_dest_dir.mkdir(parents=True)
    client_zip = DEST_DIR / "private" / "client.zip"

    print(f"Copying `client` directory to `private/client` {client_zip_dest_dir}")
    # Copy and remove unnecessary files so we can just "zip it up"
    _recursive_copy(client_dir, client_zip_dest_dir)

    # Move the `pyproject.toml` next to the `client.zip`
    try:
        print(f"Moving client's `pyproject.toml` to {DEST_DIR / 'private' / 'pyproject.toml'}")
        shutil.move(
            str(client_zip_dest_dir / "pyproject.toml"),
            str(DEST_DIR / "private" / "pyproject.toml")
        )
    except Exception:
        print("Client code has no `pyproject.toml`.")

    print(f"Creating an archive of {client_zip_dest_dir}")
    shutil.make_archive(
        str(client_zip),
        "zip",
        root_dir=str(client_zip_dest_dir)
    )

    print(f"Removing transient folder {client_zip_dest_dir}")
    # Remove transient "client" folder from "private"
    shutil.rmtree(f'{client_zip_dest_dir}', ignore_errors=True)

    addon_name = os.environ['REZ_BUILD_PROJECT_NAME']
    addon_version = os.environ['REZ_BUILD_PROJECT_VERSION']
    with open(DEST_DIR / "version.py", "w+") as version_py:
        version_py.write(f'__version__ = "{addon_version}"')

    print(f"Finished installing {addon_name}-{addon_version}")


if __name__ == "__main__":
    try:
        install_addon()
    except Exception as e:
        # shutil.rmtree(str(DEST_DIR))
        raise e


