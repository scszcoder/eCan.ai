"""
Storage Provider base class.

Single abstract base for both AWS S3 (intl) and Tencent COS (cn).
Concrete providers live in aws_s3.py and tencent_cos.py.

Note on bucket naming
---------------------
There are TWO completely separate buckets per app in this project.
Bucket short-names match the AWS S3 originals (the CN equivalents append
``-APPID`` because Tencent COS requires globally unique bucket names).

  1. OTA bucket
        intl (S3) :  ``ecan-releases``
        cn   (COS):  ``ecan-releases-1251680599``  (AppId-suffixed)
        Owner:   CI/CD (upload_to_s3.py / upload_to_cos.py + generate_appcast.py)
        Read by: Released desktop clients checking for updates
        Config:  ota/config/ota_config.yaml
        Reason:  versioned, immutable release artifacts + CDN-fronted appcast

  2. Runtime bucket
        intl (S3) :  ``ecan-skills``
        cn   (COS):  ``ecan-skills-1251680599``    (AppId-suffixed)
        Owner:   The running app via utils.storage.get_storage_provider()
        Read by: The running app and end users through CDN
        Config:  apps/{cn,intl}/config/cloud_endpoints.json
        Reason:  mutable user uploads, avatars, screenshots, exports

These two NEVER alias the same bucket. Mixing them up (e.g. uploading
a release artifact to the runtime bucket) is a misconfiguration that
will silently work but break update checks for users.
"""
from abc import ABC, abstractmethod


class StorageProvider(ABC):
    """Storage provider abstract base. One concrete subclass per backend."""

    @abstractmethod
    def upload_file(self, local_path: str, remote_key: str) -> str:
        """Upload ``local_path`` to ``remote_key``. Return the public URL."""
        raise NotImplementedError

    @abstractmethod
    def download_file(self, remote_key: str, local_path: str) -> bool:
        """Download ``remote_key`` to ``local_path``. Return True on success."""
        raise NotImplementedError

    @abstractmethod
    def delete_file(self, remote_key: str) -> bool:
        """Delete ``remote_key``. Return True on success."""
        raise NotImplementedError

    @abstractmethod
    def generate_presigned_url(self, remote_key: str, expires_in: int = 3600) -> str:
        """Return a short-lived presigned URL for ``remote_key``."""
        raise NotImplementedError

    @abstractmethod
    def file_exists(self, remote_key: str) -> bool:
        """Return True if ``remote_key`` exists in the bucket."""
        raise NotImplementedError
