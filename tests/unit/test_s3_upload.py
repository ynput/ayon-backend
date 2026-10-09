# ruff: noqa
import asyncio
import os
import sys
from unittest.mock import MagicMock, AsyncMock

# Add project root to sys.path

# Mock statistics and other file modules to avoid circular imports and postgres connections
mock_stats = MagicMock()
mock_stats.update_traffic_stats = AsyncMock()
sys.modules["ayon_server.helpers.statistics"] = mock_stats
sys.modules["ayon_server.files.project_file_record"] = MagicMock()
sys.modules["ayon_server.files.project_storage"] = MagicMock()

import pytest
from ayon_server.files.s3 import handle_s3_upload


class MockS3Client:
    def __init__(self):
        self.uploaded_parts = []

    def create_multipart_upload(self, **kwargs):
        return {"UploadId": "test-upload-id"}

    def upload_part(self, Body, Bucket, Key, PartNumber, UploadId):
        self.uploaded_parts.append((PartNumber, len(Body), Body))
        return {"ResponseMetadata": {"HTTPHeaders": {"etag": f"etag-{PartNumber}"}}}

    def complete_multipart_upload(self, **kwargs):
        pass


class MockStorage:
    def __init__(self, s3_client):
        self._s3_client = s3_client
        self.bucket_name = "test-bucket"


class MockRequest:
    def __init__(self, chunks):
        self.chunks = chunks

    async def stream(self):
        for chunk in self.chunks:
            yield chunk


@pytest.mark.anyio
async def test_handle_s3_upload_chunk_sizes():
    # Setup mock S3 client and storage
    mock_client = MockS3Client()
    mock_storage = MockStorage(mock_client)

    # 3 chunks of 2MB each
    chunk_size = 2 * 1024 * 1024
    chunks = [
        b"A" * chunk_size,
        b"B" * chunk_size,
        b"C" * chunk_size,
    ]
    mock_request = MockRequest(chunks)

    # Trigger upload
    uploaded_size = await handle_s3_upload(
        mock_storage,
        mock_request,
        "test-key",
    )

    # Total uploaded size should be 6MB
    assert uploaded_size == 6 * 1024 * 1024

    # We expect 2 parts:
    # 1. 5MB (Part 1)
    # 2. 1MB (Part 2)
    assert len(mock_client.uploaded_parts) == 2

    part1_num, part1_size, part1_body = mock_client.uploaded_parts[0]
    part2_num, part2_size, part2_body = mock_client.uploaded_parts[1]

    assert part1_num == 1
    assert part1_size == 5 * 1024 * 1024
    assert part1_body == (
        b"A" * chunk_size + b"B" * chunk_size + b"C" * (1 * 1024 * 1024)
    )

    assert part2_num == 2
    assert part2_size == 1 * 1024 * 1024
    assert part2_body == b"C" * (1 * 1024 * 1024)
