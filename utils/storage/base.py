"""
Storage Provider Abstraction Layer
统一存储抽象：自动根据 ECAN_APP_ID 选择腾讯云 COS 或 AWS S3
"""
from abc import ABC, abstractmethod


class StorageProvider(ABC):
    """存储提供者抽象基类"""

    @abstractmethod
    def upload_file(self, local_path: str, remote_key: str) -> str:
        """上传文件，返回公开访问 URL"""
        pass

    @abstractmethod
    def download_file(self, remote_key: str, local_path: str) -> bool:
        """下载文件"""
        pass

    @abstractmethod
    def delete_file(self, remote_key: str) -> bool:
        """删除文件"""
        pass

    @abstractmethod
    def generate_presigned_url(self, remote_key: str, expires_in: int = 3600) -> str:
        """生成预签名 URL"""
        pass

    @abstractmethod
    def file_exists(self, remote_key: str) -> bool:
        """检查文件是否存在"""
        pass
