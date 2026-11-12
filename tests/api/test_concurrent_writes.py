"""Many clients writing to one folder tree at the same time.

Every write rebuilds a part of the exported attributes (what a folder
passes to its children) and drops the cached folder list. Rebuilds of
a parent and of its child that run at the same time must not leave
old values behind.

The test builds a tree, then runs one job per folder in a thread pool.
A job changes only its own folder, so the final state does not depend
on the order of the jobs and can be computed here (`Node`). It is compared
with the folder list and with every folder loaded on its own.
"""

import random
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from .conftest import TempProject, create_temp_project, operation
from .test_folder_list_cache import PNG

THREADS = 8
SEQUENCES = 3
SHOTS = 4  # per sequence
DEEP = 3  # per shot
ROUNDS = 3  # writes of one value, the last one wins

# Both must be inheritable (checked by the test)
FPS = "fps"
WIDTH = "resolutionWidth"


@dataclass
class Node:
    """A folder as it should look when all jobs are done."""

    id: str
    name: str
    parent: str | None = None
    own: dict[str, Any] = field(default_factory=dict)
    active: bool = True
    tasks: list[str] = field(default_factory=list)
    has_version: bool = False
    has_reviewable: bool = False
    deleted: bool = False


@dataclass
class Tree:
    project: TempProject
    nodes: dict[str, Node] = field(default_factory=dict)
    retries: int = 0

    def add(self, name: str, parent: str | None = None) -> Node:
        node = Node(id=uuid.uuid4().hex, name=name, parent=parent)
        self.nodes[node.id] = node
        return node

    def create_op(self, node: Node, **data: Any) -> dict[str, Any]:
        return operation(
            "create",
            "folder",
            node.id,
            data={
                "name": node.name,
                "parentId": node.parent,
                "folderType": self.project.folder_types[0],
                "status": self.project.statuses[0],
                **data,
            },
        )

    def write(self, *operations: dict[str, Any]) -> None:
        """Process operations. "Locked, try again" answers are retried."""
        url = f"/api/projects/{self.project.name}/operations"
        text = ""
        for attempt in range(10):
            response = self.project.api.post(url, json={"operations": operations})
            if response.status_code == 200:
                result = response.json()
                if result["success"]:
                    return
                statuses = {op["status"] for op in result["operations"]}
            else:
                statuses = {response.status_code}
            text = response.text
            assert statuses <= {200, 201, 204, 409, 503}, text
            self.retries += 1
            time.sleep(0.1 * (attempt + 1))
        pytest.fail(f"Operations still fail after 10 attempts: {text}")

    def update(self, node: Node, **data: Any) -> None:
        # forced: a folder with versions is not renamed or moved otherwise
        self.write(operation("update", "folder", node.id, data=data, force=True))

    def set_attrib(self, node: Node, name: str, value: Any) -> None:
        """Write a few values one after another, `value` is the last one."""
        for i in reversed(range(ROUNDS)):
            self.update(node, attrib={name: value + i})
        node.own[name] = value

    # Expected state

    def ancestors(self, node: Node) -> Iterator[Node]:
        """The folder and its parents, from the folder up."""
        current: Node | None = node
        while current is not None:
            yield current
            current = self.nodes[current.parent] if current.parent else None

    def path(self, node: Node) -> str:
        return "/".join(reversed([n.name for n in self.ancestors(node)]))

    def attrib(self, node: Node, name: str, project_attrib: dict[str, Any]) -> Any:
        for ancestor in self.ancestors(node):
            if name in ancestor.own:
                return ancestor.own[name]
        return project_attrib[name]

    def children(self, node: Node) -> list[Node]:
        return [n for n in self.nodes.values() if n.parent == node.id]

    def has_versions(self, node: Node) -> bool:
        return node.has_version or any(
            self.has_versions(c) for c in self.children(node)
        )


#
# Jobs. Each one changes a single folder (and what it creates below it)
#


def sequence_job(tree: Tree, node: Node, index: int) -> None:
    tree.set_attrib(node, FPS, 40 + index)
    if index == 0:
        # the path of the whole subtree changes while it is written to
        node.name = f"{node.name}_renamed"
        tree.update(node, name=node.name)
    if index == 1:
        tree.set_attrib(node, WIDTH, 1000)


def shot_job(tree: Tree, node: Node, index: int, sequences: list[Node]) -> None:
    kind = index % 4
    if kind != 1:
        tree.set_attrib(node, WIDTH, 2000 + index * 10)
    if kind == 1:
        # moved under the next sequence, which has other values
        current = [s.id for s in sequences].index(node.parent or "")
        node.parent = sequences[(current + 1) % len(sequences)].id
        tree.update(node, parentId=node.parent)
    if kind == 2:
        node.active = False
        tree.update(node, active=False)
    if kind == 3:
        # an own value that is removed again: the inherited one is back
        tree.set_attrib(node, FPS, 60)
        del node.own[FPS]
        tree.update(node, attrib={FPS: None})


def deep_job(tree: Tree, node: Node, index: int) -> None:
    project = tree.project
    kind = index % DEEP
    if kind == 0:
        tree.set_attrib(node, FPS, 100 + index)
        product_id = uuid.uuid4().hex
        version_id = uuid.uuid4().hex
        tree.write(
            operation(
                "create",
                "product",
                product_id,
                data={"name": "review", "folderId": node.id, "productType": "review"},
            ),
            operation(
                "create",
                "version",
                version_id,
                data={"productId": product_id, "version": 1},
            ),
        )
        node.has_version = True
        response = project.api.post(
            f"/api/projects/{project.name}/versions/{version_id}/reviewables",
            content=PNG,
            headers={"x-file-name": "review.png", "content-type": "image/png"},
        )
        assert response.status_code == 200, response.text
        node.has_reviewable = True
    if kind == 1:
        tree.write(
            operation(
                "create",
                "task",
                data={
                    "name": "comp",
                    "taskType": project.task_types[0],
                    "folderId": node.id,
                },
            )
        )
        node.tasks.append("comp")
        extra = tree.add("extra", node.id)
        extra.own[WIDTH] = 3000 + index
        tree.write(tree.create_op(extra, attrib=extra.own))
    if kind == 2:
        tree.set_attrib(node, FPS, 200 + index)
        if index % 2:
            tree.write(operation("delete", "folder", node.id))
            node.deleted = True
        else:
            node.name = f"{node.name}_renamed"
            tree.update(node, name=node.name)


#
# The test
#


@pytest.fixture
def project(api: httpx.Client) -> Iterator[TempProject]:
    with create_temp_project(api) as project:
        yield project


def folder_list(project: TempProject) -> dict[str, dict[str, Any]]:
    response = project.api.get(
        f"/api/projects/{project.name}/folders", params={"attrib": "true"}
    )
    assert response.status_code == 200, response.text
    return {f["id"]: f for f in response.json()["folders"]}


def test_concurrent_writes(project: TempProject):
    api = project.api
    attributes = {a["name"]: a for a in api.get("/api/attributes").json()["attributes"]}
    for name in (FPS, WIDTH):
        if not attributes.get(name, {}).get("data", {}).get("inherit", True):
            pytest.skip(f"Attribute {name} is not inheritable")
    project_attrib = api.get(f"/api/projects/{project.name}").json()["attrib"]

    # Build the tree in one batch, and the jobs to run on it
    tree = Tree(project)
    jobs: list[Callable[[], None]] = []
    create_ops = []
    sequences = [tree.add(f"seq{i}") for i in range(SEQUENCES)]
    for s, sequence in enumerate(sequences):
        create_ops.append(tree.create_op(sequence))
        jobs.append(lambda n=sequence, i=s: sequence_job(tree, n, i))
        for j in range(SHOTS):
            shot_index = s * SHOTS + j
            shot = tree.add(f"sh{shot_index:02d}", sequence.id)
            create_ops.append(tree.create_op(shot))
            jobs.append(lambda n=shot, i=shot_index: shot_job(tree, n, i, sequences))
            for d in range(DEEP):
                deep_index = shot_index * DEEP + d
                deep = tree.add(f"deep{deep_index:02d}", shot.id)
                create_ops.append(tree.create_op(deep))
                jobs.append(lambda n=deep, i=deep_index: deep_job(tree, n, i))
    tree.write(*create_ops)
    assert len(folder_list(project)) == len(tree.nodes)

    # Run the jobs, while the folder list is read (and cached) all the time
    done = threading.Event()

    def reader() -> None:
        while not done.is_set():
            folder_list(project)

    random.Random(0).shuffle(jobs)
    with ThreadPoolExecutor(max_workers=THREADS + 1) as pool:
        reading = pool.submit(reader)
        try:
            for future in [pool.submit(job) for job in jobs]:
                future.result()
        finally:
            done.set()
        reading.result()
    print(f"{len(jobs)} jobs, {tree.retries} retried requests")

    # Compare the result with the expected state
    expected = {n.id: n for n in tree.nodes.values() if not n.deleted}
    folders = folder_list(project)
    errors: list[str] = []
    for folder_id in set(expected) - set(folders):
        errors.append(f"{tree.path(expected[folder_id])}: not in the folder list")
    for folder_id in set(folders) - set(expected):
        errors.append(f"{folders[folder_id]['path']}: should not be in the list")

    def check(node: Node, what: str, value: Any, wanted: Any) -> None:
        if value != wanted:
            errors.append(f"{tree.path(node)}: {what} is {value!r}, not {wanted!r}")

    for node in expected.values():
        if node.id not in folders:
            continue
        folder = folders[node.id]
        children = [c for c in tree.children(node) if not c.deleted]
        check(node, "path", folder["path"].strip("/"), tree.path(node))
        check(node, "parentId", folder["parentId"], node.parent)
        check(node, "ownAttrib", sorted(folder["ownAttrib"]), sorted(node.own))
        check(node, "active", folder["active"], node.active)
        visible = all(n.active for n in tree.ancestors(node))
        check(node, "visible", folder["visible"], visible)
        check(node, "hasChildren", folder["hasChildren"], bool(children))
        check(node, "hasTasks", folder["hasTasks"], bool(node.tasks))
        check(node, "taskNames", folder["taskNames"], node.tasks)
        check(node, "hasVersions", folder["hasVersions"], tree.has_versions(node))
        check(node, "hasReviewables", folder["hasReviewables"], node.has_reviewable)

        # The list shows what the folder exports. A folder loaded on its own
        # takes the inherited values from what its parent exports.
        entity = project.get("folder", node.id)
        check(node, "entity path", entity["path"].strip("/"), tree.path(node))
        for name in (FPS, WIDTH):
            wanted = tree.attrib(node, name, project_attrib)
            check(node, f"list {name}", folder["attrib"].get(name), wanted)
            check(node, f"entity {name}", entity["attrib"].get(name), wanted)

    assert not errors, "\n".join(errors)
