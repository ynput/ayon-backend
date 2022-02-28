import csv
import io

import httpx
from nxtools import logging

from openpype.lib.postgres import Postgres
from openpype.utils import json_dumps


def parse_example(example, atype):
    example = example.strip()
    if not example:
        return {}
    example = {
        "integer": int,
        "string": str,
        "float": float,
        "boolean": lambda x: True if x.lower == "true" else False,
        "list_of_strings": lambda x: None,
    }[atype](example)
    if example:
        return {"example": example}
    return {}


def parse_intval(name, value):
    value = value.strip()
    if not value:
        return {}
    if not value.isdigit():
        return {}
    value = int(value)
    if value:
        return {name: value}
    return {}


async def deploy_attributes():
    doc_id = "1ABtEVedg5OZ5XvpYw5ZQS0vTZ9ISdkz4AxluF5jgx18"
    url = f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv"

    async with httpx.AsyncClient() as client:
        res = await client.get(url, follow_redirects=True)

    if res.status_code != 200:
        return

    csvio = io.StringIO(res.text)
    adata = csv.reader(csvio, delimiter=",")

    await Postgres.execute("DELETE FROM public.attributes")

    for i, row in enumerate(adata):
        if i == 0:
            # TODO: parse columns here
            continue

        (
            name,
            scope,
            atype,
            title,
            example,
            gt,
            lt,
            regex,
            min_len,
            max_len,
            description,
        ) = row

        try:
            scope = [
                {
                    "p": "project",
                    "u": "user",
                    "f": "folder",
                    "t": "task",
                    "s": "subset",
                    "v": "version",
                    "r": "representation",
                }[k.strip().lower()]
                for k in scope.split(",")
            ]
        except KeyError:
            logging.error(f"Unknown scope specified on {name}. Skipping")
            continue

        if atype not in ["integer", "float", "string", "boolean", "list_of_strings"]:
            logging.error(f"Unknown type sepecified on {name}. Skipping.")
            continue

        data = {
            "type": atype,
            "title": title,
            **parse_example(example, atype),
            **parse_intval("gt", gt),
            **parse_intval("lt", lt),
            **parse_intval("min_length", min_len),
            **parse_intval("max_length", max_len),
        }

        if regex.strip():
            data["regex"] = regex.strip()

        if description.strip():
            data["description"] = description.strip()

        await Postgres.execute(
            """
            INSERT INTO public.attributes
                (name, scope, builtin, data)
            VALUES
                ($1, $2, TRUE, $3)
            """,
            name,
            scope,
            json_dumps(data),
        )
