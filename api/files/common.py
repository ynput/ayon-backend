import os

from ayon_server.config import ayonconfig


def id_to_path(project_name: str, file_id: str) -> str:
    file_id = file_id.replace("-", "")
    assert len(file_id) == 32
    fgroup = file_id[:2]
    return os.path.join(
        ayonconfig.upload_dir,
        project_name,
        fgroup,
        file_id,
    )
