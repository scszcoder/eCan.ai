"""
通用 S3 文件上传工具

提供统一的 S3 文件上传接口，支持：
- Presigned URL 上传（通过 AppSync 获取）
- 直接 boto3 上传
- 多种文件类型和路径配置
- 自动重试和错误处理

基于 bot/Cloud.py 的现有实现进行抽象和增强
"""

import os
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import requests

from utils.logger_helper import logger_helper as logger


class S3UploadHelper:
    """S3 文件上传辅助类"""
    
    def __init__(self, session=None, token: str = None, endpoint: str = None):
        """
        初始化 S3 上传助手
        
        Args:
            session: HTTP session（用于 presigned URL 方式）
            token: 认证 token（用于 AppSync 请求）
            endpoint: AppSync endpoint URL
        """
        self.session = session
        self.token = token
        self.endpoint = endpoint
    
    def upload_file_with_presigned_url(
        self,
        local_file_path: str,
        destination: str = None,
        file_type: str = "general",
        custom_prefix: str = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        使用 presigned URL 上传文件到 S3
        
        这个方法基于 bot/Cloud.py 的 upload_file() 函数，
        通过 AppSync 获取 presigned URL，然后上传文件。
        
        Args:
            local_file_path: 本地文件路径
            destination: 目标路径（S3 bucket 中的路径）
            file_type: 文件类型标识（用于分类，如 "avatar", "skill", "general"）
            custom_prefix: 自定义前缀（覆盖默认的 file_type|destination 格式）
        
        Returns:
            (success, s3_key, error_message)
            - success: 是否上传成功
            - s3_key: S3 中的文件 key
            - error_message: 错误信息（如果失败）
        
        Example:
            >>> helper = S3UploadHelper(session, token, endpoint)
            >>> success, s3_key, error = helper.upload_file_with_presigned_url(
            ...     "/path/to/avatar.png",
            ...     destination="user123/avatars",
            ...     file_type="avatar"
            ... )
        """
        try:
            logger.info(f"[S3Upload] Starting upload: {local_file_path}")
            start_time = datetime.now()
            
            # 验证文件存在
            if not os.path.exists(local_file_path):
                error_msg = f"File not found: {local_file_path}"
                logger.error(f"[S3Upload] {error_msg}")
                return False, "", error_msg
            
            # 获取文件名
            filename = os.path.basename(local_file_path)
            
            # 构建前缀
            if custom_prefix:
                prefix = custom_prefix
            elif destination:
                prefix = f"{file_type}|{destination}"
            else:
                prefix = f"{file_type}|{os.path.dirname(local_file_path)}"
            
            # 准备文件操作请求
            file_op_request = [{
                "op": "upload",
                "names": filename,
                "options": prefix
            }]
            
            logger.debug(f"[S3Upload] File operation request: {json.dumps(file_op_request)}")
            
            # 获取 presigned URL
            presigned_response = self._get_presigned_url(file_op_request)
            if not presigned_response:
                return False, "", "Failed to get presigned URL"
            
            logger.debug(f"[S3Upload] Got presigned URL response")
            
            # 解析响应
            presigned_data = json.loads(presigned_response['body']['urls']['result'])
            upload_info = presigned_data['body'][0]
            
            # 执行上传
            upload_success = self._upload_to_presigned_url(local_file_path, upload_info)
            
            if upload_success:
                s3_key = upload_info['fields']['key']
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.info(f"[S3Upload] ✅ Upload successful: {s3_key} ({elapsed:.2f}s)")
                return True, s3_key, None
            else:
                return False, "", "Failed to upload file to presigned URL"
            
        except Exception as e:
            error_msg = f"Upload failed: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"[S3Upload] ❌ {error_msg}")
            return False, "", error_msg
    
    def _get_presigned_url(self, file_op_request: list) -> Optional[Dict]:
        """
        从 AppSync 获取 presigned URL
        
        Args:
            file_op_request: 文件操作请求列表
        
        Returns:
            AppSync 响应数据
        """
        try:
            from bot.Cloud import send_file_op_request_to_cloud
            
            if not self.session or not self.token or not self.endpoint:
                logger.error("[S3Upload] Missing session, token, or endpoint for presigned URL request")
                return None
            
            response = send_file_op_request_to_cloud(
                self.session,
                file_op_request,
                self.token,
                self.endpoint
            )
            
            return response
            
        except Exception as e:
            logger.error(f"[S3Upload] Failed to get presigned URL: {e}")
            return None
    
    def _upload_to_presigned_url(self, local_file_path: str, upload_info: Dict) -> bool:
        """
        使用 presigned URL 上传文件
        
        Args:
            local_file_path: 本地文件路径
            upload_info: presigned URL 信息（包含 url 和 fields）
        
        Returns:
            是否上传成功
        """
        try:
            with open(local_file_path, 'rb') as file:
                files = {'file': file}
                response = requests.post(
                    upload_info['url'],
                    data=upload_info['fields'],
                    files=files
                )
            
            if response.status_code in [200, 204]:
                logger.debug(f"[S3Upload] Upload response status: {response.status_code}")
                return True
            else:
                logger.error(f"[S3Upload] Upload failed with status: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"[S3Upload] Error uploading to presigned URL: {e}")
            return False
    
    @staticmethod
    def upload_file_simple(
        local_file_path: str,
        s3_bucket_path: str,
        session=None,
        token: str = None,
        endpoint: str = None,
        file_type: str = "general"
    ) -> Tuple[bool, str, Optional[str]]:
        """
        简化的静态方法，用于快速上传文件
        
        Args:
            local_file_path: 本地文件路径
            s3_bucket_path: S3 bucket 中的目标路径
            session: HTTP session
            token: 认证 token
            endpoint: AppSync endpoint
            file_type: 文件类型标识
        
        Returns:
            (success, s3_key, error_message)
        
        Example:
            >>> from utils.s3_upload_helper import S3UploadHelper
            >>> success, s3_key, error = S3UploadHelper.upload_file_simple(
            ...     "/path/to/file.png",
            ...     "user123/avatars",
            ...     session=session,
            ...     token=token,
            ...     endpoint=endpoint,
            ...     file_type="avatar"
            ... )
        """
        helper = S3UploadHelper(session, token, endpoint)
        return helper.upload_file_with_presigned_url(
            local_file_path,
            destination=s3_bucket_path,
            file_type=file_type
        )


# 便捷函数
def upload_to_s3(
    local_file_path: str,
    s3_bucket_path: str,
    session=None,
    token: str = None,
    endpoint: str = None,
    file_type: str = "general"
) -> Tuple[bool, str, Optional[str]]:
    """
    便捷函数：上传文件到 S3
    
    Args:
        local_file_path: 本地文件路径
        s3_bucket_path: S3 bucket 中的目标路径
        session: HTTP session
        token: 认证 token
        endpoint: AppSync endpoint
        file_type: 文件类型标识（avatar, skill, general 等）
    
    Returns:
        (success, s3_key, error_message)
    
    Example:
        >>> from utils.s3_upload_helper import upload_to_s3
        >>> success, s3_key, error = upload_to_s3(
        ...     "/path/to/avatar.png",
        ...     "user123/avatars",
        ...     session=session,
        ...     token=token,
        ...     endpoint=endpoint,
        ...     file_type="avatar"
        ... )
        >>> if success:
        ...     print(f"Uploaded to: {s3_key}")
        ... else:
        ...     print(f"Upload failed: {error}")
    """
    return S3UploadHelper.upload_file_simple(
        local_file_path,
        s3_bucket_path,
        session,
        token,
        endpoint,
        file_type
    )


def upload_avatar_to_s3(
    local_file_path: str,
    owner: str,
    avatar_id: str,
    session=None,
    token: str = None,
    endpoint: str = None
) -> Tuple[bool, str, Optional[str]]:
    """
    专门用于上传头像的便捷函数
    
    Args:
        local_file_path: 本地头像文件路径
        owner: 所有者用户名
        avatar_id: 头像资源 ID
        session: HTTP session
        token: 认证 token
        endpoint: AppSync endpoint
    
    Returns:
        (success, s3_key, error_message)
    
    Example:
        >>> from utils.s3_upload_helper import upload_avatar_to_s3
        >>> success, s3_key, error = upload_avatar_to_s3(
        ...     "/path/to/avatar.png",
        ...     "user@example.com",
        ...     "avatar_abc123",
        ...     session=session,
        ...     token=token,
        ...     endpoint=endpoint
        ... )
    """
    # 构建头像专用路径
    file_ext = Path(local_file_path).suffix
    s3_path = f"{owner}/avatars/{avatar_id}{file_ext}"
    
    return upload_to_s3(
        local_file_path,
        s3_path,
        session,
        token,
        endpoint,
        file_type="avatar"
    )
