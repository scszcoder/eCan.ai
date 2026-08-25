"""Friendly mapping for cloud LLM-proxy error codes.

The CN llm-proxy gates usage on account registration/balance and answers
``403 {"error": {"code": "user_not_registered", ...}}``. Raw, that
surfaces in chat/skill logs as an opaque LLM failure; mapped, the user
learns what to actually do (activate the account or configure their own
API key).
"""

USER_NOT_REGISTERED_CODE = "user_not_registered"

USER_NOT_REGISTERED_FRIENDLY = (
    "云端 AI 服务未开通：您的账户尚未注册云端 LLM 服务。"
    "请在应用内完成账户注册/充值后重试，"
    "或在 设置 > LLM 管理 中配置您自己的 API Key。 "
    "(Cloud AI service not activated: your account is not registered with "
    "the cloud LLM proxy. Please register / top up your account in the "
    "app, or configure your own API key in Settings > LLM Management.)"
)


def friendly_proxy_error_message(error_text) -> str | None:
    """The friendly message when *error_text* carries a known proxy error
    code; None otherwise (caller keeps the original error)."""
    if error_text and USER_NOT_REGISTERED_CODE in str(error_text):
        return USER_NOT_REGISTERED_FRIENDLY
    return None


def translate_proxy_exception(exc: Exception):
    """A friendlier replacement exception for known proxy errors, or None.

    Returns ``PermissionError`` with the actionable bilingual message so
    downstream error surfaces (chat window, skill-editor log, GUI toasts)
    show guidance instead of the raw proxy JSON.
    """
    friendly = friendly_proxy_error_message(exc)
    if friendly is not None:
        return PermissionError(friendly)
    return None
