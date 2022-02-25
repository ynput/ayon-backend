import time
import asyncio
import random

from nxtools import logging

from openpype.entities import (
    ProjectEntity,
    FolderEntity,
    SubsetEntity,
    VersionEntity,
    RepresentationEntity,
    TaskEntity
)

from openpype.exceptions import RecordNotFoundException
from openpype.entities.models.attributes import common_attributes
from openpype.utils import dict_exclude, create_uuid, json_dumps
from openpype.lib.postgres import Postgres

from .generators import generators


class DemoGen:
    def __init__(self, validate: bool = True):
        self.folder_count = 0
        self.subset_count = 0
        self.version_count = 0
        self.representation_count = 0
        self.task_count = 0
        self.validate = validate

    async def populate(self, **kwargs):
        start_time = time.monotonic()
        self.project_name = kwargs["name"]

        logging.info(f"Creating project {self.project_name}")
        await Postgres.connect()

        await self.delete_project()

        self.project = ProjectEntity(**kwargs)
        await self.project.save()

        tasks = []
        for folder_data in kwargs.get("hierarchy", []):
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

    async def delete_project(self):
        """Attempt to delete the project."""
        try:
            project = await ProjectEntity.load(self.project_name)
        except RecordNotFoundException:
            return False
        else:
            await project.delete()
            logging.info(f"Project {self.project_name} deleted")
            return True

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
        for key, value in self.project.attrib.items():
            if key in attrib:
                continue
            attrib[key] = value
        kwargs["attrib"] = attrib

        folder = FolderEntity(
            project_name=self.project_name,
            parent_id=parent,
            validate=self.validate,
            **dict_exclude(kwargs, ["_", "parentId"], mode="startswith")
        )
        await folder.save(conn)
        folder.parents = parents

        for subset in kwargs.get("_subsets", []):
            await self.create_subset(conn, folder, **subset)

        for task in kwargs.get("_tasks", []):
            if task["task_type"] == "Modeling":
                task["assignees"] = random.choice([
                    ["artist"],
                    ["artist", "visitor"],
                    [],
                    [],
                    []
                ])
            await self.create_task(conn, folder_id=folder.id, **task)

        if "_children" in kwargs:
            if type(kwargs["_children"]) == str:
                async for child in generators[kwargs["_children"]](kwargs):
                    await self.create_folder(
                        conn,
                        folder.id,
                        parents=parents+[folder.name],
                        **child
                    )
            elif type(kwargs["_children"]) is list:
                for child in kwargs["_children"]:
                    await self.create_folder(
                        conn,
                        folder.id,
                        parents=parents+[folder.name],
                        **child
                    )
        return folder

    async def create_subset(self, conn, folder, **kwargs):
        self.subset_count += 1
        subset = SubsetEntity(
            project_name=self.project_name,
            folder_id=folder.id,
            validate=self.validate,
            **dict_exclude(kwargs, ["_"], mode="startswith")
        )
        await subset.save(conn)

        for i in range(1, folder.get("_version_count", 5)):
            self.version_count += 1
            attrib = {"families": [kwargs["family"]]}
            for key in [r["name"] for r in common_attributes]:
                attrib[key] = folder.attrib[key]
            version = VersionEntity(
                validate=self.validate,
                project_name=self.project_name,
                subset_id=subset.id,
                version=i,
                author="admin",
                attrib=attrib
            )
            await version.save(conn)

            for representation in kwargs.get("_representations", []):
                await self.create_representation(
                    conn,
                    folder,
                    subset,
                    version,
                    **representation
                )

    async def create_task(self, conn, **kwargs):
        self.task_count += 1
        task = TaskEntity(
            project_name=self.project_name,
            validate=self.validate,
            **kwargs
        )
        await task.save(conn)

    async def create_representation(
        self,
        conn,
        folder,
        subset,
        version,
        **kwargs
    ):
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
            frame_start = folder.attrib["frameStart"]
            frame_end = folder.attrib["frameEnd"]
        else:
            frame_start = 0
            frame_end = 0
        for i in range(frame_start, frame_end + 1):
            fid = create_uuid()
            fpath = kwargs["attrib"]["template"].format(frame=f"{i:06d}", **context)
            files[fid] = {
                "path": fpath,
                "size": random.randint(1_000_000, 10_000_000),
                "hash": fid
            }

        #
        # Save the representation
        #

        representation = RepresentationEntity(
            project_name=self.project_name,
            validate=self.validate,
            version_id=version.id,
            data={
                "files": files,
                "context": context,
            },
            **kwargs
        )
        await representation.save(conn)

        #
        # Save sync state of the files
        #

        sites = ["local", "remote"] \
            + [f"user{j:02d}" for j in range(1, 5)]

        priority = random.choice([0, 0, 0, 10, 50, 100])
        synced = random.choice([True, True, True, False])

        for site_name in sites:
            fdata = {"files": {}}
            for fid, file in files.items():
                fdata["files"][fid] = {
                    "status": "online" if synced else "pending",
                    "timestamp": int(time.time()),
                    "size": file["size"] if synced else 0,
                }

            await conn.execute(
                f"""
                INSERT INTO project_{self.project_name}.files
                    (representation_id, site_name, synced, priority, data)
                VALUES
                    ($1, $2, $3, $4, $5)
                """,
                representation.id,
                site_name,
                synced,
                priority,
                json_dumps(fdata)
            )
