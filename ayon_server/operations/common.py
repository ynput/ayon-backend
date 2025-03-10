__all__ = ["RollbackException", "OperationType"]

from typing import Literal


class RollbackException(Exception):
    pass


OperationType = Literal["create", "update", "delete"]
