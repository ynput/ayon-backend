__all__ = [
    "parse_postgres_exception",
    "ForeignKeyViolationError",
    "IntegrityConstraintViolationError",
    "NotNullViolationError",
    "UniqueViolationError",
]


import re
from typing import Any

from asyncpg.exceptions import (
    ForeignKeyViolationError,
    IntegrityConstraintViolationError,
    NotNullViolationError,
    UniqueViolationError,
)


def parse_postgres_exception(exc: IntegrityConstraintViolationError) -> dict[str, Any]:
    if isinstance(exc, NotNullViolationError):
        return {
            "detail": f"Missing required field: {exc.column_name}",
            "status_code": 400,
        }

    elif isinstance(exc, ForeignKeyViolationError):
        pg_detail = exc.detail

        # exctract field name and tail from pg_detail

        if pg_detail is not None:
            m = re.match(
                r"Key \((?P<field>.*)\)=\((?P<value>.*)\) (?P<tail>.*)",
                pg_detail,
            )
            if m is None:
                detail = exc.message
            else:
                field = m.group("field")
                value = m.group("value")
                tail = m.group("tail")
                detail = f"{field} '{value}' {tail}"
        else:
            detail = exc.message
        return {
            "detail": detail,
            "error": "foreign-key-violation",
            "code": 409,
        }

    elif isinstance(exc, UniqueViolationError):
        pg_detail = exc.detail
        # exctract field name and value from pg_detail

        if pg_detail is not None:
            m = re.match(
                r"Key \((?P<field>.*)\)=\((?P<value>.*)\) already exists.", pg_detail
            )
            if m is None:
                detail = "Unique constraint violation."
            else:
                table_name = exc.table_name or "unknown"
                record_type = table_name.rstrip("s").capitalize()
                detail = (
                    f"{record_type} with {m.group('field')} "
                    f"'{m.group('value')}' already exists."
                )
        else:
            detail = exc.message

        return {
            "detail": detail,
            "error": "unique-violation",
            "code": 409,
        }

    return {
        "detail": exc.message,
        "error": "integrity-constraint-violation",
        "code": 500,
    }
