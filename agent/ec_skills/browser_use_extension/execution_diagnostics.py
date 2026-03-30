from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Translation catalogue
# Each entry: { "message": ..., "suggestion": ... } in zh and en.
# {{timeout}} is a placeholder substituted at format time.
# ---------------------------------------------------------------------------
_TRANSLATIONS: dict[str, dict[str, dict[str, str]]] = {
    "login_required": {
        "zh": {
            "message": "平台可能需要先登录，当前步骤在未登录状态下执行失败。",
            "suggestion": "请先人工登录并保持会话有效，然后重试。",
        },
        "en": {
            "message": "The platform may require login. The current step failed in an unauthenticated state.",
            "suggestion": "Please log in manually and keep the session active, then retry.",
        },
    },
    "risk_control_blocked": {
        "zh": {
            "message": "平台可能触发了风控/反爬拦截，自动化步骤无法继续。",
            "suggestion": "建议降低操作频率，人工过验证码后再继续。",
        },
        "en": {
            "message": "The platform may have triggered risk control / anti-bot protection. Automation cannot continue.",
            "suggestion": "Reduce operation frequency, complete the CAPTCHA manually, then retry.",
        },
    },
    "image_download_failed": {
        "zh": {
            "message": "图片下载未成功，可能是链接失效、鉴权限制或防盗链。",
            "suggestion": "请检查图片 URL 可访问性，必要时先登录平台或改用可直链下载源。",
        },
        "en": {
            "message": "Image download failed. The URL may be expired, require authentication, or be hotlink-protected.",
            "suggestion": "Check image URL accessibility. Log in to the platform first if needed, or use a direct-link source.",
        },
    },
    "wait_timeout_suspected": {
        "zh": {
            "message": "检测到超时相关错误，可能存在等待时长不足或页面加载未完成。",
            "suggestion": "请增加等待时间或加入页面就绪/元素出现判断。{{timeout_hint}}{{short_wait_hint}}",
        },
        "en": {
            "message": "Timeout-related error detected. The wait duration may be too short or the page load incomplete.",
            "suggestion": "Increase wait time or add page-ready / element-appear checks. {{timeout_hint}}{{short_wait_hint}}",
        },
    },
}

# Codes that should hard-block further automation when detected.
# Keep this list strictly generic and high-confidence to avoid scenario coupling.
BLOCKING_CODES: frozenset[str] = frozenset(
    {"login_required", "risk_control_blocked"}
)


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _collect_texts(
    action_results: list[dict[str, Any]] | None,
    errors: list[str] | None,
    browser: dict[str, Any] | None,
) -> str:
    rows: list[str] = []
    for err in errors or []:
        if err:
            rows.append(_to_text(err))
    for item in action_results or []:
        if not isinstance(item, dict):
            continue
        rows.append(_to_text(item.get("error")))
        rows.append(_to_text(item.get("extracted_content")))
    if isinstance(browser, dict):
        rows.append(_to_text(browser.get("url")))
        rows.append(_to_text(browser.get("title")))
        rows.append(_to_text(browser.get("dom_text")))
    return "\n".join(r for r in rows if r).lower()


def build_execution_diagnostics(
    *,
    actions: list[dict[str, Any]] | None = None,
    action_results: list[dict[str, Any]] | None = None,
    errors: list[str] | None = None,
    browser: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> list[dict[str, Any]]:
    """
    Analyse a browser-automation step and return structured diagnostic entries.

    Each entry:
        {
            "code": str,          # stable identifier, used as i18n key on the frontend
            "severity": str,      # "error" | "warning" | "info"
            "params": dict,       # template variables for the suggestion string
        }
    """
    diagnostics: list[dict[str, Any]] = []
    safe_action_results: list[dict[str, Any]] = action_results if isinstance(action_results, list) else []

    action_names: list[str] = []
    for action in actions or []:
        if isinstance(action, dict) and action:
            action_names.append(str(next(iter(action.keys()))))

    text_blob = _collect_texts(safe_action_results, errors, browser)

    def add_diag(code: str, severity: str, params: dict[str, Any] | None = None) -> None:
        diagnostics.append({"code": code, "severity": severity, "params": params or {}})

    # --- Login required -------------------------------------------------------
    if re.search(r"(login|sign in|unauthorized|session expired|请先登录|登录|未登录)", text_blob):
        add_diag("login_required", "error")

    # --- Risk / captcha block -------------------------------------------------
    if re.search(
        r"(captcha|verify you are human|access denied|too many requests|429|forbidden|风控|验证码|人机验证|封禁|拦截)",
        text_blob,
    ):
        add_diag("risk_control_blocked", "error")

    # --- Image download failure -----------------------------------------------
    if re.search(r"(download_file failed|download failed|图片下载失败|image download failed)", text_blob):
        # Keep it as warning: download capability and network policy vary by node/tool.
        add_diag("image_download_failed", "warning")

    # --- Timeout suspected ----------------------------------------------------
    has_timeout_error = bool(
        re.search(r"(timed out|timeout|超时|page readiness timeout|navigation timeout)", text_blob)
    )
    if has_timeout_error:
        has_short_wait = any(
            isinstance(action.get("wait"), dict)
            and _safe_float(action["wait"].get("seconds")) is not None
            and _safe_float(action["wait"].get("seconds")) <= 2.0  # type: ignore[operator]
            for action in (actions or [])
            if isinstance(action, dict) and "wait" in action
        )
        params: dict[str, Any] = {}
        if timeout_seconds:
            params["timeout_seconds"] = int(timeout_seconds)
        if has_short_wait:
            params["has_short_wait"] = True
        add_diag("wait_timeout_suspected", "warning", params)

    return diagnostics


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _resolve_translation(code: str, locale: str, params: dict[str, Any]) -> tuple[str, str]:
    """Return (message, suggestion) for the given code and locale."""
    lang = locale if locale in ("zh", "en") else "zh"
    entry = _TRANSLATIONS.get(code, {})
    texts = entry.get(lang) or entry.get("zh") or {"message": code, "suggestion": ""}
    msg = texts.get("message", code)
    sug = texts.get("suggestion", "")

    # Substitute template hints for wait_timeout_suspected.
    if code == "wait_timeout_suspected":
        timeout_hint = ""
        short_wait_hint = ""
        if params.get("timeout_seconds"):
            if lang == "zh":
                timeout_hint = f"当前步骤超时配置约为 {params['timeout_seconds']}s。"
            else:
                timeout_hint = f"Current node timeout is approximately {params['timeout_seconds']}s."
        if params.get("has_short_wait"):
            if lang == "zh":
                short_wait_hint = " 当前动作中存在 ≤2s 的 wait，可能偏短。"
            else:
                short_wait_hint = " A wait ≤2s was found in the actions, which may be too short."
        sug = sug.replace("{{timeout_hint}}", timeout_hint).replace("{{short_wait_hint}}", short_wait_hint).strip()

    return msg, sug


def format_diagnostics_for_user(
    diagnostics: list[dict[str, Any]] | None,
    locale: str = "zh",
) -> str:
    """
    Format diagnostics as a human-readable string for chat / skill-editor logs.

    ``locale`` should be ``"zh"`` or ``"en"``.
    """
    rows: list[str] = []
    for diag in diagnostics or []:
        if not isinstance(diag, dict):
            continue
        sev = str(diag.get("severity") or "info").upper()
        code = str(diag.get("code") or "unknown")
        params = diag.get("params") or {}
        msg, sug = _resolve_translation(code, locale, params)
        if msg:
            row = f"[{sev}] {code}: {msg}"
            if sug:
                if locale == "en":
                    row += f" Suggestion: {sug}"
                else:
                    row += f" 建议：{sug}"
            rows.append(row)
    return "\n".join(rows)


def has_blocking_diagnostic(diagnostics: list[dict[str, Any]] | None) -> bool:
    """Return True if any diagnostic code is in BLOCKING_CODES."""
    for diag in diagnostics or []:
        if not isinstance(diag, dict):
            continue
        if str(diag.get("code") or "") in BLOCKING_CODES:
            return True
    return False
