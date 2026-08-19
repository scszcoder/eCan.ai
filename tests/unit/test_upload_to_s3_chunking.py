"""Regression tests for S3 multipart transfer configuration."""

from unittest.mock import MagicMock

from boto3.s3.transfer import TransferConfig

from build_system.scripts.upload_to_s3 import S3Uploader


def test_large_upload_uses_s3_transfer_config(tmp_path):
    uploader = S3Uploader.__new__(S3Uploader)
    uploader.bucket = "ecan-releases"
    uploader.region = "us-east-1"
    uploader.uploaded_files = []

    local_path = tmp_path / "installer.exe"
    local_path.touch()
    with local_path.open("wb") as artifact:
        artifact.truncate(200 * 1024 * 1024)

    uploader.s3 = MagicMock()

    assert uploader.upload_file(local_path, "test/releases/v1.0.0/installer.exe")

    upload_kwargs = uploader.s3.upload_file.call_args.kwargs
    transfer_config = upload_kwargs["Config"]
    assert isinstance(transfer_config, TransferConfig)
    assert transfer_config.multipart_chunksize == 50 * 1024 * 1024
    assert transfer_config.max_concurrency == 10
    assert upload_kwargs["ExtraArgs"] == {
        "ContentType": "application/octet-stream",
        "CacheControl": "max-age=3600",
    }
