"""
腾讯云短信服务
发送手机验证码
"""

import hashlib
import hmac
import json
import time
import secrets
from typing import Optional
from dataclasses import dataclass

import requests

from auth.tencent.cloudbase_config import CloudBaseConfig
from utils.logger_helper import logger_helper as logger


@dataclass
class SMSResult:
    success: bool
    code: Optional[str] = None
    error: Optional[str] = None
    request_id: Optional[str] = None


class TencentSMSService:
    """
    腾讯云短信服务

    用于发送手机验证码
    """

    API_URL = "https://sms.tencentcloudapi.com"
    API_VERSION = "2021-01-11"

    def __init__(self, config: Optional[CloudBaseConfig] = None):
        self.config = config or CloudBaseConfig.from_env()

    def _sign(self, params: dict) -> str:
        """构造 TC3-HMAC-SHA256 签名"""
        service = "sms"
        timestamp = int(time.time())
        date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))

        # 1. 拼接规范请求串
        http_request_method = "POST"
        canonical_uri = "/"
        canonical_querystring = ""
        ct = "application/json; charset=utf-8"
        payload = json.dumps(params)
        canonical_headers = f"content-type:{ct}\nhost:sms.tencentcloudapi.com\n"
        signed_headers = "content-type;host"
        canonical_request = (
            f"{http_request_method}\n"
            f"{canonical_uri}\n"
            f"{canonical_querystring}\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
        )

        # 2. 拼接待签名字符串
        credential_scope = f"{date}/{service}/tc3_request"
        string_to_sign = (
            f"TC3-HMAC-SHA256\n"
            f"{timestamp}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )

        # 3. 计算签名
        secret_date = hmac.new(
            f"TC3{self.config.secret_key}".encode("utf-8"),
            date.encode("utf-8"),
            hashlib.sha256
        ).digest()
        secret_service = hmac.new(
            secret_date, service.encode("utf-8"), hashlib.sha256
        ).digest()
        signature = hmac.new(
            secret_service,
            string_to_sign.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return signature, timestamp, date

    def _build_auth_header(self, signature: str, timestamp: int, date: str) -> str:
        """构造 Authorization 请求头"""
        return (
            f"TC3-HMAC-SHA256 "
            f"Credential={self.config.secret_id}/{date}/sms/tc3_request, "
            f"SignedHeaders=content-type;host, "
            f"Signature={signature}"
        )

    def send_verification_code(self, phone: str, code: str,
                               template_id: Optional[str] = None,
                               sign_name: Optional[str] = None) -> SMSResult:
        """
        发送验证码短信

        Args:
            phone: 手机号（11 位）
            code: 验证码
            template_id: 模板 ID（可选，默认使用配置）
            sign_name: 短信签名（可选）

        Returns:
            SMSResult
        """
        if not self.config.is_sms_configured():
            return SMSResult(success=False, error="SMS not configured")

        template_id = template_id or self.config.sms_template_id
        sign_name = sign_name or self.config.sms_sign_name

        if not template_id or not sign_name:
            return SMSResult(success=False, error="SMS template or sign not configured")

        # 中国大陆手机号格式：+86xxxxxxxxxxx
        phone_number = f"+86{phone}"

        params = {
            "PhoneNumberSet": [phone_number],
            "SmsSdkAppId": self.config.sms_sdk_app_id,
            "SignName": sign_name,
            "TemplateId": template_id,
            "TemplateParamSet": [code, "5"],  # {1}=验证码 {2}=有效分钟数
        }

        try:
            signature, timestamp, date = self._sign(params)
            auth_header = self._build_auth_header(signature, timestamp, date)

            headers = {
                "Authorization": auth_header,
                "Content-Type": "application/json; charset=utf-8",
                "Host": "sms.tencentcloudapi.com",
                "X-TC-Action": "SendSms",
                "X-TC-Version": self.API_VERSION,
                "X-TC-Timestamp": str(timestamp),
            }

            response = requests.post(
                self.API_URL,
                headers=headers,
                json=params,
                timeout=30,
            )

            result = response.json()

            if "Response" in result:
                resp = result["Response"]
                if resp.get("Error"):
                    error_msg = resp["Error"].get("Message", "Unknown error")
                    logger.error(f"[TencentSMS] Send failed: {error_msg}")
                    return SMSResult(success=False, error=error_msg)

                send_status_set = resp.get("SendStatusSet", [])
                if send_status_set:
                    status = send_status_set[0]
                    if status.get("Code") == "Ok":
                        logger.info(f"[TencentSMS] Sent code to {phone[:3]}****{phone[-2:]}")
                        return SMSResult(
                            success=True,
                            request_id=resp.get("RequestId"),
                        )
                    else:
                        error_msg = status.get("Message", "Send failed")
                        logger.error(f"[TencentSMS] Send failed: {error_msg}")
                        return SMSResult(success=False, error=error_msg)

            return SMSResult(success=False, error="Invalid response")

        except Exception as e:
            logger.error(f"[TencentSMS] Exception: {e}")
            return SMSResult(success=False, error=str(e))


_sms_service_instance = None


def get_sms_service() -> TencentSMSService:
    """获取短信服务单例"""
    global _sms_service_instance
    if _sms_service_instance is None:
        _sms_service_instance = TencentSMSService()
    return _sms_service_instance
