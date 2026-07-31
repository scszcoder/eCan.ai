"""
Storage Provider Abstraction Layer.

Dispatch to AWS S3 (intl) or Tencent COS (cn) based on the active app id.
See base.py for the bucket naming convention (OTA bucket vs runtime bucket
are intentionally different).

Each backend's SDK is imported lazily inside its provider's ``_get_client()``
so the intl build never has to install cos-python-sdk-v5.
"""
import os

from utils.storage.base import StorageProvider
from utils.app_config_loader import get_config


def get_storage_provider() -> StorageProvider:
    """Return the storage provider for the currently active app."""
    config = get_config()

    if config.is_cn():
        from utils.storage.tencent_cos import TencentCOSProvider
        return TencentCOSProvider(config)

    from utils.storage.aws_s3 import AWSS3Provider
    return AWSS3Provider(config)


__all__ = ['StorageProvider', 'get_storage_provider']
