"""
腾讯云 COS 存储提供者 - CN app 专用
"""
import os
from typing import Optional

from utils.storage import StorageProvider


class TencentCOSProvider(StorageProvider):
    """
    腾讯云 COS 存储实现
    需要环境变量：ECAN_TENCENT_SECRET_ID, ECAN_TENCENT_SECRET_KEY
    """

    def __init__(self, config):
        self.config = config
        self.region = config._endpoints.get('storage_region', 'ap-beijing')
        self.bucket = config._endpoints.get('storage_bucket', 'ecan-cn-files')
        self.secret_id = os.environ.get('ECAN_TENCENT_SECRET_ID', '')
        self.secret_key = os.environ.get('ECAN_TENCENT_SECRET_KEY', '')
        self.cdn_domain = config._endpoints.get('cdn', '')
        self._client = None

    def _get_client(self):
        """延迟初始化 COS 客户端"""
        if self._client is None:
            try:
                from qcloud_cos import CosConfig, CosS3Client
                region_map = {
                    'ap-beijing': 'ap-beijing-1',
                    'ap-shanghai': 'ap-shanghai',
                    'ap-guangzhou': 'ap-guangzhou',
                }
                cos_region = region_map.get(self.region, self.region)
                config = CosConfig(
                    Region=cos_region,
                    SecretId=self.secret_id,
                    SecretKey=self.secret_key,
                )
                self._client = CosS3Client(config)
            except ImportError:
                raise ImportError("tencentyun-cos-python-v5 is required for CN storage. Install with: pip install cos-python-sdk-v5")
        return self._client

    def upload_file(self, local_path: str, remote_key: str) -> str:
        client = self._get_client()
        client.upload_file(
            Bucket=self.bucket,
            LocalFilePath=local_path,
            Key=remote_key,
        )
        if self.cdn_domain:
            return f"{self.cdn_domain}/{remote_key}"
        return f"https://{self.bucket}.cos.{self.region}.myqcloud.com/{remote_key}"

    def download_file(self, remote_key: str, local_path: str) -> bool:
        client = self._get_client()
        try:
            client.download_file(Bucket=self.bucket, Key=remote_key, DestFilePath=local_path)
            return True
        except Exception:
            return False

    def delete_file(self, remote_key: str) -> bool:
        client = self._get_client()
        try:
            client.delete_object(Bucket=self.bucket, Key=remote_key)
            return True
        except Exception:
            return False

    def generate_presigned_url(self, remote_key: str, expires_in: int = 3600) -> str:
        client = self._get_client()
        return client.get_presigned_download_url(Bucket=self.bucket, Key=remote_key, Expired=expires_in)

    def file_exists(self, remote_key: str) -> bool:
        client = self._get_client()
        try:
            client.head_object(Bucket=self.bucket, Key=remote_key)
            return True
        except Exception:
            return False
