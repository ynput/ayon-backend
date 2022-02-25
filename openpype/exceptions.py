class OpenPypeException(Exception):
    """Base class for all OpenPype exceptions."""

    def __init__(self, detail: str = "Server error") -> None:
        super().__init__(detail)
        self.detail = detail


class UnauthorizedException(OpenPypeException):
    """Raised when a user is not authorized.

    And tries to access a resource without the proper credentials.
    """

    def __init__(self, detail: str = "Unauthorized") -> None:
        super().__init__(detail)


class ForbiddenException(OpenPypeException):
    """Raised when a user is not permitted access to the resource.

    despite providing authentication such as insufficient
    permissions of the authenticated account.
    """

    def __init__(self, detail: str = "Forbidden") -> None:
        super().__init__(detail)


class RecordNotFoundException(OpenPypeException):
    """Exception raised when a resource is not found."""

    def __init__(self, detail: str = "Record not found") -> None:
        super().__init__(detail)


class ConstraintViolationException(OpenPypeException):
    """Exception raised when a DB constraint is violated."""

    def __init__(self, detail: str = "Constraint violation") -> None:
        super().__init__(detail)
