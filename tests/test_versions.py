import sys

import pytest

# from tests.common import API


@pytest.mark.order(0)
def test_python_version():
    """Ensure we're running Python 3.10"""
    assert sys.version_info.major >= 3 and sys.version_info.minor >= 10


# def test_login():
#    api = API.login("admin", "admin")
