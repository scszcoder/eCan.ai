"""
CloudBase Authentication Configuration

设计原则（公开 vs 私密）：

公开字段（写入 apps/cn/config/auth_config.yml 随 App 打包，无安全风险）：
  - CLOUDBASE.ENV_ID / REGION  → CloudBase 环境标识
  - SMS.SDK_APP_ID / TEMPLATE_ID / SIGN_NAME / REGION  → 短信公开字段
  - WECHAT.APP_ID / CALLBACK_URL / SCOPE  → 微信客户端公开信息
  - EMAIL.PROVIDER / FROM_ADDRESS / REGION
  - LOGIN.ENABLE_*  → 登录方式开关

私密字段（永远不应该出现在 yml/仓库/打包产物中，只能由 CI/CD 运行时注入）：
  - CLOUDBASE.SECRET_ID / SECRET_KEY  → 腾讯云 API 长期密钥
  - WECHAT.APP_SECRET  → 微信公众号密钥

读取顺序（私密字段）：
  1. ECAN_TENCENT_SECRET_ID / ECAN_TENCENT_SECRET_KEY（环境变量，构建时由 CI 注入）
  2. 失败则视为未配置（启动后端服务会立即报错）

读取顺序（公开字段）：
  1. auth_config.yml（apps/cn/config/auth_config.yml）
  2. 环境变量作为 override
"""

from dataclasses import dataclass


@dataclass
class CloudBaseConfig:
    """CloudBase 认证配置"""

    # ---------- 公开字段（来自 auth_config.yml） ----------
    env_id: str = ""
    region: str = "ap-guangzhou"

    sms_sdk_app_id: str = ""
    sms_template_id: str = ""
    sms_sign_name: str = "eCan"
    sms_region: str = "ap-guangzhou"

    wechat_app_id: str = ""
    # 微信登录类型：
    #   - "open_platform" 开放平台网站应用（PC 浏览器扫码登录，scope=snsapi_login）
    #   - "mp_official"   公众号 H5 网页授权（微信内打开，scope=snsapi_userinfo/snsapi_base）
    wechat_login_type: str = "open_platform"
    wechat_scope: str = "snsapi_userinfo"

    email_provider: str = "tcb_email"
    email_from_address: str = "noreply@fastprecisiontech.com"
    email_region: str = "ap-guangzhou"

    enable_email_login: bool = True
    enable_phone_login: bool = True
    enable_wechat_login: bool = True
    enable_signup: bool = True
    enable_anonymous_login: bool = False

    # ---------- 私密字段（仅来自环境变量） ----------
    secret_id: str = ""
    secret_key: str = ""

    @classmethod
    def from_auth_config(cls) -> "CloudBaseConfig":
        """从 AuthConfig（apps/cn/config/auth_config.yml）加载配置。

        私密字段（SECRET_KEY / SECRET_ID）只从
        环境变量读取。如果这些环境变量不存在，对应字段保持为空字符串，
        调用方应通过 is_configured() / is_sms_configured() 判断。

        注意：WECHAT.APP_SECRET 仅需在 CloudBase 控制台配置，不需要环境变量。
        """
        import os
        from auth.auth_config import AuthConfig

        # Resolve each section independently. ``AuthConfig.WECHAT`` /
        # ``AuthConfig.EMAIL`` raise ``AttributeError`` when the loaded
        # ``auth_config.yml`` doesn't declare that section (e.g. CN config
        # has no WECHAT section). We must not let one missing section
        # wipe out the others — otherwise CLOUDBASE.ENV_ID silently
        # disappears even though it was loaded correctly.
        def _ns(name: str):
            try:
                return getattr(AuthConfig, name)
            except AttributeError:
                return None

        cfg = _ns("CLOUDBASE")
        sms_cfg = _ns("SMS")
        wechat_cfg = _ns("WECHAT")
        email_cfg = _ns("EMAIL")

        def _get(namespace, key: str, default: str = "") -> str:
            if namespace is None:
                return default
            try:
                value = getattr(namespace, key, default)
            except Exception:
                return default
            # ConfigNamespace 对未声明的 key 返回 _MissingAttr()（不是 None），
            # 这两种情况都应回退到 default。
            if value is None or (hasattr(value, '__class__') and value.__class__.__name__ == '_MissingAttr'):
                return default
            return str(value)

        return cls(
            # 公开字段（来自 yml）
            env_id=_get(cfg, "ENV_ID"),
            region=_get(cfg, "REGION", "ap-guangzhou"),
            sms_sdk_app_id=_get(sms_cfg, "sdk_app_id"),
            sms_template_id=_get(sms_cfg, "template_id"),
            sms_sign_name=_get(sms_cfg, "sign_name", "eCan"),
            sms_region=_get(sms_cfg, "region", "ap-guangzhou"),
            wechat_app_id=_get(wechat_cfg, "APP_ID"),
            wechat_login_type=_get(wechat_cfg, "LOGIN_TYPE", "open_platform"),
            wechat_scope=_get(wechat_cfg, "SCOPE", "snsapi_userinfo"),
            email_provider=_get(email_cfg, "provider", "tcb_email"),
            email_from_address=_get(email_cfg, "from_address", "noreply@fastprecisiontech.com"),
            email_region=_get(email_cfg, "region", "ap-guangzhou"),
            enable_email_login=_get(cfg, "ENABLE_EMAIL_LOGIN", "true").lower() == "true",
            enable_phone_login=_get(cfg, "ENABLE_PHONE_LOGIN", "true").lower() == "true",
            enable_wechat_login=_get(cfg, "ENABLE_WECHAT_LOGIN", "true").lower() == "true",
            enable_signup=_get(cfg, "ENABLE_SIGNUP", "true").lower() == "true",
            enable_anonymous_login=_get(cfg, "ENABLE_ANONYMOUS_LOGIN", "false").lower() == "true",

            # 私密字段（仅来自环境变量）
            secret_id=os.getenv("ECAN_TENCENT_SECRET_ID", ""),
            secret_key=os.getenv("ECAN_TENCENT_SECRET_KEY", ""),
        )

    # 保留 from_env() 作为旧入口（向后兼容），但内部委托给 from_auth_config
    from_env = from_auth_config

    def is_configured(self) -> bool:
        """检查是否已配置 CloudBase 公开配置（web v3 不需要 SK 签名,只要 env_id 即可）

        SK 只在历史 admin SDK 调用场景必需。Web v3 客户端不需要。
        """
        return bool(self.env_id)

    def has_admin_credentials(self) -> bool:
        """是否同时配置了 SK（用于服务端 SDK / admin 类操作）

        普通客户端登录不需要。
        """
        return bool(self.env_id and self.secret_id and self.secret_key)

    def is_sms_configured(self) -> bool:
        """检查短信服务是否已配置"""
        return bool(
            self.sms_sdk_app_id
            and self.sms_template_id
            and self.secret_id
            and self.secret_key
        )

    def is_wechat_configured(self) -> bool:
        """检查微信登录是否已配置（APP_ID 来自 yml，APP_SECRET 不再需要）"""
        return bool(self.wechat_app_id)
