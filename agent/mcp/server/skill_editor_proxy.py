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
            "Forward the user's question to the cloud-based Skill Editor "
            "agent and return its reply. Call this when the user asks "
            "about: creating a new skill / flowgram, modifying an "
            "existing skill, debugging a skill that isn't working, "
            "explaining what a node does, OR analyzing logs / runtime "
            "behavior. The cloud agent has full access to the user's "
            "skills, flowgrams, and skill-editor tools (canvas ops, "
            "validation, plan generation). It may return a clarifying "
            "question, an implementation plan, a flowgram diff, or a "
            "regular text answer. Pass the user's question verbatim "
            "(plus relevant context like which skill name they're "
            "asking about). DO NOT use this for ordinary chitchat or "
            "questions you can answer directly."
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

    # Append structured-artifact hints so the local LLM knows what's
    # available in the cloud-side editor (flowgram diff to apply,
    # clarification questions awaiting an answer, validation issues).
    artifact_lines = []
    if response.get("clarification"):
        artifact_lines.append(
            "  • The cloud agent has clarification questions — relay them to the user and reply via consult_skill_editor again."
        )
    if response.get("plan"):
        artifact_lines.append(
            "  • The cloud agent produced an implementation plan — summarize the key steps for the user."
        )
    if response.get("flowgram"):
        artifact_lines.append(
            "  • The cloud agent generated/edited a flowgram — tell the user to open the Skills page to review/apply."
        )
    if response.get("validation"):
        artifact_lines.append(
            "  • The cloud agent ran validation — surface any errors or warnings."
        )

    suffix = ("\n\n" + "\n".join(artifact_lines)) if artifact_lines else ""
    return [TextContent(
        type="text",
        text=f"{BADGE_MARKER} {assistant_text}{suffix}",
    )]
