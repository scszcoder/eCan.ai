"""The Feige pre-dispatch hook runs on every browser node. On another bundle's
front desk (PDD) it must still run the generic fan-out, but never register that
browser as a Feige shop or write the Feige front-desk slot: doing so made PDD the
"first" Feige shop, and Feige cold-start/WS dispatches ran through PDD's browser
and Q&A pool (customer run 99v, 2026-10-05)."""

import asyncio
from types import SimpleNamespace
from unittest import mock

import pytest

from agent.ec_skills import live_chat_dispatch as lcd
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import front_desk as fd


def _hook_ctx():
    f = lambda *a, **k: None
    return SimpleNamespace(
        parse_json_input=lambda inputs, key: {"enabled": True, "source_monitor_label": "新消息"},
        node_name="browser_automation_0t5L6", calling_agent_id="agent_x", mainwin=None,
        cached_browser_sessions={}, resolve_scope_key=lambda st: "node:browser_automation_0t5L6",
        dispatch_state_by_agent={}, is_dispatch_inflight=f, mark_dispatch_inflight=f,
        clear_dispatch_inflight=f, inflight_ttl_s=30, normalize_dispatch_identity_key=f,
        safe_format_dict=f)


def _run(site):
    agent = SimpleNamespace(browser_session=SimpleNamespace(
        browser_profile=SimpleNamespace(user_data_dir=f"C:/ecan_browser_data/{site}_profile")))
    ran = []

    async def fake_dispatch(cfg, ctx, ag):
        ran.append(ctx)
        return None

    tok = lcd.set_active_site(site)
    try:
        with mock.patch.object(fd, "_run_frontdesk_dispatch", fake_dispatch), \
             mock.patch.object(fd, "_set_fd_slot") as set_slot, \
             mock.patch("agent.ec_skills.browser_use_extension.hooks.external.feige_chat.ws_session.register_shop",
                        side_effect=lambda k: k) as reg:
            asyncio.run(fd.before_run_hook(agent, {}, {}, _hook_ctx()))
    finally:
        lcd.reset_active_site(tok)
    return ran, set_slot, reg


def test_pdd_node_runs_the_fanout_but_touches_no_feige_shop_state():
    ran, set_slot, reg = _run("pdd_chat")
    assert len(ran) == 1
    set_slot.assert_not_called()
    reg.assert_not_called()


def test_feige_node_still_registers_its_shop_and_slot():
    ran, set_slot, reg = _run("feige_chat")
    assert len(ran) == 1
    reg.assert_called_once()
    set_slot.assert_called_once()
