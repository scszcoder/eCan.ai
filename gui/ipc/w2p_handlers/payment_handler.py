"""Payment / account top-up IPC handlers.

Region-detected top-up:
  - CN  → Alipay + WeChat Pay, via the proven web payment flow opened in an
          in-app embedded webview (gui/payments/payment_dialog.py). The
          merchant secret + order creation + payment-notify all stay on the
          server (…/cn/payment-test/*); the app only opens the entry page
          and observes the server-verified success state.
  - Intl → Stripe (handled on the front-end via the existing Stripe flow;
          the front-end branches on region, so no backend call here).

These handlers require a valid session — they are deliberately NOT in the
IPC whitelist (registry.py), so token validation runs before them.

NOTE (v1 limitation, tracked in docs/OPEN_ITEMS.md): the test payment
endpoints charge a fixed amount and do NOT yet credit the account balance
(Account.fund) per user. Crediting must happen server-side in the payment
notify handler (order↔user association) before top-up truly moves the
balance. This handler returns the payment outcome so the UI can refresh
the account once that server-side crediting is in place.
"""

import json
import os
import traceback
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from utils.app_env import is_cn, get_app_id, get_payment_config
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import (
    IPCRequest,
    IPCResponse,
    create_error_response,
    create_success_response,
)
from utils.logger_helper import logger_helper as logger


@IPCHandlerRegistry.handler("payment_get_methods")
def handle_payment_get_methods(request: IPCRequest,
                               params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Return the payment methods available for this build's region.

    Front-end uses this (together with useIsCN) to render the top-up page:
    CN → alipay + wechat_pay; Intl → stripe.
    """
    try:
        if is_cn():
            cfg = get_payment_config()
            entry_url = str(cfg.get("entry_url") or "")
            methods = cfg.get("methods") or ["alipay", "wechat_pay"]
            return create_success_response(request, {
                "region": "cn",
                "methods": methods,
                "configured": bool(entry_url),
            })
        return create_success_response(request, {
            "region": "intl",
            "methods": ["stripe"],
            "configured": True,
        })
    except Exception as e:
        logger.error(f"[Payment] get_methods error: {e}")
        return create_error_response(request, "PAYMENT_CONFIG_ERROR", str(e))


@IPCHandlerRegistry.handler("payment_topup")
def handle_payment_topup(request: IPCRequest,
                         params: Optional[Dict[str, Any]]) -> IPCResponse:
    """CN top-up: open the in-app payment dialog (Alipay + WeChat Pay) and
    return the terminal payment result.

    Desktop-only (needs the Qt main loop to open the dialog). Intl top-up
    is handled entirely on the front-end via the existing Stripe flow, so
    it never calls this.
    """
    try:
        if not is_cn():
            return create_error_response(
                request, "CN_ONLY",
                "payment_topup is CN-only; Intl uses the Stripe flow on the frontend",
            )
        if os.getenv("ECAN_MODE", "desktop") == "web":
            return create_error_response(
                request, "DESKTOP_ONLY",
                "payment_topup is desktop-only (opens an in-app payment dialog)",
            )

        cfg = get_payment_config()
        entry_url = str(cfg.get("entry_url") or "").strip()
        if not entry_url:
            return create_error_response(
                request, "PAYMENT_NOT_CONFIGURED",
                "CN payment entry_url is not configured (apps/cn/config/payment_config.json)",
            )

        # Forward-compat: pass the requested amount so a future variable-amount
        # server endpoint can honor it. The current test endpoint ignores it.
        amount = (params or {}).get("amount")
        url = entry_url
        if amount is not None:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}amount={amount}"

        # Forward a coupon code so the payment page / create_payment_order can
        # apply it server-side (the server is authoritative — the client never
        # computes the discount). Empty/None is omitted.
        coupon_code = str((params or {}).get("coupon_code") or "").strip()
        if coupon_code:
            from urllib.parse import quote as _qc
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}coupon_code={_qc(coupon_code)}"

        # Payment-crediting contract (2026-09-02): the payment PHP must call
        # ecbAccountManager create_payment_order (user bearer) BEFORE showing
        # the QR — using the returned orderID as out_trade_no — so the notify
        # webhook's credit_payment can credit accounts.fund. The desktop's
        # embedded webview is an OTR profile with no site session cookie, so
        # the page cannot identify the payer unless we hand it the user's
        # bearer: append the eCan session token (HTTPS to our own site; the
        # login-callback PHP already handles this token class). Without it the
        # page charges anonymously and nothing is credited (the ¥0.01
        # order-'' incident).
        try:
            from app_context import AppContext as _AppContext
            from agent.cloud_api.cloud_api import _http_auth_header
            from urllib.parse import quote as _q
            mainwin = _AppContext.get_main_window()
            # create_payment_order currently verifies a CloudBase ACCESS token
            # (like ensure_account), so prefer the raw AccessToken when the
            # auth manager holds one (email/phone logins). Fall back to the
            # eCan session token — WeChat logins have nothing else; the server
            # must additionally accept session tokens for them (probed
            # 2026-09-01: session token -> "CloudBase access token
            # verification failed").
            token_value = ""
            try:
                am = getattr(mainwin, "auth_manager", None)
                if am is not None:
                    raw = am.get_tokens() or {}
                    token_value = str(raw.get("AccessToken")
                                      or raw.get("access_token") or "").strip()
            except Exception:
                token_value = ""
            if not token_value:
                bearer = _http_auth_header(mainwin.get_auth_token() or "")
                token_value = bearer[7:] if bearer.lower().startswith("bearer ") else bearer
            if token_value:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}token={_q(token_value)}"
            else:
                logger.warning("[Payment] no session token available — payment "
                               "page cannot create an attributed order")
        except Exception as _tok_err:
            logger.warning(f"[Payment] token attach failed: {_tok_err}")

        import asyncio as _asyncio
        from app_context import AppContext
        loop = AppContext.main_loop
        if not loop or not loop.is_running():
            return create_error_response(
                request, "NO_MAIN_LOOP",
                "Main event loop not running; cannot open payment dialog",
            )

        from gui.payments.payment_dialog import open_payment
        timeout_s = 600
        fut = _asyncio.run_coroutine_threadsafe(
            open_payment(url, timeout_s=timeout_s), loop,
        )
        result = fut.result(timeout=timeout_s + 30)

        if not result:
            return create_success_response(request, {
                "status": "CANCELLED",
                "message": "支付已取消",
            })
        status = result.get("status", "UNKNOWN")
        return create_success_response(request, {
            "status": status,
            "order_id": result.get("order_id", ""),
            "message": "支付成功" if status == "SUCCESS" else "支付未完成",
        })
    except Exception as e:
        logger.error(f"[Payment] topup error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, "PAYMENT_ERROR", str(e))


def _coupon_bearer_token() -> str:
    """Bearer for ecbAccountManager coupon calls. Prefer the CloudBase
    AccessToken (email/phone logins — what create_payment_order verifies), fall
    back to the eCan session token (WeChat logins have only this). Mirrors the
    token selection in handle_payment_topup."""
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin is None:
            return ""
        try:
            am = getattr(mainwin, "auth_manager", None)
            if am is not None:
                raw = am.get_tokens() or {}
                tok = str(raw.get("AccessToken") or raw.get("access_token") or "").strip()
                if tok:
                    return tok
        except Exception:
            pass
        from agent.cloud_api.cloud_api import _http_auth_header
        bearer = _http_auth_header(mainwin.get_auth_token() or "")
        return bearer[7:] if bearer.lower().startswith("bearer ") else bearer
    except Exception:
        return ""


@IPCHandlerRegistry.handler("billing.validateCoupon")
def handle_validate_coupon(request: IPCRequest,
                           params: Optional[Dict[str, Any]]) -> IPCResponse:
    """CN coupon preview — forward ``validate_coupon`` to ecbAccountManager.

    Advisory only (no side effects): shows the discounted 实付/到账 before the
    user pays. ``amount`` is in FEN (integer, ¥68.00 -> 6800) per the billing
    contract; the actual discount is re-checked server-side when the payment
    page calls create_payment_order. Returns the raw server payload
    ({valid, pay_amount, credit_amount, currency, reason, ...}) as the IPC data.
    """
    try:
        if not is_cn():
            return create_error_response(request, "CN_ONLY", "Coupons are CN-only")
        params = params or {}
        code = str(params.get("code") or "").strip()
        if not code:
            return create_error_response(request, "INVALID_PARAMS", "coupon code is required")
        try:
            amount = int(params.get("amount") or 0)   # FEN
        except (TypeError, ValueError):
            amount = 0
        purpose = str(params.get("purpose") or "topup").strip() or "topup"

        from gui.ipc.w2p_handlers.account_verify_handler import _account_manager_url
        url = _account_manager_url()
        if not url:
            return create_error_response(request, "NOT_CONFIGURED", "No GraphQL endpoint configured")
        token = _coupon_bearer_token()
        if not token:
            return create_error_response(request, "NO_TOKEN", "Not signed in — no bearer token available")

        body = {"action": "validate_coupon", "code": code, "amount": amount, "purpose": purpose}
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read(65536).decode("utf-8", "replace")
                status = resp.status
        except urllib.error.HTTPError as he:
            raw = he.read(4096).decode("utf-8", "replace")
            status = he.code
        except Exception as exc:
            logger.warning(f"[Coupon] validate transport error: {exc}")
            return create_error_response(request, "NETWORK_ERROR", str(exc))

        try:
            payload = json.loads(raw) if raw.strip() else {}
        except Exception:
            payload = {"raw": raw[:500]}
        if not isinstance(payload, dict):
            payload = {"result": payload}

        ok = status < 400 and bool(payload.get("success", True))
        logger.info(f"[Coupon] validate code={code} amount={amount} "
                    f"status={status} valid={payload.get('valid')} reason={payload.get('reason') or '-'}")
        if ok:
            return create_success_response(request, payload)
        return create_error_response(
            request, str(payload.get("error") or payload.get("code") or f"HTTP_{status}"),
            str(payload.get("message") or "coupon validation failed"), details=payload)
    except Exception as e:
        logger.error(f"[Coupon] validate error: {e}")
        return create_error_response(request, "COUPON_ERROR", str(e))
