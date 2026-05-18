"""Prompt-agent chat handler.

Implements the ``prompt_agent_chat`` IPC method backing the prompt-editor
chat panel (gui_v2/src/pages/prompts).  The user types natural-language
requests like "make the role more formal" and the agent returns

  * an ``assistant_message`` — short reply shown in the chat thread, and
  * a ``proposed_md_content`` — the full revised prompt body the user
    can preview-diff and Apply into the prompt editor.

The flow is wrapped in a minimal LangGraph ``StateGraph`` (a single LLM
node) so we can grow it later (multi-step planning, RAG over the user's
own prompt library, etc.) without changing the IPC surface.

Model selection follows the rest of the app: we ask
``llm_manager.get_default_llm_config()`` for the user's configured
default provider, then prefer ``gpt-5.5`` on that provider when the
caller doesn't override.  The same env / config tweak that changes
the rest of the app picks up here automatically.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict
from uuid import uuid4

from gui.ipc.types import IPCRequest, IPCResponse, create_success_response, create_error_response
from gui.ipc.registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger


# Default model preference for the prompt-agent.  Overridable via the
# request payload (``model_name``) or by changing the user's default
# provider in settings.
_DEFAULT_PROMPT_AGENT_MODEL = "gpt-5.5"


# ---------------------------------------------------------------------------
# LangGraph state + nodes
# ---------------------------------------------------------------------------
class _PromptAgentState(TypedDict, total=False):
    user_message: str
    current_md_content: str
    history: List[Dict[str, str]]
    provider_id: str
    model_name: str
    # echoed in for telemetry (token accounting) — not used by the LLM call
    prompt_id: str
    user_email: str
    # populated by the llm node
    assistant_message: str
    proposed_md_content: str
    raw_llm_output: str
    error: str


def _system_instructions() -> str:
    """System prompt that anchors the agent to its narrow job."""
    return (
        "You are a senior prompt-engineering assistant embedded inside the "
        "eCan.ai prompt editor. You help the user iteratively refine an "
        "LLM system-prompt expressed as Markdown with `# Role`, `# Goals`, "
        "`# Guidelines`, `# Instructions`, `# Rules`, `# Exceptions` etc. "
        "sections.\n\n"
        "On every turn you receive:\n"
        "  * the current prompt body (markdown),\n"
        "  * the user's natural-language request describing what to change,\n"
        "  * the recent conversation history.\n\n"
        "You MUST reply with a single JSON object — no prose, no Markdown "
        "fences around it — with exactly these keys:\n"
        '  {\n'
        '    \"assistant_message\": str,  // 1-3 sentences explaining what '
        'you changed (or asking for clarification if the request is '
        'ambiguous)\n'
        '    \"proposed_md_content\": str  // the FULL revised prompt body '
        'in Markdown; preserve untouched sections verbatim. Empty string '
        'iff you are only asking a question (no edit proposed).\n'
        '  }\n'
        "Never invent sections the user did not ask for. Keep existing "
        "section headings and ordering unless explicitly asked to change. "
        "If the user request is too vague to act on, leave "
        "proposed_md_content empty and use assistant_message to ask one "
        "concise clarifying question."
    )


def _resolve_llm(provider_id_hint: str = "", model_name_hint: str = "") -> tuple[Any, str, str]:
    """Return (llm_instance, provider_id, model_name) for the prompt agent.

    Falls back through: caller hints → user's configured default →
    raises a clear error if nothing is configured.
    """
    from gui.ipc.w2p_handlers.llm_handler import get_llm_manager
    mgr = get_llm_manager()
    if mgr is None:
        raise RuntimeError("LLM manager not available; configure a provider in Settings → LLM.")

    default_cfg = mgr.get_default_llm_config() or {}
    provider_id = (provider_id_hint or default_cfg.get("provider_id") or "openai").strip()
    model_name = (model_name_hint or _DEFAULT_PROMPT_AGENT_MODEL).strip() or _DEFAULT_PROMPT_AGENT_MODEL

    provider_dict = mgr.get_provider(provider_id) or default_cfg.get("provider_dict") or {}
    if not provider_dict:
        raise RuntimeError(
            f"Provider {provider_id!r} has no configuration; pick a default LLM in Settings."
        )

    # Build the chat model.  We use the same convention as build_llm_node:
    # langchain_openai.ChatOpenAI for openai-compatible providers (which
    # covers OpenAI, DeepSeek, Qwen and similar), langchain_anthropic for
    # claude.  The prompt agent is small, so we don't try to mirror every
    # provider — fall back to ChatOpenAI when in doubt.
    api_key = provider_dict.get("api_key") or provider_dict.get("apiKey") or ""
    api_base = provider_dict.get("api_base") or provider_dict.get("apiHost") or provider_dict.get("base_url") or ""

    canonical = provider_id.lower()
    if canonical in ("anthropic", "claude"):
        from langchain_anthropic import ChatAnthropic
        kwargs: Dict[str, Any] = {"model": model_name, "temperature": 0.4}
        if api_key:
            kwargs["api_key"] = api_key
        if api_base:
            kwargs["base_url"] = api_base
        return ChatAnthropic(**kwargs), provider_id, model_name

    # Default: OpenAI-compatible.
    from langchain_openai import ChatOpenAI
    kwargs = {"model": model_name, "temperature": 0.4}
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["base_url"] = api_base
    return ChatOpenAI(**kwargs), provider_id, model_name


def _build_graph():
    """Build (and lazily cache) the StateGraph for the prompt agent.

    A single ``llm`` node for now; structured so a future planner /
    critic / library-lookup node can slot in without changing the
    handler signature.
    """
    from langgraph.graph import StateGraph, START, END
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

    def _llm_node(state: _PromptAgentState) -> _PromptAgentState:
        try:
            llm, _pid, _mname = _resolve_llm(
                provider_id_hint=state.get("provider_id", "") or "",
                model_name_hint=state.get("model_name", "") or "",
            )
        except Exception as exc:
            state["error"] = f"LLM init failed: {exc}"
            state["assistant_message"] = (
                "I couldn't reach the LLM provider — check your "
                "Settings → LLM configuration."
            )
            state["proposed_md_content"] = ""
            return state

        # Compose the message list: system + prior history (capped) + current turn.
        messages: List[Any] = [SystemMessage(content=_system_instructions())]
        history = state.get("history") or []
        # Cap history so we don't blow context on a long-running chat.
        for entry in history[-12:]:
            role = (entry.get("role") or "").lower()
            content = entry.get("content") or ""
            if not content:
                continue
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))

        current_md = state.get("current_md_content") or ""
        user_msg = state.get("user_message") or ""
        turn_payload = (
            "## Current prompt body (Markdown)\n\n"
            f"{current_md if current_md.strip() else '(empty)'}\n\n"
            "## User request\n\n"
            f"{user_msg}\n\n"
            "Respond now with the JSON object specified in your system "
            "instructions."
        )
        messages.append(HumanMessage(content=turn_payload))

        try:
            start_dt = datetime.utcnow()
            t0 = time.perf_counter()
            response = llm.invoke(messages)
            elapsed_ms_f = (time.perf_counter() - t0) * 1000.0
            end_dt = datetime.utcnow()
            raw = str(getattr(response, "content", "") or "")
            state["raw_llm_output"] = raw
            logger.info(
                f"[prompt_agent_chat] llm.invoke ok in {elapsed_ms_f:.0f}ms, "
                f"output_len={len(raw)}"
            )

            # ── Token accounting ────────────────────────────────────
            # Route through the shared TokenTracker so this LLM call
            # shows up in the same DB table (`token_usage`) and
            # JSONL ledger (`runlogs/token_usage_bookings.jsonl`) as
            # every other LLM invocation in the app.  source_type
            # gets its own bucket ("prompt_agent_chat") so usage
            # analytics can break it out from skill traffic.
            try:
                from agent.ec_skills.token_tracker import TokenTracker
                TokenTracker().record_llm_usage(
                    response,
                    source_type="prompt_agent_chat",
                    source_id=str(state.get("prompt_id") or "") or None,
                    source_name="prompt-editor agent",
                    user_email=str(state.get("user_email") or "") or None,
                    node_type="llm",
                    start_time=start_dt,
                    end_time=end_dt,
                    duration_ms=int(elapsed_ms_f),
                    skill_name="prompt_agent_chat",
                )
            except Exception as track_err:
                # Never let a tracking failure mask the real reply.
                logger.warning(
                    f"[prompt_agent_chat] token accounting skipped: {track_err}"
                )
        except Exception as exc:
            state["error"] = f"LLM call failed: {exc}"
            state["assistant_message"] = (
                "The LLM call failed; see logs for details."
            )
            state["proposed_md_content"] = ""
            return state

        # Parse the JSON contract.  Be defensive: the model may wrap in ``` fences.
        parsed = _parse_agent_json(raw)
        state["assistant_message"] = str(parsed.get("assistant_message") or "")
        state["proposed_md_content"] = str(parsed.get("proposed_md_content") or "")
        if not state["assistant_message"] and not state["proposed_md_content"]:
            # Fall back to the raw text so the user sees *something*.
            state["assistant_message"] = raw.strip()[:2000] or "(empty response)"
        return state

    graph = StateGraph(_PromptAgentState)
    graph.add_node("llm", _llm_node)
    graph.add_edge(START, "llm")
    graph.add_edge("llm", END)
    return graph.compile()


# Module-level compiled graph cache.  StateGraph compilation is cheap but
# not free, and the handler can fire many times per session.
_GRAPH_CACHE: Dict[str, Any] = {}


def _get_graph():
    g = _GRAPH_CACHE.get("graph")
    if g is None:
        g = _build_graph()
        _GRAPH_CACHE["graph"] = g
    return g


def _parse_agent_json(raw: str) -> Dict[str, str]:
    """Extract the JSON object from the LLM's response.

    Handles both bare JSON and JSON wrapped in ```json fences.
    """
    if not raw:
        return {}
    s = raw.strip()
    # Strip code fences if present.
    if s.startswith("```"):
        # Remove opening fence line.
        nl = s.find("\n")
        if nl >= 0:
            s = s[nl + 1:]
        # Remove trailing closing fence.
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3].rstrip()
    # Try direct parse first.
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # Fall back: find the outermost { ... } block.
    first = s.find("{")
    last = s.rfind("}")
    if first >= 0 and last > first:
        try:
            obj = json.loads(s[first:last + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return {}


# ---------------------------------------------------------------------------
# IPC handler
# ---------------------------------------------------------------------------
@IPCHandlerRegistry.handler('prompt_agent_chat')
def handle_prompt_agent_chat(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """Run one turn of the prompt-agent conversation.

    Expected params:
      {
        "prompt_id": str,              // for logging / persistence keying
        "user_message": str,           // required
        "current_md_content": str,     // current prompt body in markdown
        "history": [                   // optional, prior turns in this thread
          { "role": "user"|"assistant", "content": str }
        ],
        "provider_id": str?,           // optional override
        "model_name": str?             // optional override
      }

    Returns:
      {
        "assistant_message": str,
        "proposed_md_content": str,    // empty when the agent only asks a question
        "raw_llm_output": str,         // verbatim, for debugging
        "model": { "provider_id": str, "model_name": str }
      }
    """
    try:
        params = params or {}
        user_message = str(params.get("user_message") or "").strip()
        if not user_message:
            return create_error_response(request, 'INVALID_PARAMS', 'user_message is required')

        current_md = str(params.get("current_md_content") or "")
        history_raw = params.get("history") or []
        history: List[Dict[str, str]] = []
        if isinstance(history_raw, list):
            for entry in history_raw[-30:]:  # hard cap independent of caller
                if not isinstance(entry, dict):
                    continue
                role = str(entry.get("role") or "").lower()
                if role not in ("user", "assistant"):
                    continue
                content = str(entry.get("content") or "")
                if not content:
                    continue
                history.append({"role": role, "content": content})

        provider_id = str(params.get("provider_id") or "").strip()
        model_name = str(params.get("model_name") or "").strip()

        # Resolve up-front so we can echo back what we actually used
        # (and surface a clean error if the LLM isn't configured at all).
        try:
            _llm, resolved_provider, resolved_model = _resolve_llm(provider_id, model_name)
            del _llm  # we only built it here to validate; the node rebuilds inside.
        except Exception as exc:
            logger.warning(f"[prompt_agent_chat] LLM resolution failed: {exc}")
            return create_error_response(request, 'LLM_NOT_CONFIGURED', str(exc))

        prompt_id = str(params.get("prompt_id") or "")
        # Resolve current user email so the token-usage entry is
        # attributed correctly. Falls back gracefully when unauthenticated
        # (record_llm_usage handles None).
        user_email = ""
        try:
            from gui.ipc.w2p_handlers.skill_handler import get_current_username
            user_email = str(get_current_username() or "") or ""
        except Exception:
            user_email = ""

        logger.info(
            f"[prompt_agent_chat] prompt_id={prompt_id!r} "
            f"provider={resolved_provider} model={resolved_model} "
            f"user={user_email!r} "
            f"history_len={len(history)} md_len={len(current_md)} "
            f"user_msg_len={len(user_message)}"
        )

        graph = _get_graph()
        initial: _PromptAgentState = {
            "user_message": user_message,
            "current_md_content": current_md,
            "history": history,
            "provider_id": resolved_provider,
            "model_name": resolved_model,
            "prompt_id": prompt_id,
            "user_email": user_email,
        }
        result = graph.invoke(initial)

        if result.get("error"):
            return create_error_response(request, 'AGENT_ERROR', result["error"])

        payload = {
            "assistant_message": str(result.get("assistant_message") or ""),
            "proposed_md_content": str(result.get("proposed_md_content") or ""),
            "raw_llm_output": str(result.get("raw_llm_output") or ""),
            "model": {
                "provider_id": resolved_provider,
                "model_name": resolved_model,
            },
        }
        return create_success_response(request, payload)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"[prompt_agent_chat] unexpected error: {exc}")
        import traceback as _tb
        logger.error(_tb.format_exc())
        return create_error_response(request, 'PROMPT_AGENT_CHAT_ERROR', str(exc))
