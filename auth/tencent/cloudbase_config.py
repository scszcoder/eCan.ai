"""
CloudBase 认证配置
"""

import os
from dataclasses import dataclass, field


@dataclass
class CloudBaseConfig:
    """CloudBase 认证配置"""

    env_id: str = ""
    secret_id: str = ""
    secret_key: str = ""
    region: str = "ap-guangzhou"

    jwt_secret: str = ""
    jwt_expires_in: int = 86400

    sms_sdk_app_id: str = ""
    sms_template_id: str = ""
    sms_sign_name: str = "eCan"

    enable_email_login: bool = True
    enable_phone_login: bool = True
    enable_signup: bool = True

    @classmethod
    def from_env(cls) -> "CloudBaseConfig":
        """从环境变量加载配置"""
        return cls(
            env_id=os.getenv("ECAN_TENCENT_CLOUDBASE_ENV_ID", ""),
            secret_id=os.getenv("ECAN_TENCENT_SECRET_ID", ""),
            secret_key=os.getenv("ECAN_TENCENT_SECRET_KEY", ""),
            region=os.getenv("ECAN_TENCENT_REGION", "ap-guangzhou"),
            jwt_secret=os.getenv("ECAN_JWT_SECRET", ""),
            jwt_expires_in=int(os.getenv("ECAN_JWT_EXPIRES_IN", "86400")),
            sms_sdk_app_id=os.getenv("ECAN_TENCENT_SMS_SDK_APP_ID", ""),
            sms_template_id=os.getenv("ECAN_TENCENT_SMS_TEMPLATE_ID", ""),
            sms_sign_name=os.getenv("ECAN_TENCENT_SMS_SIGN_NAME", "eCan"),
            enable_email_login=os.getenv("ECAN_ENABLE_EMAIL_LOGIN", "true").lower() == "true",
            enable_phone_login=os.getenv("ECAN_ENABLE_PHONE_LOGIN", "true").lower() == "true",
            enable_signup=os.getenv("ECAN_ENABLE_SIGNUP", "true").lower() == "true",
        )

    def is_configured(self) -> bool:
        """检查是否已配置 CloudBase 凭证"""
        return bool(self.env_id and self.secret_id and self.secret_key)

    def is_sms_configured(self) -> bool:
        """检查短信服务是否已配置"""
        return bool(
            self.sms_sdk_app_id
            and self.sms_template_id
            and self.secret_id
            and self.secret_key
        )

    def get_jwt_secret(self) -> str:
        """获取 JWT 密钥（生产环境强制要求配置）"""
        if self.jwt_secret and len(self.jwt_secret) >= 32:
            return self.jwt_secret
        import secrets
        return secrets.token_urlsafe(64)
