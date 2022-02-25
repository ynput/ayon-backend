import sys
import json
import asyncio

from nxtools import critical_error, log_traceback
from .demogen import DemoGen


async def main():
    data = sys.stdin.read()
    if not data:
        critical_error("No data provided")

    try:
        project = json.loads(data)
    except Exception:
        log_traceback()
        critical_error("Invalid project data provided")

    # Set validate to True, to validate source data
    # against the Pydantic models. It's slightly slower.
    demo = DemoGen(validate=True)
    await demo.populate(**project)


if __name__ == "__main__":
    asyncio.run(main())
