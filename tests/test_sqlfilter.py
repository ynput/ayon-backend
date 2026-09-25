import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


from ayon_server.sqlfilter import QueryCondition, build_condition


def _cond(key: str, operator: str, value) -> str:
    return build_condition(
        QueryCondition(key=key, operator=operator, value=value),
        table_prefix="folders",
    )


class TestNegativeOperatorsIncludeNull:
    """Negative operators must not drop rows where the field is NULL/unset.

    `NOT (NULL = ANY(...))` evaluates to NULL in Postgres, which a WHERE
    clause treats as false, so unset attributes were silently filtered out.
    """

    def test_notin_json_attribute(self):
        sql = _cond("attrib.myAttribute", "notin", ["myValue"])
        assert sql == (
            "NOT COALESCE((folders.attrib->'myAttribute')::text "
            "= ANY(array['\"myValue\"']), FALSE)"
        )

    def test_notin_column(self):
        sql = _cond("status", "notin", ["Done"])
        assert sql == "NOT COALESCE((folders.status)::text = ANY(array['Done']), FALSE)"

    def test_ne_json_attribute(self):
        sql = _cond("attrib.myAttribute", "ne", "myValue")
        assert sql == (
            "folders.attrib->'myAttribute' IS DISTINCT FROM '\"myValue\"'::jsonb"
        )

    def test_ne_column(self):
        sql = _cond("status", "ne", "Done")
        assert sql == "folders.status IS DISTINCT FROM 'Done'"

    def test_excludes_array_column(self):
        sql = _cond("tags", "excludes", "foo")
        assert sql == "NOT COALESCE('foo' = ANY(folders.tags), FALSE)"

    def test_excludesany_array_column(self):
        sql = _cond("tags", "excludesany", ["a", "b"])
        assert sql == "NOT COALESCE((folders.tags)::text[] && array['a', 'b'], FALSE)"

    def test_excludesall_array_column(self):
        sql = _cond("tags", "excludesall", ["a", "b"])
        assert sql == "NOT COALESCE((folders.tags)::text[] @> array['a', 'b'], FALSE)"

    def test_excludesall_json_attribute(self):
        sql = _cond("attrib.myList", "excludesall", ["a"])
        assert sql == (
            "NOT COALESCE((folders.attrib->'myList')::jsonb @> '[\"a\"]'::jsonb, FALSE)"
        )
