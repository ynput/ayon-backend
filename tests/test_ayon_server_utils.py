from ayon_server.utils import dict_remove_path


class TestDictRemovePath:
    def test_remove_existing_path(self):
        data = {"a": {"b": {"c": 1}}}
        dict_remove_path(data, ["a", "b", "c"], remove_orphans=False)
        assert data == {"a": {"b": {}}}

        dict_remove_path(data, ["a", "b"], remove_orphans=False)
        assert data == {"a": {}}

    def test_remove_non_existent_path(self):
        data = {"a": {"b": {"c": 1}}}
        dict_remove_path(data, ["a", "x", "c"])
        assert data == {"a": {"b": {"c": 1}}}

    def test_remove_with_orphans(self):
        data = {"a": {"b": {"c": 1}}}
        dict_remove_path(data, ["a", "b", "c"], remove_orphans=True)
        assert data == {}

    def test_remove_without_orphans(self):
        data = {"a": {"b": {"c": 1}}}
        dict_remove_path(data, ["a", "b", "c"], remove_orphans=False)
        assert data == {"a": {"b": {}}}

    def test_remove_path_with_non_dict(self):
        data = {"a": {"b": "not a dict"}}
        dict_remove_path(data, ["a", "b", "c"])
        assert data == {"a": {"b": "not a dict"}}
