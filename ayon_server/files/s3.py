import os
from typing import TYPE_CHECKING

try:
    import boto3

    has_boto3 = True
except ModuleNotFoundError:
    has_boto3 = False

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
        if not has_boto3:
            raise Exception("boto3 is not installed")
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


# Upload to s3


class S3Uploader:
    """
    This is a proof of concept. Ideally the logic should be rewritten:
    We should spawn one thread and then use a queue to push chunks to the thread,
    instead of creating a new thread for each chunk.
    """

    def __init__(self, client, bucket_name: str):
        self._client = client
        self._multipart = None
        self._parts: list[tuple[int, str]] = []
        self._key: str | None = None
        self.bucket_name = bucket_name

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

    def _push_chunk(self, chunk: bytes):
        if not self._multipart:
            raise Exception("Multipart upload not started")

        part_number = len(self._parts) + 1
        res = self._client.upload_part(
            Body=chunk,
            Bucket=self.bucket_name,
            Key=self._key,
            PartNumber=part_number,
            UploadId=self._multipart["UploadId"],
        )
        etag = res["ResponseMetadata"]["HTTPHeaders"]["etag"]
        self._parts.append((part_number, etag))

    def _abort(self):
        if not self._multipart:
            return
        logging.warning(f"Aborting upload for {self._key}", user="s3")
        self._client.abort_multipart_upload(
            Bucket=self.bucket_name,
            Key=self._key,
            UploadId=self._multipart["UploadId"],
        )

    def _complete(self):
        if not self._multipart:
            raise Exception("Multipart upload not started")

        logging.debug(f"Completing upload for {self._key}", user="s3")
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

    async def init_file_upload(self, file_path: str):
        await run_in_threadpool(self._init_file_upload, file_path)

    async def push_chunk(self, chunk: bytes):
        await run_in_threadpool(self._push_chunk, chunk)

    async def abort(self):
        await run_in_threadpool(self._abort)

    async def complete(self):
        await run_in_threadpool(self._complete)

    def __del__(self):
        self._abort()


async def handle_s3_upload(
    storage: "ProjectStorage",
    request: Request,
    path: str,
) -> int:
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
    return i


# S3 file management


async def delete_s3_file(storage: "ProjectStorage", key: str):
    bucket_name = storage.bucket_name
    assert bucket_name
    logging.debug(f"Deleting {key} from {bucket_name}", user="s3")
    client = await get_s3_client(storage)
    client.delete_object(Bucket=bucket_name, Key=key)
