"""Tier-aware port of actionable_items.before_prompt_build_hook (Step 2c).

This is the second hook port in the hybrid-cloud migration.  It targets
the ``cloud_only`` tier and runs against :class:`CloudHookContext`
instead of the legacy ``BrowserUseHookContext``.

What changes vs. v1
-------------------

* ``hook_ctx.mainwin.agents`` enumeration → ``ctx.agent_registry.list_workers``
* ``_get_agent_load(agent_id, mainwin)``  → ``ctx.agent_registry.get_load(agent_id)``
* ``_auto_send_chat(mainwin, ...)``       → ``await ctx.send_chat.send_chat(...)``
* ``customer_recently_dispatched(c)``     → ``ctx.dispatch_state.is_inflight(c)``
* Module-level ``_dispatched_identity_keys`` dict → ``ctx.state[...]`` (SessionKV)
* Module-level ``_auto_dispatch_rr_index`` / ``_auto_dispatch_affinity`` /
  ``_auto_dispatch_cooldown`` dicts → ``ctx.state[...]`` (SessionKV)
* Local-mode glue dropped:
    - ``_mark_discovery``               (LLM tool-gate workaround; not needed cloud-side)
    - ``_send_chat_dedup_cache`` writes (handled inside cloud send_chat proxy)

What stays identical
--------------------

* :class:`PromptBuildContext` shape (already a pure data snapshot)
* ``state`` and ``inputs`` parameters
* :class:`PromptBuildResult` return shape
* The protocol-override block text (steeped in front-desk conventions)
* The actionable-item filtering logic in :func:`_evaluate_item_filter_pure`

The v1 hook in ``actionable_items.py`` remains in place; v2 is exercised
only by ``tests/test_actionable_items_v2.py`` and does not yet
participate in the live runtime — that wiring lands in Step 4.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from agent.ec_skills.browser_node.contexts import (
    CloudHookContext,
    PromptBuildContext,
    PromptBuildResult,
)

logger = logging.getLogger("ecan.hooks.feige_chat.v2")

__all__ = ["before_prompt_build_hook_v2", "FeigeActionableItemsHookV2"]


# ─────────────────────────────────────────────────────────────────────────────
# State-key helpers (built on SessionKV; replaces module-level dicts)
# ─────────────────────────────────────────────────────────────────────────────

# All state for this hook lives behind these key prefixes so the SessionKV
# can be inspected / namespaced cleanly.  Cooldown TTL only applies to
# safety-net GC; the primary dedup signal is identity_key presence in DOM.
_DISPATCHED_IDENT_PREFIX = "ai:dispatched_ident:"   # ai = actionable_items
_AFFINITY_PREFIX = "ai:affinity:"                   # customer → (agent_id, ts)
_RR_INDEX_PREFIX = "ai:rr_index:"                   # node_name → int
_COOLDOWN_PREFIX = "ai:cooldown:"                   # customer → ts
_DISPATCHED_IDENTITY_SAFETY_TTL_S = 3600.0
_AUTO_DISPATCH_COOLDOWN_S = 10.0


def _truthy_config_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return False


def _read_jsonish_input(inputs: dict, key: str, parser=None) -> Any:
    if callable(parser):
        try:
            parsed = parser(inputs, key)
            if parsed is not None:
                if not (
                    isinstance(parsed, dict)
                    and set(parsed.keys()) == {"content"}
                ):
                    return parsed
                raw = parsed.get("content")
                if raw in (None, ""):
                    return None
                if isinstance(raw, (dict, list)):
                    return raw
                if isinstance(raw, str):
                    try:
                        return json.loads(raw.strip())
                    except Exception:
                        return None
                return None
        except Exception:
            pass
    raw = (inputs.get(key) or {}).get("content") if isinstance(inputs, dict) else None
    if raw in (None, ""):
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw.strip())
        except Exception:
            return None
    return None


def _pre_dispatch_enabled_for_browser_event(inputs: dict, parser, evt_type: str) -> bool:
    if evt_type != "browser_event":
        return False
    cfg = _read_jsonish_input(inputs, "preDispatch", parser)
    return isinstance(cfg, dict) and _truthy_config_value(cfg.get("enabled"))


def _auto_dispatch_allows_pre_dispatch(auto_dispatch_cfg: dict | None) -> bool:
    if not isinstance(auto_dispatch_cfg, dict):
        return False
    for key in ("allow_with_preDispatch", "allow_with_pre_dispatch", "allowWithPreDispatch"):
        if _truthy_config_value(auto_dispatch_cfg.get(key)):
            return True
    dispatch_cfg = auto_dispatch_cfg.get("dispatch")
    if isinstance(dispatch_cfg, dict):
        for key in ("allow_with_preDispatch", "allow_with_pre_dispatch", "allowWithPreDispatch"):
            if _truthy_config_value(dispatch_cfg.get(key)):
                return True
    return False


def _build_pre_dispatch_guard_state(item_count: int) -> dict:
    return {
        "result": {
            "llm_result": {
                "all_done": True,
                "work_done": False,
                "hot_path": True,
                "hot_path_type": "predispatch_guard",
                "message": (
                    "preDispatch is enabled; suppressing autoDispatch/LLM "
                    f"fallback for browser_event ({item_count} actionable item(s))."
                ),
            }
        }
    }


def _pre_dispatch_suppresses_prompt_auto_dispatch(
    *,
    inputs: dict,
    parser,
    evt_type: str,
    auto_dispatch_cfg: dict | None,
) -> bool:
    """Whether prompt-build autoDispatch should defer to PreDispatch.

    The prompt-build hook runs before the full-local late PreDispatch hook.
    A short-circuit here prevents PreDispatch from running and can drop the
    browser_event.  Suppress only this hook's autoDispatch path; keep the
    actionable-items prompt as fallback if PreDispatch declines the event.
    """
    return (
        _pre_dispatch_enabled_for_browser_event(inputs, parser, evt_type)
        and not _auto_dispatch_allows_pre_dispatch(auto_dispatch_cfg)
    )


def _get_dispatched_at(state, identity_key: str) -> float:
    return float(state.get(_DISPATCHED_IDENT_PREFIX + identity_key, 0.0) or 0.0)


def _set_dispatched_at(state, identity_key: str, ts: float) -> None:
    state.set(_DISPATCHED_IDENT_PREFIX + identity_key, ts)


def _list_dispatched_identity_keys(state) -> list[str]:
    return [
        k[len(_DISPATCHED_IDENT_PREFIX):]
        for k in state.keys()
        if k.startswith(_DISPATCHED_IDENT_PREFIX)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Pure filter — no module-level state, takes a "is_dispatched" callback
# ─────────────────────────────────────────────────────────────────────────────


def _evaluate_item_filter_pure(
    item: dict,
    filter_cfg: dict | None,
    *,
    resolved: dict | None = None,
    customer_id: str | None = None,
    inflight_check=None,
    is_dispatched_check=None,
    cooldown_check=None,
    now: float | None = None,
) -> tuple[bool, str]:
    """Same semantics as v1's ``_evaluate_item_filter`` but every stateful
    check is delegated to a caller-supplied callback so the function is
    pure and can be reused from the cloud-side context.

    Callbacks (each takes the relevant key, returns a number / 0):

    * ``inflight_check(customer_id) -> age_seconds`` (>0 means in-flight)
    * ``is_dispatched_check(identity_key) -> dispatched_at`` (>0 means dedup)
    * ``cooldown_check(customer_id) -> last_dispatch_ts`` (>0 means still cooling)
    """
    if now is None:
        now = time.time()
    cfg = filter_cfg or {}
    resolved = resolved or {}

    # 1. Required fields
    for rf in (cfg.get("required_fields") or []):
        v = resolved.get(rf) or str(item.get(rf, "") or "").strip()
        if not v:
            return False, f"required_field_missing:{rf}"

    # 2. Exclude patterns
    for pat in (cfg.get("exclude_patterns") or []):
        if not isinstance(pat, dict):
            continue
        field = pat.get("field")
        if not field:
            continue
        val = str(resolved.get(field) or item.get(field, "") or "").strip()
        if not val:
            continue
        for op in ("equals", "contains", "prefix", "regex"):
            if op not in pat:
                continue
            literal = str(pat[op])
            try:
                if op == "equals":
                    matched = val == literal
                elif op == "contains":
                    matched = literal in val
                elif op == "prefix":
                    matched = val.startswith(literal)
                else:  # regex
                    matched = bool(re.search(literal, val))
            except Exception:
                matched = False
            if matched:
                return False, f"exclude:{field}:{op}:{literal[:30]}"

    se_cfg = cfg.get("exclude_self_echo") or {}
    il_cfg = cfg.get("inflight") or {}
    cd_cfg = cfg.get("cooldown") or {}

    # msg_text powers inflight's allow_new_message gate.
    msg_fields = il_cfg.get("message_fields") or ["last_message", "latest_message"]
    msg_text = ""
    for mf in msg_fields:
        v = resolved.get(mf) or item.get(mf) or ""
        if isinstance(v, str) and v.strip():
            msg_text = v.strip()[:80]
            break

    cust_id = customer_id or ""

    # 3. Identity-key dedup
    if se_cfg.get("enabled") and is_dispatched_check:
        ident = str(item.get("identity_key") or "").strip()
        if ident:
            try:
                dispatched_at = float(is_dispatched_check(ident) or 0.0)
            except Exception:
                dispatched_at = 0.0
            if dispatched_at > 0.0:
                logger.info(
                    f"[filter] identity_key dedup: cust={cust_id!r}, "
                    f"identity_key={ident!r}, age={now - dispatched_at:.1f}s"
                )
                return False, "already_dispatched"

    # 4. In-flight
    if il_cfg.get("enabled") and cust_id and inflight_check:
        try:
            age = float(inflight_check(cust_id) or 0.0)
        except Exception:
            age = 0.0
        if age > 0.0:
            if il_cfg.get("allow_new_message", True) and msg_text:
                pass  # new user message; let it through
            else:
                return False, f"inflight:{age:.0f}s"

    # 5. Cooldown
    if cd_cfg.get("enabled") and cust_id and cooldown_check:
        window = float(cd_cfg.get("window_s") or _AUTO_DISPATCH_COOLDOWN_S)
        try:
            cd_ts = float(cooldown_check(cust_id) or 0.0)
        except Exception:
            cd_ts = 0.0
        if cd_ts and (now - cd_ts) < window:
            return False, f"cooldown:{now - cd_ts:.0f}s"

    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# Auto-dispatch — cloud-side equivalent of v1's _try_auto_dispatch
# ─────────────────────────────────────────────────────────────────────────────


async def _try_auto_dispatch_cloud(
    *,
    config: dict,
    actionable: list,
    all_agents: list,
    caller_id: str,
    ctx: CloudHookContext,
    node_name: str,
    evt_type: str,
) -> dict | None:
    """Cloud-side port of v1 ``_try_auto_dispatch``.

    Differences vs. v1:

    * Uses ``ctx.agent_registry.get_load`` (not ``mainwin.agents`` walk)
    * Uses ``await ctx.send_chat.send_chat(...)`` (not sync ``_auto_send_chat``)
    * Reads/writes affinity, RR index, cooldown via ``ctx.state``
    * Reads inflight via ``ctx.dispatch_state.is_inflight``
    * No ``_mark_discovery`` call (cloud LLM has no tool-gate)
    * No ``_send_chat_dedup_cache`` writes (lives inside cloud send_chat)
    """
    # ── 1. Trigger check ──
    trigger = config.get("trigger") or {}
    required_evt = trigger.get("event_type", "")
    if required_evt and required_evt != evt_type:
        return None
    if trigger.get("require_actionable", True) and not actionable:
        return None

    # ── 2. Build candidate pool ──
    sel = config.get("agent_selection") or {}
    strategy = sel.get("strategy", "first_available")
    filter_tasks = sel.get("filter_by_tasks") or []
    affinity_ttl = float(sel.get("affinity_ttl_s", 1800))

    candidates = [
        a for a in all_agents
        if a.get("status", "active") != "disabled"
    ]
    if filter_tasks:
        _patterns = [str(p) for p in filter_tasks if str(p).strip()]

        def _matches(agent_entry: dict) -> bool:
            tasks = [str(t) for t in (agent_entry.get("tasks") or [])]
            return any(p in t for p in _patterns for t in tasks)

        candidates = [a for a in candidates if _matches(a)]
    if not candidates:
        logger.info(
            f"[AUTO-DISPATCH-V2] No candidate agents after filter "
            f"(filter_by_tasks={filter_tasks}), node={node_name}"
        )
        return None

    candidate_ids = {a["id"] for a in candidates}

    # ── 3. Payload template & item filter ──
    payload_tpl = config.get("payload_template") or {}
    if not payload_tpl:
        payload_tpl = {
            "customer_id": "{{customer_id || identity_key || customer_name}}",
            "customer_name": "{{customer_name || name}}",
            "latest_message": "{{latest_message || last_message || message}}",
        }

    _user_filter = dict(config.get("item_filter") or {})
    _user_filter.setdefault("exclude_self_echo", {"enabled": True})
    _user_filter.setdefault("cooldown", {
        "enabled": True,
        "window_s": _AUTO_DISPATCH_COOLDOWN_S,
    })
    item_filter_cfg = _user_filter
    dispatch_cfg = config.get("dispatch") or {}
    use_dedup = dispatch_cfg.get("dedup", True)

    # ── 4. Agent picker (affinity → strategy fallback) ──
    rr_idx_key = _RR_INDEX_PREFIX + node_name
    _rr_idx = int(ctx.state.get(rr_idx_key, 0) or 0)
    now = time.time()
    _load_cache: dict[str, int] = {}

    def _agent_load(aid: str) -> int:
        if aid not in _load_cache:
            try:
                _load_cache[aid] = int(ctx.agent_registry.get_load(aid))
            except Exception:
                _load_cache[aid] = 0
        return _load_cache[aid]

    def _pick_agent(customer_id: str) -> dict:
        nonlocal _rr_idx

        # Affinity check
        if customer_id:
            entry = ctx.state.get(_AFFINITY_PREFIX + customer_id)
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                prev_agent_id, ts = entry
                try:
                    if (now - float(ts)) < affinity_ttl and prev_agent_id in candidate_ids:
                        for c in candidates:
                            if c["id"] == prev_agent_id:
                                return c
                except (TypeError, ValueError):
                    pass

        # Strategy fallback
        if strategy == "round_robin":
            agent = candidates[_rr_idx % len(candidates)]
            _rr_idx += 1
            return agent

        # first_available: lowest pending-task count
        return min(candidates, key=lambda c: _agent_load(c["id"]))

    dispatched = 0
    for item in actionable:
        # Resolve template fields
        resolved = {}
        for key, tpl in payload_tpl.items():
            resolved[key] = ctx.resolve_template(tpl, item)

        cust_id = ctx.normalize_dispatch_identity_key(
            resolved.get("customer_id") or resolved.get("customer_name") or ""
        )

        keep, reason = _evaluate_item_filter_pure(
            item,
            item_filter_cfg,
            resolved=resolved,
            customer_id=cust_id,
            inflight_check=ctx.dispatch_state.is_inflight,
            is_dispatched_check=lambda ident: _get_dispatched_at(ctx.state, ident),
            cooldown_check=lambda c: float(ctx.state.get(_COOLDOWN_PREFIX + c, 0.0) or 0.0),
            now=now,
        )
        if not keep:
            logger.info(
                f"[AUTO-DISPATCH-V2] filter drop '{cust_id or '?'}' "
                f"reason={reason}, node={node_name}"
            )
            continue

        target_agent = _pick_agent(cust_id)
        target_agent_id = target_agent.get("id", "")
        target_agent_name = target_agent.get("name", target_agent_id)

        message_str = json.dumps(resolved, ensure_ascii=False)
        result = await ctx.send_chat.send_chat(
            target_agent_id,
            message_str,
            metadata={"sender_agent_id": caller_id, "node_name": node_name},
        )

        if result.get("success"):
            dispatched += 1

            # Affinity update
            if cust_id:
                ctx.state.set(_AFFINITY_PREFIX + cust_id, [target_agent_id, now])

            # Identity-key dedup
            ident = str(item.get("identity_key") or "").strip()
            if ident:
                _set_dispatched_at(ctx.state, ident, now)

            # Cooldown
            if use_dedup and cust_id:
                ctx.state.set(_COOLDOWN_PREFIX + cust_id, now)

            logger.info(
                f"[AUTO-DISPATCH-V2] sent '{resolved.get('customer_name', '?')}' "
                f"→ {target_agent_name} (load={_agent_load(target_agent_id)}) "
                f"msg='{message_str[:80]}', node={node_name}"
            )
        else:
            logger.warning(
                f"[AUTO-DISPATCH-V2] failed for item: {result.get('error', '?')}, "
                f"node={node_name}"
            )

    # Persist RR index
    ctx.state.set(rr_idx_key, _rr_idx)

    # GC stale identity-key records (safety net)
    for ident in _list_dispatched_identity_keys(ctx.state):
        ts = _get_dispatched_at(ctx.state, ident)
        if ts > 0 and (now - ts) > _DISPATCHED_IDENTITY_SAFETY_TTL_S:
            ctx.state.delete(_DISPATCHED_IDENT_PREFIX + ident)

    if dispatched > 0:
        logger.info(
            f"[AUTO-DISPATCH-V2] {dispatched}/{len(actionable)} items dispatched, "
            f"skipping LLM Phase 1, node={node_name}"
        )
        return {
            "result": {
                "llm_result": {
                    "all_done": False,
                    "work_done": False,
                    "hot_path": True,
                    "hot_path_type": "auto_dispatch",
                }
            }
        }
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Prompt-build hook — main entry point
# ─────────────────────────────────────────────────────────────────────────────


async def before_prompt_build_hook_v2(
    state: dict,
    inputs: dict,
    ctx: CloudHookContext,
    prompt_ctx: PromptBuildContext,
) -> PromptBuildResult | None:
    """Cloud-only port of ``actionable_items.before_prompt_build_hook``.

    Same flow as v1:

    1. Apply data-driven item filter.
    2. Build task-hint block + protocol-override block.
    3. Inject pre-resolved agent_list (so LLM skips ``bu_select_agents``).
    4. If autoDispatch is configured, attempt deterministic dispatch.
    """
    actionable_field = prompt_ctx.actionable_field
    if not actionable_field:
        return None

    compact_items = prompt_ctx.compact_items
    actionable_raw = list(prompt_ctx.actionable_raw)
    if not compact_items:
        return None

    node_name = ctx.node_name
    calling_agent_id = ctx.calling_agent_id
    evt_type = prompt_ctx.event_type
    _now = time.time()

    # ── Resolve user-authored filter ──
    _user_filter: dict = {}
    try:
        _fa_raw = (inputs.get("autoDispatch") or {}).get("content")
        if isinstance(_fa_raw, str) and _fa_raw.strip():
            _fa_parsed = json.loads(_fa_raw)
            if isinstance(_fa_parsed, dict):
                _fif = _fa_parsed.get("item_filter")
                if isinstance(_fif, dict):
                    _user_filter = dict(_fif)
        elif isinstance(_fa_raw, dict):
            _fif = _fa_raw.get("item_filter")
            if isinstance(_fif, dict):
                _user_filter = dict(_fif)
    except Exception as _fa_err:
        logger.debug(
            f"[V2 actionable_items] could not parse autoDispatch.item_filter "
            f"({_fa_err}); using defaults"
        )

    _user_filter.setdefault("inflight", {
        "enabled": True,
        "allow_new_message": True,
        "message_fields": ["last_message", "latest_message"],
    })
    _user_filter.setdefault("exclude_self_echo", {"enabled": True})
    _user_filter.setdefault("cooldown", {
        "enabled": True,
        "window_s": _AUTO_DISPATCH_COOLDOWN_S,
    })

    # ── Prune identity_key records for entries no longer in DOM ──
    _live_ident_keys = {
        str(_it.get("identity_key") or "").strip()
        for _it in compact_items
        if _it.get("identity_key")
    }
    for _stale in _list_dispatched_identity_keys(ctx.state):
        if _stale and _stale not in _live_ident_keys:
            ctx.state.delete(_DISPATCHED_IDENT_PREFIX + _stale)

    # ── Apply filter to actionable_raw ──
    _actionable = []
    _filtered_out: list[tuple[str, str]] = []
    for _it in actionable_raw:
        _cust_id = ctx.normalize_dispatch_identity_key(
            _it.get("customer_id")
            or _it.get("customer_name")
            or _it.get("name")
            or ""
        )
        _keep, _reason = _evaluate_item_filter_pure(
            _it,
            _user_filter,
            customer_id=_cust_id,
            inflight_check=ctx.dispatch_state.is_inflight,
            is_dispatched_check=lambda ident: _get_dispatched_at(ctx.state, ident),
            cooldown_check=lambda c: float(ctx.state.get(_COOLDOWN_PREFIX + c, 0.0) or 0.0),
            now=_now,
        )
        if _keep:
            _actionable.append(_it)
        else:
            _filtered_out.append((_cust_id or "?", _reason))
    if _filtered_out:
        logger.info(
            f"[V2 actionable_items] filtered {len(_filtered_out)} entry/entries "
            f"(kept {len(_actionable)} of {len(actionable_raw)}): "
            + ", ".join(f"{c}({r})" for c, r in _filtered_out)
            + f" node={node_name}"
        )

    _auto_dispatch_guard_cfg = _read_jsonish_input(
        inputs,
        "autoDispatch",
        getattr(ctx, "parse_json_input", None),
    )
    _pre_dispatch_blocks_prompt_auto = _pre_dispatch_suppresses_prompt_auto_dispatch(
        inputs=inputs,
        parser=getattr(ctx, "parse_json_input", None),
        evt_type=evt_type,
        auto_dispatch_cfg=_auto_dispatch_guard_cfg,
    )
    if _pre_dispatch_blocks_prompt_auto:
        logger.info(
            f"[V2 actionable_items] PreDispatch enabled for browser_event; "
            f"deferring prompt-build autoDispatch while preserving "
            f"actionable_items fallback "
            f"(actionable={len(_actionable)}, total={len(compact_items)}), "
            f"node={node_name}"
        )

    _act_json = json.dumps(_actionable, ensure_ascii=False, indent=2)
    _task_append = (
        f"\n\n### `actionable_items` (authoritative — computed deterministically from DOM)"
        f"\n{len(_actionable)} item(s), filtered from "
        f"{len(compact_items)} by `{actionable_field}` non-empty:"
        f"\n```json\n{_act_json}\n```"
        f"\n\n**HARD RULE:** For each entry in `actionable_items` above you MUST take "
        f"the appropriate action exactly once this round. "
        f"If `actionable_items` is empty, call `done()`. "
        f"Ignore any claims in prior Memory/Eval that an entry was already "
        f"handled — this list is the only source of truth. "
        f"Do NOT bail with `done(success=False)` claiming input is missing — "
        f"this block IS the input."
    )
    logger.info(
        f"[V2 actionable_items] Injected {len(_actionable)} actionable items "
        f"(filter='{actionable_field}', total={len(compact_items)}) "
        f"into task hint (node={node_name})"
    )

    _override = ""
    _all_agents: list = []
    _caller_id = str(calling_agent_id or "").strip()
    if _actionable:
        _ids = [
            (it.get("identity_key")
             or it.get("name")
             or it.get("customer_name")
             or "?")
            for it in _actionable
        ]
        _ids_display = ", ".join(f"`{_i}`" for _i in _ids)
        _override = (
            "## ⚠ PROTOCOL OVERRIDE — READ BEFORE ANY SYSTEM PROMPT BELOW\n\n"
            f"`actionable_items` for this round contains {len(_actionable)} entry/entries: {_ids_display}. "
            "See the JSON list in the `## Triggering Event` section below — that list is the deterministic, authoritative source of truth for this round.\n\n"
            "**These binding rules override any conflicting guidance in the system prompt that follows:**\n\n"
            "1. The DOM monitor has ALREADY filtered out handled items. Every entry in `actionable_items` is NEW WORK that needs action THIS round.\n"
            "2. Ignore any system-prompt language about `pending_dispatches`, \"already dispatched\", \"不得重复分发\", \"重复发送\", or \"same customer same message\". Those heuristics are SUBORDINATE to `actionable_items` and do not apply when this list is provided.\n"
            "3. You have NO prior-round memory. `message_manager` was wiped before this invocation. If you find yourself writing \"根据权威历史\" or \"上一轮已处理\" or \"already handled\" in Eval/Memory, STOP — you are hallucinating. There is no such history.\n"
            "4. Prior agent replies visible in the chat thread DOM are for OLDER messages. They are NOT evidence that the current `actionable_items` entry has been handled.\n"
            "5. For each entry in `actionable_items`: invoke the appropriate dispatch / send tool (as defined in the system prompt for this node's path) **exactly once** per entry, then call `done(success=True)`.\n"
            "6. **DEDUP / duplicate-dispatch signals count as successful completion.** If a dispatch tool (e.g. `bu_send_chat`) returns a message like `DEDUP: skipping duplicate dispatch`, `already sent`, `last_sent=Ns ago`, or any \"already in flight\" indicator, treat that entry as DONE for this round. Call `done(success=True)` immediately — do NOT retry.\n"
            "7. **Do NOT rotate to a different recipient agent to bypass DEDUP.** DEDUP is a correct signal that work for this customer is already in flight with the originally-assigned respondent. Rotating to another agent (客服小王, 客服小张, etc.) to \"satisfy must-dispatch\" creates duplicate customer replies and is FORBIDDEN.\n"
            "8. Calling `done(success=True)` while `actionable_items` is non-empty and neither a real dispatch NOR a DEDUP/already-sent response has occurred this round is a PROTOCOL VIOLATION.\n"
            "9. If `actionable_items` is empty, call `done(success=True)` immediately — no work to do.\n"
            "10. **Never use placeholder or template strings as real tool arguments.** "
            "Do NOT pass `agent_id_1`, `agent_id_2`, `<分配的代理ID>`, `<example_agent_id>`, or any other placeholder/template string as `recipient_agent_id` — those are illustrations in the system prompt, not real values. Use ONLY the real agent IDs from the Pre-resolved agent_list above. A dispatch with a fake ID silently fails and the customer gets no reply.\n\n"
        )

        # ── Inject pre-resolved agent list ──
        try:
            if _caller_id:
                _all_agents = [
                    a for a in ctx.agent_registry.list_workers(exclude=_caller_id)
                    if a.get("status", "active") != "disabled"
                ]
                if _all_agents:
                    _agent_lines = []
                    for _ag in _all_agents:
                        _tasks_str = ", ".join(_ag.get("tasks", [])) or "none"
                        _agent_lines.append(
                            f"- {_ag['name']} (ID: {_ag['id']}, tasks: {_tasks_str})"
                        )
                    _override += (
                        "### Pre-resolved `agent_list` (skip `bu_select_agents`)\n\n"
                        "The following agents are available for dispatch. "
                        "Use these IDs directly — do NOT call `bu_select_agents`, it is unnecessary.\n\n"
                        + "\n".join(_agent_lines)
                        + "\n\n---\n\n"
                    )
                    logger.info(
                        f"[V2 actionable_items] Injected pre-resolved agent_list "
                        f"({len(_all_agents)} agents) into override block, "
                        f"node={node_name}"
                    )
        except Exception as _agent_inject_err:
            logger.debug(
                f"[V2 actionable_items] Failed to inject agent_list "
                f"(non-fatal): {_agent_inject_err}"
            )
        _override += "---\n\n"

        # ── Configurable auto-dispatch short-circuit ──
        try:
            _ad_raw = (inputs.get("autoDispatch") or {}).get("content")
            _ad_cfg = None
            if isinstance(_ad_raw, str) and _ad_raw.strip():
                _ad_cfg = json.loads(_ad_raw)
            elif isinstance(_ad_raw, dict):
                _ad_cfg = _ad_raw
            if (
                _ad_cfg
                and not _pre_dispatch_blocks_prompt_auto
                and _all_agents
                and _caller_id
            ):
                _ad_state = await _try_auto_dispatch_cloud(
                    config=_ad_cfg,
                    actionable=_actionable,
                    all_agents=_all_agents,
                    caller_id=_caller_id,
                    ctx=ctx,
                    node_name=node_name,
                    evt_type=evt_type,
                )
                if _ad_state is not None:
                    return PromptBuildResult(short_circuit_state=_ad_state)
        except Exception as _ad_err:
            logger.debug(
                f"[AUTO-DISPATCH-V2] config-driven dispatch failed "
                f"(non-fatal, falling back to LLM): {_ad_err}"
            )

    return PromptBuildResult(
        task_hint_append=_task_append,
        override_prepend=_override,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Class wrapper — for symmetry with FeigeQuickReplyHookV2
# ─────────────────────────────────────────────────────────────────────────────


class FeigeActionableItemsHookV2:
    """Tier ``cloud_only`` port of actionable_items.before_prompt_build_hook.

    Class wrapper around :func:`before_prompt_build_hook_v2` for symmetry
    with :class:`FeigeQuickReplyHookV2` and so the future tier-aware
    loader (Step 4) can instantiate hooks uniformly.
    """

    EXECUTION_TIER = "cloud_only"

    def __init__(self, config: dict | None = None):
        self.config = dict(config or {})

    async def run(
        self,
        ctx: CloudHookContext,
        state: dict,
        inputs: dict,
        prompt_ctx: PromptBuildContext,
    ) -> PromptBuildResult | None:
        return await before_prompt_build_hook_v2(state, inputs, ctx, prompt_ctx)
