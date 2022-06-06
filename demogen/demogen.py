import asyncio
import enum
import random
import time
from typing import Any

from nxtools import logging

from demogen.generators import generators
from openpype.entities import (
    FolderEntity,
    ProjectEntity,
    RepresentationEntity,
    SubsetEntity,
    TaskEntity,
    VersionEntity,
)
from openpype.entities.models.attributes import common_attributes
from openpype.lib.postgres import Postgres
from openpype.utils import create_uuid, dict_exclude

VERSIONS_PER_SUBSET = 5


class StateEnum(enum.IntEnum):
    """
    -1 : State is not available
    0 : Transfer in progress
    1 : File is queued for Transfer
    2 : Transfer failed
    3 : Tranfer is paused
    4 : File/representation is fully synchronized
    """

    NOT_AVAILABLE = -1
    IN_PROGRESS = 0
    QUEUED = 1
    FAILED = 2
    PAUSED = 3
    SYNCED = 4


class DemoGen:
    def __init__(self, validate: bool = True):
        self.folder_count = 0
        self.subset_count = 0
        self.version_count = 0
        self.representation_count = 0
        self.task_count = 0
        self.validate = validate

    async def populate(self, project_name: str, hierarchy: list[dict[str, Any]]):
        start_time = time.monotonic()
        self.project_name = project_name
        self.project = await ProjectEntity.load(project_name)

        logging.info(f"Creating folders for project {project_name}")

        tasks = []
        for folder_data in hierarchy:
            tasks.append(self.create_branch(**folder_data))

        await asyncio.gather(*tasks)
        logging.info("Refreshing views")
        await Postgres.execute(
            f"""
            REFRESH MATERIALIZED VIEW project_{self.project.name}.hierarchy;
            REFRESH MATERIALIZED VIEW project_{self.project.name}.version_list;
            """
        )

        elapsed_time = time.monotonic() - start_time
        logging.info(f"{self.folder_count} folders created")
        logging.info(f"{self.subset_count} subset created")
        logging.info(f"{self.version_count} versions created")
        logging.info(f"{self.representation_count} representations created")
        logging.info(f"{self.task_count} tasks created")
        logging.goodnews(
            f"Project {self.project_name} demo in {elapsed_time:.2f} seconds"
        )

    async def create_branch(self, **kwargs):
        async with Postgres.acquire() as conn:
            async with conn.transaction():
                folder = await self.create_folder(conn, **kwargs)
                await folder.commit(conn)

    async def create_folder(self, conn, parent=None, parents=[], **kwargs):
        self.folder_count += 1
        if self.folder_count % 100 == 0:
            logging.debug(f"{self.folder_count} folders created")

        # Propagate project attributes
        attrib = kwargs.get("attrib", {})
        for key, value in self.project.attrib.dict().items():
            if key in attrib:
                continue
            attrib[key] = value
        kwargs["attrib"] = attrib

        payload = {
            "parent_id": parent,
            **dict_exclude(kwargs, ["_", "parentId"], mode="startswith"),
        }
        folder = FolderEntity(
            project_name=self.project_name,
            payload=payload,
            validate=self.validate,
        )
        await folder.save(conn)
        folder.parents = parents

        tasks = {}

        for task in kwargs.get("_tasks", []):
            if task["task_type"] == "Modeling":
                task["assignees"] = random.choice(
                    [["artist"], ["artist", "visitor"], [], [], []]
                )
            tname, tid = await self.create_task(conn, folder_id=folder.id, **task)
            tasks[tname] = tid

        for subset in kwargs.get("_subsets", []):
            await self.create_subset(conn, folder, tasks=tasks, **subset)

        if "_children" in kwargs:
            if type(kwargs["_children"]) == str:
                async for child in generators[kwargs["_children"]](kwargs):
                    await self.create_folder(
                        conn, folder.id, parents=parents + [folder.name], **child
                    )
            elif type(kwargs["_children"]) is list:
                for child in kwargs["_children"]:
                    await self.create_folder(
                        conn, folder.id, parents=parents + [folder.name], **child
                    )
        return folder

    async def create_subset(self, conn, folder, tasks, **kwargs):
        self.subset_count += 1
        if task_name := kwargs.get("_task_link"):
            task_id = tasks.get(task_name)
            # print(f"subset {kwargs['name']} linked to task_id {task_id}")
        else:
            task_id = None

        payload = {
            "folder_id": folder.id,
            **dict_exclude(kwargs, ["_"], mode="startswith"),
        }
        subset = SubsetEntity(
            project_name=self.project_name,
            payload=payload,
            validate=self.validate,
        )
        await subset.save(conn)

        for i in range(1, VERSIONS_PER_SUBSET):
            self.version_count += 1
            attrib = {"families": [kwargs["family"]]}
            for key in [r["name"] for r in common_attributes]:
                val = folder.attrib.dict().get(key)
                if val is not None:
                    attrib[key] = val
            version = VersionEntity(
                project_name=self.project_name,
                payload={
                    "subset_id": subset.id,
                    "task_id": task_id,
                    "version": i,
                    "author": "admin",
                    "attrib": attrib,
                },
                validate=self.validate,
            )
            await version.save(conn)

            for representation in kwargs.get("_representations", []):
                await self.create_representation(
                    conn, folder, subset, version, **representation
                )

    async def create_task(self, conn, **kwargs):
        self.task_count += 1
        task = TaskEntity(
            project_name=self.project_name, payload=kwargs, validate=self.validate
        )
        await task.save(conn)
        return task.name, task.id

    async def create_representation(self, conn, folder, subset, version, **kwargs):
        self.representation_count += 1

        attrib = kwargs.get("attrib", {})
        if "template" in kwargs:
            attrib["template"] = kwargs["template"]
        kwargs["attrib"] = attrib

        #
        # Create a list of files
        #
        context = {
            "root": "{root}",
            "project_name": self.project_name,
            "path": "/".join(folder.parents + [folder.name]),
            "family": subset.family,
            "subset": subset.name,
            "version": version.version,
            "folder": folder.name,
        }

        files = {}
        if "{frame}" in kwargs["attrib"]["template"]:
            frame_start = folder.attrib.frameStart
            frame_end = folder.attrib.frameEnd
        else:
            frame_start = 0
            frame_end = 0
        for i in range(frame_start, frame_end + 1):
            fid = create_uuid()
            fpath = kwargs["attrib"]["template"].format(frame=f"{i:06d}", **context)
            files[fid] = {
                "path": fpath,
                "size": random.randint(1_000_000, 10_000_000),
                "hash": fid,
            }

        #
        # Save the representation
        #

        representation = RepresentationEntity(
            project_name=self.project_name,
            payload={
                "version_id": version.id,
                "data": {
                    "files": files,
                    "context": context,
                },
                **kwargs,
            },
            validate=self.validate,
        )
        await representation.save(conn)

        #
        # Save sync state of the files
        #

        sites = ["local", "remote"] + [f"user{j:02d}" for j in range(1, 5)]

        priority = random.choice([0, 0, 0, 10, 50, 100])

        for site_name in sites:

            if site_name == "local" and random.choice([True] * 4 + [False]):
                continue

            fdata = {"files": {}}
            for fid, file in files.items():

                if site_name == "remote":
                    status = StateEnum.SYNCED
                else:
                    status = random.choice([-1, 0, 2, 3, 4])
                fsize = {
                    StateEnum.NOT_AVAILABLE: 0,
                    StateEnum.FAILED: 0,
                    StateEnum.IN_PROGRESS: random.randint(0, file["size"]),
                    StateEnum.PAUSED: random.randint(0, file["size"]),
                    StateEnum.QUEUED: 0,
                    StateEnum.SYNCED: file["size"],
                }[status]

                fdata["files"][fid] = {
                    "status": status,
                    "timestamp": int(time.time())
                    if status
                    in [
                        StateEnum.SYNCED,
                        StateEnum.PAUSED,
                        StateEnum.IN_PROGRESS,
                        StateEnum.FAILED,
                    ]
                    else 0,
                    "size": fsize,
                }
                if status == StateEnum.FAILED:
                    excuse = random.choice(
                        [
                            "Resonant Kernel Incompatibility"
                            "Nullified Handler Problem",
                            "Severe Warming Infection",
                            "Insufficient Kernel Flag",
                            "Outmoded Protocol Problem",
                            "Unregistered Peripheral Rejection",
                        ]
                    )
                    fdata["files"][fid].update(
                        {
                            "message": f"Transfer failed: {excuse}",
                            "retries": random.randint(1, 4),
                        }
                    )

            await conn.execute(
                f"""
                INSERT INTO project_{self.project_name}.files
                    (representation_id, site_name, status, priority, data)
                VALUES
                    ($1, $2, $3, $4, $5)
                """,
                representation.id,
                site_name,
                status,
                priority,
                fdata,
            )
