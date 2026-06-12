import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from ayon_server.operations.project_level.__init__ import _log_validation_error


def test_log_validation_error_handles_braces_in_payload():
    validation_errors = [
        {
            "loc": ("attrib", "customAttrib", 2),
            "msg": "unexpected value",
            "type": "value_error",
            "ctx": {"value": "4"},
        }
    ]

    _log_validation_error(
        "[FOLDER UPDATE]",
        validation_errors,
        project_name="demo",
        operation_id="operation-1",
    )
