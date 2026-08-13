"""IPC handlers for human-intervention state (mt017).

When a human customer-service agent jumps into Feige and types a reply
directly, ``feige_chat.human_intervention`` tracks which customers are
currently being handled by humans (TTL 120s).  These handlers expose
the state to the React front-end so the operator can:

* ``feige_human_intervention.snapshot`` — list customers currently
  marked human-handled (with age + last-seen msg_id).  Used by the
  GUI to show a small badge per customer indicating "Human-handled,
  automation paused".
* ``feige_human_intervention.clear`` — clear a specific customer's
  flag immediately, resuming automation without waiting for the
  120s TTL.  Useful when the operator finished handling and wants
  the bot back online.
* ``feige_human_intervention.mark`` — manually mark a customer as
  human-handled (paused).  Useful when the operator is ABOUT to type
  a reply and wants to prevent the bot from also typing one.

The detection itself happens automatically via the thread-scrape in
``pre_dispatch_enrich._scrape_and_override_last_message`` — these
handlers are just GUI-facing controls + diagnostics.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import (
    IPCRequest,
    IPCResponse,
    create_error_response,
    create_success_response,
)
from utils.logger_helper import logger_helper as logger


def _load_module():
    """Lazy import — feige_chat is a hook bundle and may not be loaded
    in cloud-only contexts.  Returns ``None`` cleanly when unavailable."""
    try:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            human_intervention as _hi,
        )
        return _hi
    except Exception as exc:
        logger.debug(f"[feige_human_intervention] feige_chat hook not loaded: {exc}")
        return None


@IPCHandlerRegistry.handler("feige_human_intervention.snapshot")
def handle_snapshot(
    request: IPCRequest, params: Optional[Dict[str, Any]]
) -> IPCResponse:
    """Return all customers currently marked human-handled, plus per-entry
    age in seconds and the msg_id of the human-typed bubble.

    Response shape::

        {
            "ttl_s": 120.0,
            "active": {
                "客户01": {"ts": 1779348385.5, "age_s": 12.3, "msg_id": "abc"},
                ...
            }
        }
    """
    try:
        mod = _load_module()
        if mod is None:
            return create_success_response(
                request,
                {"ttl_s": 0.0, "active": {}, "module_loaded": False},
            )
        snap = mod.snapshot()
        snap["module_loaded"] = True
        return create_success_response(request, snap)
    except Exception as exc:
        logger.error(f"[feige_human_intervention.snapshot] error: {exc}")
        return create_error_response(
            request, "HUMAN_INTERVENTION_SNAPSHOT_ERROR", str(exc),
        )


@IPCHandlerRegistry.handler("feige_human_intervention.clear")
def handle_clear(
    request: IPCRequest, params: Optional[Dict[str, Any]]
) -> IPCResponse:
    """Clear a customer's human-handled flag immediately, resuming
    automation before the 120s TTL expires.

    Params::

        {"customer_key": "客户01"}

    If ``customer_key`` is empty or missing, returns an error.
    """
    try:
        if not isinstance(params, dict):
            return create_error_response(
                request, "INVALID_PARAMS", "expected dict with customer_key",
            )
        customer_key = str(params.get("customer_key") or "").strip()
        if not customer_key:
            return create_error_response(
                request, "INVALID_PARAMS", "customer_key is required",
            )
        mod = _load_module()
        if mod is None:
            return create_error_response(
                request,
                "MODULE_NOT_LOADED",
                "feige_chat hook bundle is not loaded in this process",
            )
        was_active = mod.is_handled_recent(customer_key)
        mod.clear(customer_key)
        logger.info(
            f"[feige_human_intervention.clear] cust={customer_key!r} "
            f"(was_active={was_active})"
        )
        return create_success_response(
            request,
            {"customer_key": customer_key, "was_active": was_active, "cleared": True},
        )
    except Exception as exc:
        logger.error(f"[feige_human_intervention.clear] error: {exc}")
        return create_error_response(
            request, "HUMAN_INTERVENTION_CLEAR_ERROR", str(exc),
        )


@IPCHandlerRegistry.handler("feige_human_intervention.mark")
def handle_mark(
    request: IPCRequest, params: Optional[Dict[str, Any]]
) -> IPCResponse:
    """Manually mark a customer as human-handled.  Use when the operator
    is about to type a reply and wants to pause the bot's automation
    for that customer (auto-resumes after TTL or via ``clear``).

    Params::

        {
            "customer_key": "客户01",
            "msg_id": "optional human bubble msg_id",
            "source": "manual_mark"   # diagnostic tag, default "manual"
        }
    """
    try:
        if not isinstance(params, dict):
            return create_error_response(
                request, "INVALID_PARAMS", "expected dict with customer_key",
            )
        customer_key = str(params.get("customer_key") or "").strip()
        if not customer_key:
            return create_error_response(
                request, "INVALID_PARAMS", "customer_key is required",
            )
        msg_id = str(params.get("msg_id") or "").strip()
        source = str(params.get("source") or "manual").strip()
        mod = _load_module()
        if mod is None:
            return create_error_response(
                request,
                "MODULE_NOT_LOADED",
                "feige_chat hook bundle is not loaded in this process",
            )
        mod.mark_handled(customer_key, msg_id, source=source)
        # Also cancel any in-flight placeholder for this customer so the
        # bot doesn't keep firing while the human is composing.
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                placeholder_timer as _pt,
            )
            _pt.cancel_any_for_customer(customer_key)
        except Exception:
            pass
        return create_success_response(
            request,
            {
                "customer_key": customer_key,
                "msg_id": msg_id,
                "source": source,
                "marked": True,
                "ttl_s": mod.HUMAN_HANDLED_TTL_S,
            },
        )
    except Exception as exc:
        logger.error(f"[feige_human_intervention.mark] error: {exc}")
        return create_error_response(
            request, "HUMAN_INTERVENTION_MARK_ERROR", str(exc),
        )
