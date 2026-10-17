# store_s3.py: the object store on any S3 API: SeaweedFS locally, AWS S3 in production.
# Used by: tests/test_objects.py, orchestrate.py from step 6. Uses: nothing local.
# Holds raw signal bodies (S1 writes, S2 reads). Documents, evidence, traces and replays come later.
import os
from collections.abc import Iterator, MutableMapping

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

# Config
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "finebrain")  # local SeaweedFS accepts any key
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "finebrain-dev-only")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")
S3_BUCKET = os.environ.get("S3_BUCKET", "brain")
FAST_FAIL = Config(connect_timeout=2, read_timeout=5, retries={"max_attempts": 1})


def connect():
    """An S3 client pointed at the configured endpoint."""
    return boto3.client(
        "s3", endpoint_url=S3_ENDPOINT, region_name=S3_REGION, config=FAST_FAIL,
        aws_access_key_id=S3_ACCESS_KEY, aws_secret_access_key=S3_SECRET_KEY,
    )


def s3_is_up() -> bool:
    """True when the S3 endpoint answers, so tests can skip cleanly when Docker is down."""
    try:
        connect().list_buckets()
    except (BotoCoreError, ClientError):
        return False
    return True


class S3ObjectStore(MutableMapping[str, bytes]):
    """Behaves like the dict S1 and S2 use, keyed by s3://bucket/key URIs, so stages do not change."""

    def __init__(self, client, bucket: str = S3_BUCKET, prefix: str = ""):
        self.client = client
        self.bucket = bucket
        self.prefix = prefix  # tests use a fresh prefix; production uses the tenant, as in brain/{tenant}/
        self.ensure_bucket()

    def ensure_bucket(self) -> None:
        """Create the bucket once. An existing bucket is fine."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def key_for(self, uri: str) -> str:
        """s3://brain/finebase_labs/raw/x.eml becomes finebase_labs/raw/x.eml. Other buckets are refused."""
        start = f"s3://{self.bucket}/"
        if not uri.startswith(start):
            raise KeyError(f"{uri} is not in bucket {self.bucket}")
        return uri.removeprefix(start)

    def __getitem__(self, uri: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=self.key_for(uri))["Body"].read()
        except self.client.exceptions.NoSuchKey:
            raise KeyError(uri) from None

    def __setitem__(self, uri: str, body: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self.key_for(uri), Body=body)

    def __delitem__(self, uri: str) -> None:
        """Only for retention rules, like raw bodies after 90 days."""
        self.client.delete_object(Bucket=self.bucket, Key=self.key_for(uri))

    def __iter__(self) -> Iterator[str]:
        pages = self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=self.prefix)
        keys = [item["Key"] for page in pages for item in page.get("Contents", [])]
        return iter(f"s3://{self.bucket}/{key}" for key in sorted(keys))

    def __len__(self) -> int:
        return sum(1 for _ in self)
