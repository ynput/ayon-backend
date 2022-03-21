"""A set of commonly used functions."""

import hashlib
import random
import re
import time
import uuid
from typing import Any

import orjson
from pydantic import Field


def json_loads(data: str) -> Any:
    """Load JSON data."""
    return orjson.loads(data)


def json_dumps(data: Any, *, default=None) -> str:
    """Dump JSON data."""
    return orjson.dumps(data, default=default).decode()


def hash_data(data: Any) -> str:
    """Create a SHA-256 hash from arbitrary (json-serializable) data."""
    if type(data) in [int, float, bool, dict, list]:
        data = json_dumps(data)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def create_hash() -> str:
    """Create a pseudo-random hash (used as and access token)."""
    return hash_data([time.time(), random.random()])


def create_uuid() -> str:
    """Create UUID without hyphens."""
    return uuid.uuid1().hex


def dict_exclude(
    data: dict[Any, Any],
    keys: list[str],
    mode: str = "exact",
) -> dict[Any, Any]:
    """Return a copy of the dictionary with the specified keys removed."""
    if mode == "exact":
        return {k: v for k, v in data.items() if k not in keys}
    elif mode == "startswith":
        return {
            k: v
            for k, v in data.items()
            if not any([k.startswith(key) for key in keys])
        }
    return data


def validate_name(name: str) -> bool:
    """Validate a name."""
    if not name:
        return False
    if not re.match(r"^[a-zA-Z0-9_]+$", name):
        return False
    return True


def parse_access_token(authorization: str) -> str | None:
    """Parse an authorization header value.

    Get a TOKEN from "Bearer TOKEN" and return a token
    string or None if the input value does not match
    the expected format (64 bytes string)
    """
    if (not authorization) or type(authorization) != str:
        return None
    try:
        # ttype is not a ttypo :)
        ttype, token = authorization.split()
    except ValueError:
        return None
    if ttype.lower() != "bearer":
        return None
    if len(token) != 64:
        return None
    return token


class EntityID:
    META = {
        "example": "af10c8f0e9b111e9b8f90242ac130003",
        "min_length": 32,
        "max_length": 32,
        "regex": r"^[0-9a-f]{32}$",
    }

    @classmethod
    def create(cls) -> str:
        return create_uuid()

    @classmethod
    def parse(
        cls, entity_id: str | uuid.UUID | None, allow_nulls: bool = False
    ) -> str | None:
        """Convert UUID object or its string representation to string"""
        if entity_id is None and allow_nulls:
            return None
        if isinstance(entity_id, uuid.UUID):
            return entity_id.hex
        if isinstance(entity_id, str):
            entity_id = entity_id.replace("-", "")
            if len(entity_id) == 32:
                return entity_id
        # TODO: Raise OpenPypeException, not Value error
        raise ValueError("Invalid entity ID")

    @classmethod
    @property
    def example(cls):
        return cls.meta["example"]

    @classmethod
    def field(cls, name: str = "entity") -> Field:
        return Field(
            title=f"{name.capitalize()} ID",
            description=f"{name.capitalize()} ID",
            **cls.META,
        )


class SQLTool:
    """SQL query construction helpers."""

    @staticmethod
    def array(elements: list[str] | list[int]):
        """Return a SQL-friendly list string."""
        return (
            "("
            + (", ".join([(f"'{e}'" if type(e) == str else str(e)) for e in elements]))
            + ")"
        )

    @staticmethod
    def id_array(ids: list[str] | list[uuid.UUID]) -> str:
        """Return a SQL-friendly list of IDs.

        list(['a', 'b', 'c']) becomes str("('a', 'b', 'c')")
        Also provided list elements must be valid entity IDs
        """
        assert all([EntityID.parse(id, allow_nulls=True) for id in ids])
        return "(" + (", ".join([f"'{id}'" for id in ids])) + ")"

    @staticmethod
    def conditions(
        condition_list: list[str],
        operand: str | None = "AND",
        add_where: bool | None = True,
    ) -> str:
        """Return a SQL-friendly list of conditions.

        list(['a = 1', 'b = 2']) becomes str("a = 1 AND b = 2")
        """
        if condition_list:
            return ("WHERE " if add_where else "") + (
                f" {operand} ".join(condition_list)
            )
        return ""

    @staticmethod
    def order(
        order: str | None = None,
        desc: bool | None = False,
        limit: int | None = None,
        offset: int | None = None,
    ) -> str:
        result = []
        if order:
            result.append(f"ORDER BY {order}")
            if desc:
                result.append("DESC")
            if limit:
                result.append(f"LIMIT {limit}")
                if offset:
                    result.append(f"OFFSET {offset}")
        if result:
            return " ".join(result)
        return ""

    @staticmethod
    def insert(table: str, **kwargs):
        """Return an SQL INSERT statement."""
        keys = list(kwargs.keys())
        command = f"""
            INSERT INTO {table}
            ({
                ', '.join(keys)
            })
            VALUES
            ({
                ', '.join([f'${i+1}' for i, _ in enumerate(keys)])
            })
            """
        result = [command]
        for key in keys:
            if type(kwargs[key]) == dict:
                result.append(json_dumps(kwargs[key]))
            else:
                result.append(kwargs[key])
        return result

    @staticmethod
    def update(
        table: str,
        conditions: str,
        **kwargs,
    ):
        """Return an SQL UPDATE statement.

        Updated fields shall be specified in kwargs.
        Conditions argument is a list of conditions provided as a string
        including WHERE statement (so it is compatible with SQLTool.conditions
        function without additional arguments.)

        Result is provided as an array with the SQL command as the first
        argument and followed by the values, so it is ready to be used in
        the Postgres.execute function when unpacked using a star operator.
        """

        keys = list(kwargs.keys())
        command = f"""
            UPDATE {table}
            SET {', '.join([f'{key} = ${i+1}' for i, key in enumerate(keys)])}
            {conditions}
            """

        result = [command]
        for key in keys:
            if type(kwargs[key]) == dict:
                result.append(json_dumps(kwargs[key]))
            else:
                result.append(kwargs[key])
        return result
