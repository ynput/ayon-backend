from collections import defaultdict


class HierarchyResolver:
    branch_name = "children"
    id_key = "id"
    parent_key = "parentId"

    def __init__(self, source: list[dict] | None = None):
        """
        You can either pass a source list to the constructor or call
        the append method for each item, and finally call the commit
        method to build the hierarchy (to avoid unnecessary memory usage
        caused by creating an intermediate list).
        """
        if source is None:
            source = []
        self._parents = defaultdict(list)
        self._hierarchy = []
        self.count = 0
        if not source:
            return
        for item in source:
            self.append(item)
        self.commit()

    def append(self, item: dict) -> None:
        parent_id = item[self.parent_key]
        self._parents[parent_id].append(item)
        self.count += 1

    def commit(self):
        self._hierarchy = self._build_tree(self._parents, None)

    def _build_tree(self, parents, parent=None):
        items = []
        for child in parents.get(parent, []):
            if not child:
                continue
            items.append(child)
            if child[self.id_key] in parents.keys():
                items[-1][self.branch_name] = self._build_tree(
                    parents, child[self.id_key]
                )
        return items

    @property
    def hierarchy(self):
        # TODO: use LRU cache
        return self._hierarchy

    def all(self) -> list:
        """Return all items of the hierarchy."""
        return self.hierarchy

    def filtered(
        self, search: str = "", types: list[int] | None = None, folder=None
    ) -> list:
        """Return filtered hiearchy.

        You may specify a serch string and list of types to
        narrow the search.
        """
        if types is None:
            types = []
        new_tree = []
        for item in folder or self.hierarchy:
            if item.get("name", "").find(search) > -1:
                new_tree.append(item)
            elif item.get(self.branch_name):
                if new_children := self.filtered(search, types, item[self.branch_name]):
                    new_item = item.copy()
                    new_item[self.branch_name] = new_children
                    new_tree.append(new_item)
        return new_tree

    def __call__(self, search: str = "", types: list[int] | None = None) -> list:
        if types is None:
            types = []
        if not (search or types):
            return self.all()
        return self.filtered(search)
