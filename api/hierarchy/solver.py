from collections import defaultdict
from typing import Any

HierarchyType = list[dict[str, Any]]


class HierarchyResolver:
    branch_name = "children"
    id_key = "id"
    parent_key = "parentId"

    def __init__(self, source: HierarchyType | None = None):
        """
        You can either pass a source list to the constructor or call
        the append method for each item, and finally call the commit
        method to build the hierarchy (to avoid unnecessary memory usage
        caused by creating an intermediate list).
        """
        if source is None:
            source = []
        self._parents: defaultdict[str, list[Any]] = defaultdict(list[Any])
        self._hierarchy: list[Any] = []
        self.count = 0
        if not source:
            return
        for item in source:
            self.append(item)
        self.commit()

    def append(self, item: dict[str, Any]) -> None:
        parent_id = item[self.parent_key]
        self._parents[parent_id].append(item)
        self.count += 1

    def commit(self) -> None:
        self._hierarchy = self._build_tree(self._parents, None)

    def _build_tree(
        self, parents: defaultdict[str, list[Any]], parent: str | None = None
    ) -> HierarchyType:
        items: HierarchyType = []
        for child in parents.get(parent, []):  # type: ignore
            if not child:
                continue
            items.append(child)
            if child[self.id_key] in parents.keys():
                items[-1][self.branch_name] = self._build_tree(
                    parents, child[self.id_key]
                )
        return items

    @property
    def hierarchy(self) -> HierarchyType:
        # TODO: use LRU cache
        return self._hierarchy

    def all(self) -> HierarchyType:
        """Return all items of the hierarchy."""
        return self.hierarchy

    def filtered(
        self,
        search: str = "",
        types: list[int] | None = None,
        folder: HierarchyType | None = None,
    ) -> HierarchyType:
        """Return filtered hiearchy.

        You may specify a serch string and list of types to
        narrow the search.
        """
        if types is None:
            types = []
        new_tree = []
        for item in self.hierarchy if folder is None else folder:
            if item.get("name", "").find(search) > -1:
                new_tree.append(item)
            elif item.get(self.branch_name):
                if new_children := self.filtered(search, types, item[self.branch_name]):
                    new_item = item.copy()
                    new_item[self.branch_name] = new_children
                    new_tree.append(new_item)
        return new_tree

    def __call__(
        self,
        search: str = "",
        types: list[int] | None = None,
    ) -> HierarchyType:
        if types is None:
            types = []
        if not (search or types):
            return self.all()
        return self.filtered(search)
