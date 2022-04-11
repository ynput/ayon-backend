from nxtools import logging


class OpenPypeException(Exception):
    """Base class for all OpenPype exceptions."""

    detail: str = "Error"
    status: int = 500

    def __init__(
        self,
        detail: str | None = None,
        log: bool | str = False,
    ) -> None:

        if detail is not None:
            self.detail = detail

        if log is True:
            logging.error(f"EXCEPTION: {self.status} {self.detail}")
        elif type(log) is str:
            logging.error(f"EXCEPTION: {self.status} {log}")

        super().__init__(self.detail)


class BadRequestException(OpenPypeException):
    """Raised when the request is malformed or missing required fields."""

    detail: str = "Bad request"
    status = 400


class UnauthorizedException(OpenPypeException):
    """Raised when a user is not authorized.

    And tries to access a resource without the proper credentials.
    """

    detail: str = "Not logged in"
    status: int = 401


class ForbiddenException(OpenPypeException):
    """Raised when a user is not permitted access to the resource.

    despite providing authentication such as insufficient
    permissions of the authenticated account.
    """

    detail: str = "Forbidden"
    status: int = 403


class NotFoundException(OpenPypeException):
    """Exception raised when a resource is not found."""

    detail: str = "Not found"
    status: int = 404


class ConstraintViolationException(OpenPypeException):
    """Exception raised when a DB constraint is violated."""

    detail: str = "Constraint violation"
    status: int = 409


class UnsupportedMediaException(OpenPypeException):
    """Exception raised when a provided media is not supported."""

    detail: str = "Unsupported media"
    status: int = 415


class LowPasswordComplexityException(OpenPypeException):
    """Exception raised when a new password doesn't meet the required complexity."""

    detail: str = "Password is not seure enough"
    status: int = 400
