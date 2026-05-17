"""Skill Editor Cloud Agent — proxy MCP tool.

Exposes a single MCP tool, ``consult_skill_editor``, that forwards the
user's question to the cloud-based Skill Editor agent (the same Lambda
that powers the GUI's Skill Editor page) and returns its reply.

Used to "merge" a generic helper agent's local chat with the cloud
skill-editor agent: when the helper LLM decides the user's request is
about creating/editing/debugging a skill or analyzing logs, it calls
this tool and relays the answer back. The cloud agent decides whether
the request is something it can help with — for log analysis or
non-skill questions it'll fall through to its own general-purpose path,
which is fine.

Session handling
----------------
The proxy maintains ONE "helper-proxy" session per user (separate from
whatever sessions the Skills page is using, to avoid bleeding
helper-chat events onto the canvas). The session id is cached in
``_HELPER_PROXY_SESSIONS`` and persisted across calls for the lifetime
of the process. If the cached id is rejected by the cloud (session
deleted, etc.), a fresh one is created on the next call.

Badge marker
------------
The returned text is prefixed with ``[SkillEditor] `` — the helper
LLM's system prompt instructs it to preserve this prefix in its final
``send_chat`` reply so the frontend can render a "via cloud skill
editor" badge. See ``ChatDetail.tsx`` for the render side.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

import mcp.types as types

from utils.logger_helper import logger_helper as logger


# Marker that the helper LLM is instructed to keep at the start of its
# reply. The frontend strips it and renders a badge in its place.
BADGE_MARKER = "[SkillEditor]"

# Sentinel emitted by ``hand_off_to_skill_editor``. When ChatDetail's
# MessageRenderer sees this prefix, it stashes the inner payload in
# ``sessionStorage`` and navigates to the Skills page, which then seeds
# its chat input from the stashed payload. The protocol is intentionally
# embedded in the message text (rather than a parallel metadata field)
# so it survives the regular send_chat → chat-history round-trip without
# needing a chat-message schema migration.
HANDOFF_MARKER = "[HandoffToSkillEditor]"

# (user_owner) -> session_id cache. Process-local; rebuilt on restart.
# We don't persist to disk: the cloud's S3-backed sessions still exist
# across restarts and a fresh create-session is cheap (~one AppSync
# round-trip). Persistence would just add a settings.json schema entry
# for marginal benefit.
_HELPER_PROXY_SESSIONS: Dict[str, str] = {}
_SESSION_CACHE_LOCK = threading.Lock()

_SESSION_NAME = "Helper Chat Proxy"


def _resolve_current_user() -> str:
    """Return the user identifier the cloud relay uses for owner-filtering."""
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin is not None:
            return str(getattr(mainwin, "user", None) or "")
    except Exception:
        pass
    return ""


def _ensure_session_id() -> Optional[str]:
    """Return the cached helper-proxy session id, lazy-creating one if needed."""
    user = _resolve_current_user()
    if not user:
        logger.warning("[consult_skill_editor] No user identity; cannot create session")
        return None

    with _SESSION_CACHE_LOCK:
        cached = _HELPER_PROXY_SESSIONS.get(user)
    if cached:
        return cached

    try:
        from gui.ipc.w2p_handlers.skill_editor_cloud_relay import relay_create_session
    except Exception as exc:
        logger.warning(f"[consult_skill_editor] relay_create_session unavailable: {exc}")
        return None

    session = relay_create_session(name=_SESSION_NAME, flowgram_id=None)
    if not isinstance(session, dict):
        logger.warning("[consult_skill_editor] create_session returned non-dict")
        return None
    session_id = str(session.get("id") or session.get("sessionId") or "")
    if not session_id:
        logger.warning(f"[consult_skill_editor] No session id in response: keys={list(session.keys())}")
        return None

    with _SESSION_CACHE_LOCK:
        _HELPER_PROXY_SESSIONS[user] = session_id
    logger.info(f"[consult_skill_editor] Created helper-proxy session={session_id} for user={user!r}")
    return session_id


def _invalidate_session(user: str) -> None:
    with _SESSION_CACHE_LOCK:
        _HELPER_PROXY_SESSIONS.pop(user, None)


def get_consult_skill_editor_tool_schema() -> types.Tool:
    """MCP schema for the helper -> cloud-skill-editor proxy.

    Description deliberately spells out the routing rule so the local
    LLM picks the right time to call this. Keep this aligned with the
    basic_chatter skill's system prompt.
    """
    return types.Tool(
        name="consult_skill_editor",
        description=(
            "PRIMARY ROUTING TARGET for any user message about skills, "
            "flowgrams, nodes, hooks, logs, errors, debug, runtime "
            "behavior, traceback, exception, crash, stall, slow, "
            "regression. Call this FIRST and immediately for those "
            "topics — do NOT clarify locally or ask the user for files "
            "/ paths / formats first. The cloud Skill Editor agent has "
            "full access to the user's skills, flowgrams, skill-editor "
            "tools (canvas ops, validation, plan generation, log "
            "ingest), and will either answer, ask a clarifying "
            "question, return an implementation plan, or generate a "
            "flowgram diff. Pass the user's question verbatim plus any "
            "context they provided (skill name, log snippet, error "
            "text). DO NOT use this for ordinary chitchat or questions "
            "you can clearly answer with the other available tools "
            "yourself."
        ),
        # Wrapped in an ``input`` object to match the calling convention of
        # the other tools (send_chat, rag_query, etc.). The compact prompt
        # provider unwraps this and presents the LLM with the inner param
        # names; the dispatcher invokes the tool with ``args = {"input": {...}}``.
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["prompt"],
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": (
                                "The user's question, restated clearly. "
                                "Include any context the user has provided "
                                "(skill name, log snippet, error message)."
                            ),
                        },
                        "context_hint": {
                            "type": "string",
                            "description": (
                                "Optional one-line hint about what the "
                                "helper agent thinks the user wants "
                                "(e.g. 'create new skill', 'debug failing "
                                "chat_node', 'explain pend_event behavior'). "
                                "Used to disambiguate."
                            ),
                        },
                    },
                },
            },
        },
    )


async def async_consult_skill_editor(mainwin: Any, args: Dict[str, Any]) -> List[Any]:
    """Body of the ``consult_skill_editor`` MCP tool.

    Signature matches the other chat_tools / aws_tools entries used by
    ``_CLOUD_TOOL_REGISTRY``: ``async def fn(mainwin, args) -> list``.
    Returns a single ``TextContent`` whose text is what the helper LLM
    will see as the tool result.
    """
    # ``TextContent`` import is local because mcp.types resolves lazily
    # in some test environments.
    from mcp.types import TextContent

    # The MCP dispatcher wraps params in ``{"input": {...}}`` per the
    # standard tool-calling convention, but defensive callers (or test
    # harnesses) may pass the params flat. Accept either shape.
    _payload = args.get("input") if isinstance(args, dict) else None
    if not isinstance(_payload, dict):
        _payload = args if isinstance(args, dict) else {}
    prompt = str(_payload.get("prompt") or "").strip()
    context_hint = str(_payload.get("context_hint") or "").strip()
    if not prompt:
        return [TextContent(type="text", text=f"{BADGE_MARKER} (no prompt provided)")]

    # Compose the cloud message. The context hint goes inline so the
    # cloud agent has the helper's classification too.
    if context_hint:
        cloud_prompt = f"{prompt}\n\n(helper hint: {context_hint})"
    else:
        cloud_prompt = prompt

    session_id = _ensure_session_id()
    if not session_id:
        return [TextContent(
            type="text",
            text=(
                f"{BADGE_MARKER} Could not reach the cloud Skill Editor "
                f"(no session or no cloud auth). Try again after logging "
                f"in, or answer the user locally if possible."
            ),
        )]

    try:
        from gui.ipc.w2p_handlers.skill_editor_cloud_relay import relay_send_message
    except Exception as exc:
        logger.warning(f"[consult_skill_editor] relay_send_message unavailable: {exc}")
        return [TextContent(
            type="text",
            text=f"{BADGE_MARKER} Cloud relay unavailable: {exc}",
        )]

    response = relay_send_message(session_id=session_id, content=cloud_prompt)
    if response is None:
        # The cloud rejected our session id OR the call failed. Invalidate
        # the cached session so the next call creates a fresh one — this
        # auto-recovers from "session deleted on cloud side" cases.
        user = _resolve_current_user()
        if user:
            _invalidate_session(user)
        logger.warning("[consult_skill_editor] relay_send_message returned None; session invalidated")
        return [TextContent(
            type="text",
            text=(
                f"{BADGE_MARKER} The cloud Skill Editor did not respond. "
                f"Try again — the session has been refreshed."
            ),
        )]

    # The relay already parses AWSJSON fields. Pull out the assistant text
    # and any structured artifacts we want the helper LLM to know about.
    assistant_text = ""
    msg = response.get("message")
    if isinstance(msg, dict):
        assistant_text = str(msg.get("content") or "").strip()
    if not assistant_text:
        # Some response shapes put the text at the top level under
        # different keys; fall back to a few of them.
        for key in ("content", "text", "assistantMessage"):
            v = response.get(key)
            if isinstance(v, str) and v.strip():
                assistant_text = v.strip()
                break
    if not assistant_text:
        assistant_text = "(Cloud Skill Editor returned an empty reply.)"

    # ── A2UI artifact rendering ────────────────────────────────────────
    # The Skills page renders these as rich interactive cards. The helper
    # chat UI doesn't have those components yet, so we render the same
    # data as nicely-formatted markdown sections appended to the cloud's
    # text reply. The helper LLM is system-prompted to preserve the
    # ``[SkillEditor]`` prefix and pass this text through unchanged
    # (modulo a short summary), so the user sees the artifacts inline in
    # the chat. Future work: define a chat-message metadata schema so
    # the frontend can render true cards instead of markdown.
    sections = _format_artifact_sections(response)
    suffix = ("\n\n---\n" + "\n\n".join(sections)) if sections else ""
    return [TextContent(
        type="text",
        text=f"{BADGE_MARKER} {assistant_text}{suffix}",
    )]


def _format_artifact_sections(response: Dict[str, Any]) -> List[str]:
    """Render clarification/plan/flowgram/validation artifacts as markdown.

    Each section is a self-contained markdown block that the helper LLM
    is instructed to pass through to the user verbatim. Sections that
    contain no data are skipped (so a plain text reply with no artifacts
    has no trailing horizontal-rule + empty sections).
    """
    out: List[str] = []

    # Clarification questions — show each as a numbered question with
    # bulleted choices so the user can type back a choice.
    clarification = response.get("clarification")
    if isinstance(clarification, list) and clarification:
        lines = ["### 💬 需要澄清的问题 / Clarification needed"]
        for idx, q in enumerate(clarification, start=1):
            if not isinstance(q, dict):
                continue
            qtext = str(q.get("question") or "").strip() or "(no question text)"
            ctx = str(q.get("context") or "").strip()
            allow_multi = bool(q.get("allow_multiple"))
            lines.append(f"\n**{idx}. {qtext}**")
            if ctx:
                lines.append(f"   *{ctx}*")
            choices = q.get("choices") or []
            if isinstance(choices, list) and choices:
                for c in choices:
                    if isinstance(c, dict):
                        ctext = str(c.get("text") or c.get("label") or c.get("id") or "").strip()
                        if ctext:
                            lines.append(f"   - {ctext}")
                    elif isinstance(c, str):
                        lines.append(f"   - {c}")
            if allow_multi:
                lines.append("   *(multiple selections allowed)*")
        lines.append(
            "\n*Reply with your selection(s) — I'll forward your answer to the cloud Skill Editor.*"
        )
        out.append("\n".join(lines))

    # Implementation plan — summary + numbered steps + complexity badge.
    plan = response.get("plan")
    if isinstance(plan, dict) and plan:
        lines = ["### 📋 实施计划 / Implementation Plan"]
        summary = str(plan.get("summary") or "").strip()
        if summary:
            lines.append(f"\n{summary}")
        complexity = str(plan.get("complexity") or "").strip()
        if complexity:
            badge = {"simple": "🟢", "medium": "🟡", "complex": "🔴"}.get(complexity.lower(), "⚪")
            lines.append(f"\n**Complexity:** {badge} `{complexity}`")
        steps = plan.get("steps") or []
        if isinstance(steps, list) and steps:
            lines.append("\n**Steps:**")
            for idx, s in enumerate(steps, start=1):
                if isinstance(s, dict):
                    stitle = str(s.get("title") or s.get("name") or f"Step {idx}").strip()
                    sdesc = str(s.get("description") or s.get("desc") or "").strip()
                    lines.append(f"{idx}. **{stitle}**" + (f" — {sdesc}" if sdesc else ""))
                elif isinstance(s, str):
                    lines.append(f"{idx}. {s}")
        nodes = plan.get("estimated_nodes") or []
        if isinstance(nodes, list) and nodes:
            lines.append(f"\n**Estimated node types:** `{'`, `'.join(str(n) for n in nodes)}`")
        out.append("\n".join(lines))

    # Flowgram diff — pointer to the Skills page (we can't render the
    # canvas inline; the user has to open Skills to review/apply).
    flowgram = response.get("flowgram")
    if isinstance(flowgram, dict) and flowgram:
        nodes = flowgram.get("nodes") or []
        edges = flowgram.get("edges") or []
        n_nodes = len(nodes) if isinstance(nodes, list) else "?"
        n_edges = len(edges) if isinstance(edges, list) else "?"
        out.append(
            "### 🧩 流程图 / Flowgram generated\n\n"
            f"The cloud Skill Editor produced a flowgram with **{n_nodes} nodes** and "
            f"**{n_edges} edges**. Open the **Skills** page to review and apply it.\n\n"
            "*(In-chat preview/apply is not yet supported here — coming in a future "
            "release. For now the canvas on the Skills page is the source of truth.)*"
        )

    # Validation issues — only render if there are problems to surface.
    validation = response.get("validation")
    if isinstance(validation, dict) and validation:
        errors = validation.get("errors") or []
        warnings = validation.get("warnings") or []
        # Skip the section entirely when both lists are empty (which means
        # validation passed cleanly — no need to chatter about it).
        if errors or warnings:
            lines = ["### 🔍 验证结果 / Validation"]
            if errors:
                lines.append("\n**❌ Errors:**")
                for e in errors[:10]:
                    if isinstance(e, dict):
                        nid = str(e.get("node_id") or e.get("nodeId") or "").strip()
                        msg = str(e.get("message") or e.get("error") or "").strip()
                        prefix = f"`{nid}`: " if nid else ""
                        lines.append(f"  - {prefix}{msg}")
                    elif isinstance(e, str):
                        lines.append(f"  - {e}")
                if len(errors) > 10:
                    lines.append(f"  - …and {len(errors) - 10} more")
            if warnings:
                lines.append("\n**⚠️ Warnings:**")
                for w in warnings[:10]:
                    if isinstance(w, dict):
                        nid = str(w.get("node_id") or w.get("nodeId") or "").strip()
                        msg = str(w.get("message") or w.get("warning") or "").strip()
                        prefix = f"`{nid}`: " if nid else ""
                        lines.append(f"  - {prefix}{msg}")
                    elif isinstance(w, str):
                        lines.append(f"  - {w}")
                if len(warnings) > 10:
                    lines.append(f"  - …and {len(warnings) - 10} more")
            out.append("\n".join(lines))

    return out


# ─── hand_off_to_skill_editor — full transfer to the Skills page ───────────
#
# ``consult_skill_editor`` is for one-shot questions ("what does pend_event
# do?") — the answer lands inline in the helper chat.  ``hand_off_to_skill_editor``
# is for multi-turn work — creating a new skill, modifying an existing one,
# analyzing logs — where the user needs the full Skills-page UX (canvas,
# clarification cards, plan review, flowgram apply, validation chips).
#
# Mechanism: the tool returns a chat-message-shaped payload prefixed with
# ``HANDOFF_MARKER``.  Frontend ``ChatDetail.MessageRenderer`` intercepts
# the marker, stashes the inner payload into sessionStorage under a
# well-known key, then routes to ``/skills``.  The Skills page reads
# that sessionStorage entry on mount and seeds its chat input.

import base64 as _base64
import json as _json
import urllib.parse as _urlparse


def _encode_handoff_payload(payload: Dict[str, Any]) -> str:
    """Compact, URL-safe encoding for the handoff message.

    JSON → UTF-8 → base64-urlsafe so the payload survives the
    ``[HandoffToSkillEditor] <body>`` text-channel round-trip without
    quoting issues (chat infrastructure occasionally re-escapes JSON
    strings, but a base64 token is opaque to it).
    """
    raw = _json.dumps(payload, ensure_ascii=False)
    return _base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def get_hand_off_to_skill_editor_tool_schema() -> types.Tool:
    """MCP schema for the helper -> Skills-page handoff tool.

    Description spells out the consult-vs-handoff distinction so the LLM
    picks the right tool. Aligned with the basic_chatter system prompt's
    MANDATORY FIRST CHECK block.
    """
    return types.Tool(
        name="hand_off_to_skill_editor",
        description=(
            "TRANSFER the conversation to the cloud Skills page so the "
            "user can continue with the full Skill Editor UX (canvas, "
            "clarification cards, plan review, flowgram apply, "
            "validation). Call this — INSTEAD of consult_skill_editor — "
            "whenever the user wants a MULTI-TURN workflow: creating a "
            "new skill, modifying an existing skill, or doing in-depth "
            "log analysis. Examples that should trigger handoff: "
            "'create a new skill that …', 'modify the order-sync "
            "skill', 'help me debug why this skill stalls', 'analyze "
            "this log file and find the root cause'. Use "
            "consult_skill_editor instead for one-shot questions you "
            "can answer in a single bubble ('what does pend_event do?'). "
            "Pass the user's question verbatim; the Skills page will "
            "open and seed its chat input with the message so the user "
            "can hit Send (or edit first)."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["user_message"],
                    "properties": {
                        "user_message": {
                            "type": "string",
                            "description": (
                                "The user's request, verbatim or "
                                "lightly cleaned up. This is what gets "
                                "seeded into the Skills-page chat."
                            ),
                        },
                        "intent": {
                            "type": "string",
                            "description": (
                                "Optional one-word category for "
                                "telemetry: 'create' | 'modify' | "
                                "'debug' | 'analyze_logs' | 'other'."
                            ),
                        },
                        "auto_send": {
                            "type": "boolean",
                            "description": (
                                "If true, the Skills page will "
                                "auto-send the seeded message on "
                                "arrival. If false (default), the "
                                "message is only prefilled into the "
                                "input box so the user can review/edit "
                                "before clicking Send."
                            ),
                        },
                    },
                },
            },
        },
    )


async def async_hand_off_to_skill_editor(mainwin: Any, args: Dict[str, Any]) -> List[Any]:
    """Body of ``hand_off_to_skill_editor``.

    Returns a chat-message-shaped text whose first line is
    ``HANDOFF_MARKER <base64-urlsafe-json-payload>``.  ``ChatDetail``'s
    ``MessageRenderer`` parses that line, stashes the payload, and
    navigates to ``/skills``. The body that follows the marker is what
    the user sees as a "Transferring to Skill Editor…" bubble while the
    navigation happens.
    """
    from mcp.types import TextContent

    # Tolerate both wrapped ({"input": {...}}) and flat shapes — same
    # convention as the consult tool above.
    _payload = args.get("input") if isinstance(args, dict) else None
    if not isinstance(_payload, dict):
        _payload = args if isinstance(args, dict) else {}
    user_message = str(_payload.get("user_message") or "").strip()
    intent = str(_payload.get("intent") or "other").strip().lower() or "other"
    auto_send = bool(_payload.get("auto_send"))

    if not user_message:
        return [TextContent(
            type="text",
            text=(
                f"{HANDOFF_MARKER} (no user message provided)\n\n"
                "↗ I tried to transfer you to the Skill Editor but the "
                "message was empty. Could you re-state what you'd like "
                "to do?"
            ),
        )]

    handoff_payload = {
        "user_message": user_message,
        "intent": intent,
        "auto_send": auto_send,
        # Tag the payload with a timestamp so the Skills page can
        # discard stale entries (e.g. if the user navigates manually
        # later and an old seed is still in sessionStorage).
        "ts_ms": int(__import__("time").time() * 1000),
    }
    encoded = _encode_handoff_payload(handoff_payload)

    # Human-readable body that the chat UI shows while/before navigating.
    # The frontend will render this with a "transferring" badge in place
    # of the marker line.
    body = (
        f"↗ 正在转交给 Skill Editor — 即将打开 Skills 页面...\n\n"
        f"*Transferring to Skill Editor — opening the Skills page now...*"
    )
    if intent in ("create", "modify", "debug", "analyze_logs"):
        intent_human = {
            "create": "创建新技能 / Creating a new skill",
            "modify": "修改技能 / Modifying a skill",
            "debug": "调试技能 / Debugging a skill",
            "analyze_logs": "日志分析 / Analyzing logs",
        }[intent]
        body = f"↗ {intent_human}\n\n{body}"

    return [TextContent(
        type="text",
        text=f"{HANDOFF_MARKER} {encoded}\n\n{body}",
    )]
