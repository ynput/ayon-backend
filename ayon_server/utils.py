"""A set of commonly used functions."""

import asyncio
import datetime
import functools
import hashlib
import itertools
import json
import random
import threading
import time
import uuid
from typing import Any, Callable, Iterable

import codenamize
import orjson
from pydantic import BaseModel, Field


def json_loads(data: str) -> Any:
    """Load JSON data."""
    return orjson.loads(data)


def isinstance_namedtuple(obj: Any) -> bool:
    """Check if an object is an instance of a named tuple."""
    return (
        isinstance(obj, tuple) and hasattr(obj, "_asdict") and hasattr(obj, "_fields")
    )


def json_print(data: Any, header: str | None = None) -> None:
    """Print JSON data."""
    if header:
        print()
        print(header, flush=True)
    print(json.dumps(data, indent=2), flush=True)
    if header:
        print()


def json_default_handler(value: Any) -> Any:
    if isinstance_namedtuple(value):
        return list(value)

    if isinstance(value, BaseModel):
        value.dict()

    if isinstance(value, datetime.datetime):
        return value.isoformat()

    raise TypeError(f"Type {type(value)} is not JSON serializable")


def json_dumps(data: Any, *, default: Callable[[Any], Any] | None = None) -> str:
    """Dump JSON data."""
    return orjson.dumps(data, default=json_default_handler).decode()


def hash_data(data: Any) -> str:
    """Create a SHA-256 hash from arbitrary (json-serializable) data."""
    if isinstance(data, (int, float, bool, dict, list, tuple)):
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
            k: v for k, v in data.items() if not any(k.startswith(key) for key in keys)
        }
    return data


def dict_remove_path(
    data: dict[str, Any],
    path: list[str],
    remove_orphans: bool = True,
):
    """Delete a key in a nested dictionary specified by its path."""
    parents = [data]
    for key in path[:-1]:
        if key in parents[-1]:
            n = parents[-1][key]
            if isinstance(n, dict):
                parents.append(n)
            else:
                return  # Early exit if the path is invalid
        else:
            return  # Early exit if the key does not exist in the path
    if path[-1] in parents[-1]:
        del parents[-1][path[-1]]
    else:
        return  # Early exit if the final key does not exist

    if not remove_orphans:
        return

    for i, key in enumerate(reversed(path[:-1]), 1):
        if not parents[-i]:
            del parents[-i - 1][key]
        else:
            break


def batched(iterable: Iterable[Any], n: int):
    """Implement batched function to split an iterable into batches of size n

    We need this instead of itertools.batched as we need to run on Python 3.11
    """
    it = iter(iterable)
    while True:
        batch = list(itertools.islice(it, n))
        if not batch:
            break
        yield batch


def parse_access_token(authorization: str) -> str | None:
    """Parse an authorization header value.

    Get a TOKEN from "Bearer TOKEN" and return a token
    string or None if the input value does not match
    the expected format (64 bytes string)
    """
    if (not authorization) or not isinstance(authorization, str):
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


def parse_api_key(authorization: str) -> str | None:
    if (not authorization) or not isinstance(authorization, str):
        return None
    try:
        ttype, token = authorization.split()
    except ValueError:
        return None
    if ttype.lower() != "apikey":
        return None
    return token


@functools.lru_cache(maxsize=128)
def obscure(text: str):
    obscured = ""
    for c in text:
        if c == " ":
            obscured += c
        else:
            obscured += "*"
    return obscured


@functools.lru_cache(maxsize=128)
def get_nickname(text: str, length: int = 1):
    return codenamize.codenamize(text, length)


class EntityID:
    example: str = "af10c8f0e9b111e9b8f90242ac130003"
    META: dict[str, Any] = {
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
        raise ValueError(f"Invalid entity ID {entity_id}")

    @classmethod
    def field(cls, name: str = "entity") -> Field:  # type: ignore
        return Field(  # type: ignore
            title=f"{name.capitalize()} ID",
            description=f"{name.capitalize()} ID",
            **cls.META,
        )


class SQLTool:
    """SQL query construction helpers."""

    @staticmethod
    def array(elements: list[str] | list[int], curly=False, nobraces=False) -> str:
        """Return a SQL-friendly list string."""
        if nobraces:
            start = end = ""
        else:
            start = "'{" if curly else "("
            end = "}'" if curly else ")"
        return (
            start
            + (
                ", ".join(
                    [
                        (f"'{e}'" if isinstance(e, str) and not curly else str(e))
                        for e in elements
                    ]
                )
            )
            + end
        )

    @staticmethod
    def id_array(ids: list[str] | list[uuid.UUID]) -> str:
        """Return a SQL-friendly list of IDs.

        list(['a', 'b', 'c']) becomes str("('a', 'b', 'c')")
        Also provided list elements must be valid entity IDs

        Null values will be ignored.
        """
        parsed = [EntityID.parse(id, allow_nulls=True) for id in ids]
        return "(" + (", ".join([f"'{id}'" for id in parsed if id is not None])) + ")"

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
    def insert(table: str, **kwargs: Any) -> list[Any]:
        """Return an SQL INSERT statement.

        The result format is a list, in which the first element
        is the SQL statement and the other items are the values,
        so the results could be used as:.
            Postgres.execute(*SQLTool.insert(...))
        """

        keys = list(kwargs.keys())
        command = f"""
            INSERT INTO {table}
            ({', '.join(keys)})
            VALUES
            ({ ', '.join([f'${i+1}' for i, _ in enumerate(keys)]) })
            """
        result: list[Any] = [command]
        for key in keys:
            result.append(kwargs[key])
        return result

    @staticmethod
    def update(
        table: str,
        conditions: str,
        **kwargs: Any,
    ) -> list[Any]:
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
            result.append(kwargs[key])
        return result


def run_blocking_coro(coro) -> Any:
    result = {"output": None}

    def execute():
        loop = asyncio.new_event_loop()
        task = loop.create_task(coro())
        # asyncio.set_event_loop(loop)
        loop.run_until_complete(task)
        result["output"] = task.result()  # noqa
        loop.close()

    thread = threading.Thread(target=execute)
    thread.start()
    thread.join()
    return result["output"]
