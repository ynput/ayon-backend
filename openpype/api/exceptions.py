from nxtools import logging


class APIException(Exception):
    def __init__(
        self, status: int = 500, detail: str = "Error", log: bool | str = True
    ):
        self.status = status
        self.detail = detail
        super().__init__(self.detail)
        if log is True:
            logging.error(f"EXCEPTION: {status} {detail}")
        elif type(log) is str:
            logging.error(f"EXCEPTION: {status} {log}")
