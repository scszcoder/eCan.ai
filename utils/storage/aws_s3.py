"""
AWS S3 存储提供者 - Intl app 专用
"""
import os
from typing import Optional

from utils.storage import StorageProvider


class AWSS3Provider(StorageProvider):
    """
    AWS S3 存储实现
    通过 boto3 / 环境变量配置
    """

    def __init__(self, config):
        self.config = config
        self.region = config._endpoints.get('storage_region', 'us-east-1')
        self.bucket = config._endpoints.get('storage_bucket', 'ecan-intl-files')
        self.cdn_domain = config._endpoints.get('cdn', '')
        self._client = None

    def _get_client(self):
        """延迟初始化 S3 客户端"""
        if self._client is None:
            import boto3
            self._client = boto3.client(
                's3',
                region_name=self.region,
                aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID', ''),
                aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY', ''),
            )
        return self._client

    def upload_file(self, local_path: str, remote_key: str) -> str:
        client = self._get_client()
        client.upload_file(local_path, self.bucket, remote_key)
        if self.cdn_domain:
            return f"{self.cdn_domain}/{remote_key}"
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{remote_key}"

    def download_file(self, remote_key: str, local_path: str) -> bool:
        client = self._get_client()
        try:
            client.download_file(self.bucket, remote_key, local_path)
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
        return client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': remote_key},
            ExpiresIn=expires_in,
        )

    def file_exists(self, remote_key: str) -> bool:
        client = self._get_client()
        try:
            client.head_object(Bucket=self.bucket, Key=remote_key)
            return True
        except Exception:
            return False
