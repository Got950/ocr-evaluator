from __future__ import annotations

import uuid
from typing import Optional

import aioboto3
import boto3

from app.config import get_settings


class StorageService:
    def __init__(
        self,
        bucket: str,
        endpoint_url: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        region: str = "us-east-1",
    ) -> None:
        self.bucket = bucket
        self.endpoint_url = endpoint_url or None
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.region = region
        self._aio_session = aioboto3.Session(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region,
        )

    @classmethod
    def from_settings(cls) -> "StorageService":
        settings = get_settings()
        return cls(
            bucket=settings.s3_bucket or "ocr-evaluator-uploads",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region=settings.s3_region,
        )

    def _client_kwargs(self) -> dict:
        kw: dict = {"region_name": self.region}
        if self.endpoint_url:
            kw["endpoint_url"] = self.endpoint_url
        return kw

    async def upload_file(self, file_bytes: bytes, filename: str, content_type: str) -> str:
        key = f"uploads/{uuid.uuid4()}/{filename}"
        async with self._aio_session.client("s3", **self._client_kwargs()) as s3:
            await s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=file_bytes,
                ContentType=content_type,
            )
        return key

    async def get_file_url(self, key: str) -> str:
        async with self._aio_session.client("s3", **self._client_kwargs()) as s3:
            url = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=3600,
            )
        return str(url)

    async def download_file(self, key: str) -> bytes:
        async with self._aio_session.client("s3", **self._client_kwargs()) as s3:
            resp = await s3.get_object(Bucket=self.bucket, Key=key)
            return await resp["Body"].read()

    def download_file_sync(self, key: str) -> bytes:
        kw = self._client_kwargs()
        session = boto3.Session(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region,
        )
        s3 = session.client("s3", **kw)
        resp = s3.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()
