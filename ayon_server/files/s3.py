import boto3
from fastapi import Request
from nxtools import logging
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool


class S3Config(BaseModel):
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    session_token: str | None = None
    endpoint_url: str | None = None
    region_name: str | None = None


def _get_s3_client(s3_config: S3Config):
    cfg = s3_config.dict(exclude_none=True)
    return boto3.client("s3", **cfg)


async def get_s3_client(s3_config: S3Config):
    return await run_in_threadpool(_get_s3_client, s3_config)


def _get_signed_url(
    s3_config: S3Config, bucket_name: str, key: str, ttl: int = 3600
) -> str:
    client = _get_s3_client(s3_config)
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name, "Key": key},
        ExpiresIn=ttl,
    )


async def get_signed_url(
    s3_config: S3Config, bucket_name: str, key: str, ttl: int = 3600
) -> str:
    return await run_in_threadpool(_get_signed_url, s3_config, bucket_name, key, ttl)


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
    request: Request,
    s3_config: S3Config,
    bucket_name: str,
    path: str,
) -> int:
    client = await get_s3_client(s3_config)

    uploader = S3Uploader(client, bucket_name)

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


async def delete_s3_file(s3_config: S3Config, bucket_name: str, key: str):
    logging.debug(f"Deleting {key} from {bucket_name}", user="s3")
    client = await get_s3_client(s3_config)
    client.delete_object(Bucket=bucket_name, Key=key)
