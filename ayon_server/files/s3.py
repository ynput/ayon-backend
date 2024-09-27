import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

import boto3
from fastapi import Request
from nxtools import logging
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

if TYPE_CHECKING:
    from ayon_server.files.project_storage import ProjectStorage


class S3Config(BaseModel):
    aws_access_key_id: str | None = Field(
        default_factory=lambda: os.getenv("AWS_ACCESS_KEY_ID")
    )
    aws_secret_access_key: str | None = Field(
        default_factory=lambda: os.getenv("AWS_SECRET_ACCESS_KEY")
    )
    session_token: str | None = Field(
        default_factory=lambda: os.getenv("AWS_SESSION_TOKEN")
    )
    endpoint_url: str | None = Field(
        default_factory=lambda: os.getenv("S3_ENDPOINT_URL")
    )
    region_name: str | None = Field(default_factory=lambda: os.getenv("S3_REGION_NAME"))


# Get client


def _get_s3_client(storage: "ProjectStorage"):
    if storage._s3_client is None:
        if storage.s3_config is None:
            cfg = {}
        else:
            cfg = storage.s3_config.dict(exclude_none=True)
        storage._s3_client = boto3.client("s3", **cfg)
    return storage._s3_client


async def get_s3_client(storage: "ProjectStorage"):
    return await run_in_threadpool(_get_s3_client, storage)


# Presigned URLs


def _get_signed_url(storage: "ProjectStorage", key: str, ttl: int = 3600) -> str:
    client = _get_s3_client(storage)
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": storage.bucket_name, "Key": key},
        ExpiresIn=ttl,
    )


async def get_signed_url(storage: "ProjectStorage", key: str, ttl: int = 3600) -> str:
    return await run_in_threadpool(_get_signed_url, storage, key, ttl)


# Simple file store / retrieve


def _store_s3_file(storage: "ProjectStorage", key: str, data: bytes) -> None:
    client = _get_s3_client(storage)
    client.put_object(Bucket=storage.bucket_name, Key=key, Body=data)


async def store_s3_file(storage: "ProjectStorage", key: str, data: bytes) -> None:
    await run_in_threadpool(_store_s3_file, storage, key, data)


def _retrieve_s3_file(storage: "ProjectStorage", key: str) -> bytes:
    client = _get_s3_client(storage)
    response = client.get_object(Bucket=storage.bucket_name, Key=key)
    return response["Body"].read()


async def retrieve_s3_file(storage: "ProjectStorage", key: str) -> bytes:
    return await run_in_threadpool(_retrieve_s3_file, storage, key)


def _delete_s3_file(storage: "ProjectStorage", key: str):
    client = _get_s3_client(storage)
    client.delete_object(Bucket=storage.bucket_name, Key=key)


async def delete_s3_file(storage: "ProjectStorage", key: str):
    await run_in_threadpool(_delete_s3_file, storage, key)


# Multipart upload to S3 with async queue
# Used for larger files


class S3Uploader:
    _worker_task: asyncio.Task[Any] | None
    _queue: asyncio.Queue[bytes | None]

    def __init__(self, client, bucket_name: str, max_queue_size=5, max_workers=4):
        self._client = client
        self._multipart = None
        self._parts: list[tuple[int, str]] = []
        self._key: str | None = None
        self.bucket_name = bucket_name

        # Limited-size async queue for chunk uploads to prevent over-filling
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=max_queue_size)
        self._worker_task: asyncio.Task[Any] | None = None
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def _init_file_upload(self, key: str):
        logging.debug(f"Initiating upload for {key}", user="s3")
        if self._multipart:
            raise Exception("Multipart upload already started")

        self._multipart = self._client.create_multipart_upload(
            Bucket=self.bucket_name,
            Key=key,
        )

        self._parts = []
        self._key = key

    def _upload_chunk(self, chunk: bytes, part_number: int):
        """
        Sync method for uploading a single chunk to S3.
        This will be offloaded to a thread by the background worker.
        """

        assert self._multipart  # this shouldn't happen

        res = self._client.upload_part(
            Body=chunk,
            Bucket=self.bucket_name,
            Key=self._key,
            PartNumber=part_number,
            UploadId=self._multipart["UploadId"],
        )
        etag = res["ResponseMetadata"]["HTTPHeaders"]["etag"]
        return part_number, etag

    async def _worker(self):
        """
        Async worker that continuously processes chunks in the queue.
        Uploads to S3 and maintains part order.
        """
        part_number = 1

        while True:
            chunk = await self._queue.get()
            if chunk is None:
                break  # Exit signal received

            # Upload the chunk in a thread pool, and block asyncio minimally
            part_number, etag = await asyncio.get_running_loop().run_in_executor(
                self._executor,
                self._upload_chunk,
                chunk,
                part_number,
            )
            self._parts.append((part_number, etag))
            part_number += 1
            self._queue.task_done()  # Mark chunk as processed

    async def init_file_upload(self, file_path: str):
        await asyncio.get_running_loop().run_in_executor(
            self._executor,
            self._init_file_upload,
            file_path,
        )
        self._worker_task = asyncio.create_task(self._worker())

    async def push_chunk(self, chunk: bytes):
        """
        Push chunk to the queue for background processing by the worker.
        If the queue is full, wait until there's space.
        """
        await self._queue.put(chunk)

    def _complete(self):
        if not self._multipart:
            return

        parts = [{"ETag": etag, "PartNumber": i} for i, etag in self._parts]
        self._client.complete_multipart_upload(
            Bucket=self.bucket_name,
            Key=self._key,
            MultipartUpload={"Parts": parts},
            UploadId=self._multipart["UploadId"],
        )
        self._multipart = None
        self._parts = []
        self._key = None

    async def complete(self):
        """
        Signal the worker to complete and wait for uploads to finish.
        Finalize the multipart upload.
        """
        await self._queue.put(None)  # Shutdown signal for the worker
        if self._worker_task:
            await self._worker_task  # Wait for the worker to finish.

        logging.debug(f"Completing upload for {self._key}", user="s3")
        await asyncio.get_running_loop().run_in_executor(self._executor, self._complete)

    def _abort(self) -> None:
        if not self._multipart:
            return

        logging.warning(f"Aborting upload for {self._key}", user="s3")
        self._client.abort_multipart_upload(
            Bucket=self.bucket_name,
            Key=self._key,
            UploadId=self._multipart["UploadId"],
        )
        self._multipart = None
        self._parts = []
        self._key = None

    async def abort(self) -> None:
        """Abort the multipart upload if there's an exception."""
        await asyncio.get_running_loop().run_in_executor(self._executor, self._abort)

    def __del__(self):
        """Ensure clean-up if the object is destroyed prematurely."""
        self._abort()


async def handle_s3_upload(
    storage: "ProjectStorage",
    request: Request,
    path: str,
) -> int:
    start_time = time.monotonic()
    client = await get_s3_client(storage)
    assert storage.bucket_name
    uploader = S3Uploader(client, storage.bucket_name)

    await uploader.init_file_upload(path)
    i = 0
    buffer_size = 1024 * 1024 * 5
    buff = b""

    async for chunk in request.stream():
        buff += chunk
        if len(buff) >= buffer_size:
            await uploader.push_chunk(buff)
            i += len(buff)
            buff = b""

    if buff:
        await uploader.push_chunk(buff)
        i += len(buff)

    await uploader.complete()
    upload_time = time.monotonic() - start_time

    logging.info(f"Uploaded {i} bytes to {path} in {upload_time:.2f} seconds")
    return i
