"""Friendly mapping for cloud LLM-proxy error codes.

The CN llm-proxy gates usage on account registration/balance and answers
with structured error codes:

    403 {"error": {"code": "user_not_registered", ...}}
    403 {"error": {"code": "account_inactive", ...}}
    402 {"error": {"code": "insufficient_balance", ...}}

Raw, those surface in chat/skill logs as an opaque LLM failure; mapped, the
user learns what to actually do (top up, activate the account, or configure
their own API key).

Billing blocks are NOT transient: the server caches the denial (~10s) and
the balance only moves via top-up, so callers must not retry — they should
pause the task and point the user at the Account page. ``LLMBillingError``
(a ``PermissionError`` subclass, so existing handlers keep working) carries
the machine ``code`` for that decision.
"""

USER_NOT_REGISTERED_CODE = "user_not_registered"
INSUFFICIENT_BALANCE_CODE = "insufficient_balance"
ACCOUNT_INACTIVE_CODE = "account_inactive"

USER_NOT_REGISTERED_FRIENDLY = (
    "云端 AI 服务未开通：您的账户尚未注册云端 LLM 服务。"
    "请在应用内完成账户注册/充值后重试，"
    "或在 设置 > LLM 管理 中配置您自己的 API Key。 "
    "(Cloud AI service not activated: your account is not registered with "
    "the cloud LLM proxy. Please register / top up your account in the "
    "app, or configure your own API key in Settings > LLM Management.) "
    "[code: user_not_registered]"
)

INSUFFICIENT_BALANCE_FRIENDLY = (
    "云端 AI 服务余额不足：您的账户余额已用尽，本次调用被拒绝。"
    "请在 账户 页面充值后重试；充值到账即时生效。"
    "任务已暂停，充值后会随下一条消息自动恢复。 "
    "(Cloud AI balance exhausted: this call was rejected. Please top up on "
    "the Account page — credits apply immediately. The task is paused and "
    "resumes with the next message after top-up.) "
    "[code: insufficient_balance]"
)

ACCOUNT_INACTIVE_FRIENDLY = (
    "云端 AI 账户已停用：您的账户当前处于停用状态，无法调用云端 LLM 服务。"
    "请联系客服恢复账户，或在 设置 > LLM 管理 中配置您自己的 API Key。 "
    "(Cloud AI account inactive: your account is deactivated and cannot use "
    "the cloud LLM proxy. Please contact support to reactivate, or "
    "configure your own API key in Settings > LLM Management.) "
    "[code: account_inactive]"
)

_BILLING_FRIENDLY = {
    USER_NOT_REGISTERED_CODE: USER_NOT_REGISTERED_FRIENDLY,
    INSUFFICIENT_BALANCE_CODE: INSUFFICIENT_BALANCE_FRIENDLY,
    ACCOUNT_INACTIVE_CODE: ACCOUNT_INACTIVE_FRIENDLY,
}


class LLMBillingError(PermissionError):
    """A proxy billing/registration block (402/403). Never retryable —
    pause the task and let the user top up / activate."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def billing_block_code(error_text) -> str | None:
    """The billing-block code carried in *error_text*, or None."""
    text = str(error_text or "")
    for code in _BILLING_FRIENDLY:
        if code in text:
            return code
    return None


def friendly_proxy_error_message(error_text) -> str | None:
    """The friendly message when *error_text* carries a known proxy error
    code; None otherwise (caller keeps the original error)."""
    code = billing_block_code(error_text)
    return _BILLING_FRIENDLY[code] if code else None


def translate_proxy_exception(exc: Exception):
    """A friendlier replacement exception for known proxy errors, or None.

    Returns ``LLMBillingError`` (a ``PermissionError``) with the actionable
    bilingual message so downstream error surfaces (chat window,
    skill-editor log, GUI toasts) show guidance instead of the raw proxy
    JSON — and so retry loops can recognise the block as terminal.
    """
    code = billing_block_code(exc)
    if code:
        return LLMBillingError(_BILLING_FRIENDLY[code], code)
    return None


def notify_billing_block(code: str) -> None:
    """Best-effort push of a billing block to connected frontends.

    The GUI listens for ``account.billingBlocked`` and reacts by refreshing
    the account balance (which trips the low-fund banner) and toasting a
    top-up hint. Safe no-op in cloud-worker/headless mode.
    """
    try:
        from gui.LocalServer import app_ws_manager
        app_ws_manager.broadcast_sync('account.billingBlocked', {'code': code})
    except Exception:
        pass
