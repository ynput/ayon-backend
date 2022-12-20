import asyncio
import enum
import hashlib
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
    WorkfileEntity,
)
from openpype.lib.postgres import Postgres
from openpype.utils import create_uuid, dict_exclude
from setup.attributes import DEFAULT_ATTRIBUTES

VERSIONS_PER_SUBSET = 5


def get_random_md5():
    """Get random md5 hash."""
    return hashlib.md5(str(random.random()).encode("utf-8")).hexdigest()


class DemoGen:
    def __init__(self, validate: bool = True):
        self.folder_count = 0
        self.subset_count = 0
        self.version_count = 0
        self.representation_count = 0
        self.task_count = 0
        self.workfile_count = 0
        self.validate = validate

    async def populate(
        self,
        project_name: str,
        hierarchy: list[dict[str, Any]],
    ) -> None:
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
        logging.info(f"{self.workfile_count} workfiles created")
        logging.goodnews(
            f"Project {self.project_name} demo in {elapsed_time:.2f} seconds"
        )

    def get_entity_tags(self):
        """return a list of random tags for entity"""
        tags = [tag["name"] for tag in self.project.tags]
        return random.sample(tags, random.randint(0, 5))

    def get_entity_status(self):
        """return a random status for entity"""
        status = random.choice(self.project.statuses)
        return status["name"]

    async def create_branch(self, **kwargs: Any) -> None:
        async with Postgres.acquire() as conn:
            async with conn.transaction():
                folder = await self.create_folder(conn, **kwargs)
                await folder.commit(conn)

    async def create_folder(
        self,
        conn: Postgres.Transaction,
        parent_id: str | None = None,
        parents: list[str] = [],
        **kwargs: Any,
    ) -> FolderEntity:
        self.folder_count += 1
        if self.folder_count % 100 == 0:
            logging.debug(f"{self.folder_count} folders created")

        # Propagate project attributes
        attrib = kwargs.get("attrib", {})
        if kwargs.get("folder_type") is None:
            # Use explicit attributes inherited from the project settings
            # For folder-folders
            for key, value in self.project.attrib.dict().items():
                if key in attrib:
                    continue
                attrib[key] = value
        kwargs["attrib"] = attrib

        for s in kwargs.get("_subsets", []):
            for r in s.get("_representations", []):
                if (tpl := r.get("template")) is not None:
                    if "{frame}" in tpl:
                        kwargs["attrib"]["frameStart"] = self.project.attrib.frameStart
                        kwargs["attrib"]["frameEnd"] = self.project.attrib.frameEnd

        payload = {
            "parent_id": parent_id,
            "tags": self.get_entity_tags(),
            "status": self.get_entity_status(),
            **dict_exclude(kwargs, ["_", "parentId"], mode="startswith"),
        }
        folder = FolderEntity(
            project_name=self.project_name,
            payload=payload,
            validate=self.validate,
        )
        await folder.save(conn)
        folder.parents = parents  # type: ignore

        tasks = {}

        for task in kwargs.get("_tasks", []):
            if task["task_type"] == "Modeling":
                task["assignees"] = random.choice(
                    [["artist"], ["artist", "visitor"], [], [], []]
                )
            task_entity = await self.create_task(
                conn,
                folder=folder,
                parents=parents + [folder.name],
                **task,
            )
            tasks[task_entity.name] = task_entity.id

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

    async def create_subset(
        self,
        conn: Postgres.Transaction,
        folder: FolderEntity,
        tasks,
        **kwargs,
    ) -> SubsetEntity:
        self.subset_count += 1
        if task_name := kwargs.get("_task_link"):
            task_id = tasks.get(task_name)
            # print(f"subset {kwargs['name']} linked to task_id {task_id}")
        else:
            task_id = None

        payload = {
            "folder_id": folder.id,
            "tags": self.get_entity_tags(),
            "status": self.get_entity_status(),
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

            for key, acfg in DEFAULT_ATTRIBUTES.items():
                if "V" not in [scope.strip() for scope in acfg["scope"].split(",")]:
                    continue

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
                    "tags": self.get_entity_tags(),
                    "status": self.get_entity_status(),
                },
                validate=self.validate,
            )
            await version.save(conn)

            for representation in kwargs.get("_representations", []):
                await self.create_representation(
                    conn, folder, subset, version, **representation
                )
        return subset

    async def create_task(
        self,
        conn: Postgres.Transaction,
        folder: FolderEntity,
        parents: list[str],
        **kwargs: Any,
    ) -> TaskEntity:
        self.task_count += 1
        payload = {**kwargs}
        payload["folder_id"] = folder.id
        payload["attrib"] = folder.attrib.dict()
        payload["tags"] = self.get_entity_tags()
        payload["status"] = self.get_entity_status()
        task = TaskEntity(
            project_name=self.project_name,
            payload=payload,
            validate=self.validate,
        )
        await task.save(conn)

        num_workfiles = random.randint(0, 5)
        for i in range(1, num_workfiles):
            fname = f"{self.project.code}_{folder.name}_{task.name}_v{i:03d}.ma"
            path = "{root[work]}/"
            path += "/".join(parents)
            path += f"/work/{task.name}/{fname}"

            workfile = WorkfileEntity(
                project_name=self.project_name,
                payload={
                    "path": path,
                    "task_id": task.id,
                    "created_by": "admin",
                    "tags": self.get_entity_tags(),
                    "status": self.get_entity_status(),
                },
                validate=self.validate,
            )
            await workfile.save(conn)
            self.workfile_count += 1

        return task

    async def create_representation(
        self,
        conn: Postgres.Transaction,
        folder: FolderEntity,
        subset: SubsetEntity,
        version: VersionEntity,
        **kwargs: Any,
    ) -> RepresentationEntity:
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
            "path": "/".join(folder.parents + [folder.name]),  # type: ignore
            "family": subset.family,
            "subset": subset.name,
            "version": version.version,
            "folder": folder.name,
        }

        files = []
        if "{frame}" in kwargs["attrib"]["template"]:
            frame_start = folder.attrib.frameStart
            frame_end = folder.attrib.frameEnd
        else:
            frame_start = 0
            frame_end = 0
        for i in range(frame_start, frame_end + 1):
            fid = create_uuid()
            fpath = kwargs["attrib"]["template"].format(frame=f"{i:06d}", **context)
            files.append(
                {
                    "id": fid,
                    "path": fpath,
                    "size": random.randint(1_000_000, 10_000_000),
                    "hash": get_random_md5(),
                }
            )

        #
        # Save the representation
        #

        representation = RepresentationEntity(
            project_name=self.project_name,
            payload={
                "version_id": version.id,
                "tags": self.get_entity_tags(),
                "status": self.get_entity_status(),
                "files": files,
                "data": {
                    "context": context,
                },
                **kwargs,
            },
            validate=self.validate,
        )
        await representation.save(conn)

        return representation
