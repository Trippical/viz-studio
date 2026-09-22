"""S3 backend via boto3. Credentials come from the environment or the pod role."""
from typing import Iterator

import boto3
from botocore.exceptions import ClientError

from .base import NotFound, ObjectInfo

CHUNK = 1024 * 1024


def _is_missing(err: ClientError) -> bool:
    return err.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound")


class S3Storage:
    def __init__(self, bucket: str, client=None):
        self.bucket = bucket
        self.client = client or boto3.client("s3")

    def list(self, prefix: str) -> list[ObjectInfo]:
        out = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                out.append(ObjectInfo(
                    key=obj["Key"],
                    size=obj["Size"],
                    etag=obj["ETag"].strip('"'),
                    last_modified=obj.get("LastModified"),
                ))
        return sorted(out, key=lambda o: o.key)

    def head(self, key: str) -> ObjectInfo:
        try:
            resp = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as err:
            if _is_missing(err):
                raise NotFound(key) from err
            raise
        return ObjectInfo(key=key, size=resp["ContentLength"], etag=resp["ETag"].strip('"'),
                          last_modified=resp.get("LastModified"))

    def get(self, key: str) -> bytes:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as err:
            if _is_missing(err):
                raise NotFound(key) from err
            raise
        return resp["Body"].read()

    def open(self, key: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        range_header = f"bytes={start}-" if end is None else f"bytes={start}-{end}"
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key, Range=range_header)
        except ClientError as err:
            if _is_missing(err):
                raise NotFound(key) from err
            raise
        yield from resp["Body"].iter_chunks(CHUNK)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def copy(self, src: str, dst: str) -> None:
        try:
            self.client.copy_object(Bucket=self.bucket, Key=dst, CopySource={"Bucket": self.bucket, "Key": src})
        except ClientError as err:
            if _is_missing(err):
                raise NotFound(src) from err
            raise
