"""LLM-based relevance judge for human-intervention vs bot-reply (mt048B).

Background
----------
mt017/mt036A detects when a human staff member types a reply directly
into Feige's chat thread.  When such a bubble is observed targeting
a question the bot is currently preparing to answer, the existing logic
unconditionally drops the bot's reply (``human_intervention_skip``).

That's correct when the human's text actually answers the customer's
question.  It's WRONG when the human said something off-topic
(greeting, clarification, "let me check"), because then the customer
still has an unanswered question and the bot's well-formed reply was
silently lost.

This module exposes :func:`judge` — a thin one-shot LLM call that
decides "did the human reply answer the customer's question?".  The
caller (``runner._handle_direct_outcome``'s drop check) uses the
verdict to either drop (existing behaviour) or proceed (new for cases
where the human just said hi).

Tunables (env)
--------------
``ECAN_HUMAN_JUDGE_ENABLED`` — ``true``/``1``/``yes``/``on`` (default ``true``).
    Set to anything else to disable the judge entirely.  When disabled,
    the caller falls back to the pre-mt048B unconditional drop.

``ECAN_HUMAN_JUDGE_MODEL`` — model name, default ``gpt-5-mini``.
    A fast cheap judge model is plenty for binary classification.

``ECAN_HUMAN_JUDGE_TIMEOUT_S`` — float, default ``3.0``.
    Hard wall-clock cap on the judge call.  On timeout, judge returns
    ``answered=False`` so the bot reply proceeds (favours visibility
    over silent loss).

``ECAN_HUMAN_JUDGE_MIN_CONFIDENCE`` — float 0-1, default ``0.7``.
    The caller only drops when ``answered=True AND confidence>=this``.
    Lower it to drop more aggressively; raise it to keep the bot's
    reply in marginal cases.

Failure modes
-------------
Any exception inside the judge (LLM client init failed, API error,
malformed JSON response, etc.) is caught and logged; the verdict
defaults to ``answered=False`` so the bot reply proceeds.  This module
must never raise — it's a safety net, not a correctness gate.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("eCan")


@dataclass
class JudgeVerdict:
    """Result of one judge call."""
    answered: bool
    confidence: float
    reason: str
    model: str
    elapsed_ms: int
    error: str = ""  # non-empty when the verdict was forced by an exception


_JUDGE_LLM_CACHE: Optional[object] = None  # ChatOpenAI instance
_JUDGE_LLM_LOCK = threading.Lock()
_JUDGE_LLM_MODEL_KEY: str = ""  # which model the cached instance was built for


_SYSTEM_PROMPT = (
    "You are a strict binary classifier for a Chinese e-commerce customer "
    "service workflow.  A customer asked a question; a human staff member "
    "then typed something.  Decide whether the human's text DIRECTLY "
    "ANSWERS the customer's question (gives substantive info that resolves "
    "what the customer asked), or whether it does NOT answer it "
    "(greeting, acknowledgement, clarification request, off-topic, says "
    "'let me check', etc.).\n\n"
    "Output ONLY a single JSON object with these keys:\n"
    '  "answered": boolean — true iff the human directly answered\n'
    '  "confidence": number 0..1 — how sure you are\n'
    '  "reason": short string in Chinese explaining the decision\n\n'
    "Do NOT include any text outside the JSON object.  Do NOT include "
    "markdown code fences."
)


def _env_bool(name: str, default: bool) -> bool:
    val = (os.getenv(name) or "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    val = (os.getenv(name) or "").strip()
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    val = (os.getenv(name) or "").strip()
    return val or default


def is_enabled() -> bool:
    return _env_bool("ECAN_HUMAN_JUDGE_ENABLED", True)


def get_min_confidence() -> float:
    raw = _env_float("ECAN_HUMAN_JUDGE_MIN_CONFIDENCE", 0.7)
    if raw < 0.0:
        return 0.0
    if raw > 1.0:
        return 1.0
    return raw


def _get_llm(model_name: str):
    """Return a cached ChatOpenAI bound to the API key in the secure store.

    Cached per model name; rebuilds when the tunable changes between calls.
    """
    global _JUDGE_LLM_CACHE, _JUDGE_LLM_MODEL_KEY
    if _JUDGE_LLM_CACHE is not None and _JUDGE_LLM_MODEL_KEY == model_name:
        return _JUDGE_LLM_CACHE
    with _JUDGE_LLM_LOCK:
        if _JUDGE_LLM_CACHE is not None and _JUDGE_LLM_MODEL_KEY == model_name:
            return _JUDGE_LLM_CACHE
        from langchain_openai import ChatOpenAI
        # 2026-05-27 mt050C — corrected import paths.  mt048B shipped
        # with ``from utils.secure_store`` + ``from utils.user_context``
        # which both ImportError at runtime (the actual module is
        # ``utils.env.secure_store`` and ``get_current_username`` lives
        # there too — see build_node.py:26).  This broke the judge
        # entirely: every invocation returned
        # ``JudgeVerdict(error="llm_init_failed", answered=False)``,
        # which the runner interpreted as "human did NOT answer →
        # allow bot reply through".  Live customer trace 2026-05-27
        # 12:26:11 hit this: human typed "亲亲帮您查询了这个是有的哈"
        # but bot's reply followed 28 s later asking for a product link.
        from utils.env.secure_store import secure_store, get_current_username
        username = get_current_username()
        api_key = secure_store.get("OPENAI_API_KEY", username=username) or ""
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not found in secure store")
        _JUDGE_LLM_CACHE = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            temperature=0.0,  # deterministic classification
        )
        _JUDGE_LLM_MODEL_KEY = model_name
        return _JUDGE_LLM_CACHE


def _parse_verdict(content: str, model: str, elapsed_ms: int) -> JudgeVerdict:
    """Extract the JSON object the system prompt requested.  Tolerates
    leading/trailing whitespace, surrounding ```json fences (some models
    add them despite the instruction), and a wrapping array.
    """
    text = (content or "").strip()
    # Strip code fences if present.
    if text.startswith("```"):
        # Drop first line + last line if it's a fence.
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Find the first { and last } in case the model added prose.
    lb = text.find("{")
    rb = text.rfind("}")
    if lb >= 0 and rb > lb:
        text = text[lb : rb + 1]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"expected object, got {type(parsed).__name__}")
    answered = bool(parsed.get("answered", False))
    raw_conf = parsed.get("confidence", 0.0)
    try:
        confidence = float(raw_conf)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < 0.0:
        confidence = 0.0
    if confidence > 1.0:
        confidence = 1.0
    reason = str(parsed.get("reason", "") or "")[:200]
    return JudgeVerdict(
        answered=answered,
        confidence=confidence,
        reason=reason,
        model=model,
        elapsed_ms=elapsed_ms,
    )


def judge(customer_question: str, human_text: str) -> JudgeVerdict:
    """One-shot LLM classification.  Never raises.

    Returns ``answered=False`` on any failure (disabled, empty inputs,
    LLM error, timeout, malformed JSON) so the caller's safe default
    (let the bot reply through) takes effect.
    """
    t0 = time.monotonic()
    model = _env_str("ECAN_HUMAN_JUDGE_MODEL", "gpt-5-mini")

    if not is_enabled():
        return JudgeVerdict(
            answered=False, confidence=0.0,
            reason="judge_disabled_via_env",
            model=model, elapsed_ms=0, error="disabled",
        )
    q = (customer_question or "").strip()
    h = (human_text or "").strip()
    if not q or not h:
        return JudgeVerdict(
            answered=False, confidence=0.0,
            reason="empty_input",
            model=model, elapsed_ms=int((time.monotonic() - t0) * 1000),
            error="empty_input",
        )

    timeout_s = _env_float("ECAN_HUMAN_JUDGE_TIMEOUT_S", 3.0)
    user_prompt = (
        f"客户的问题：{q}\n"
        f"人工客服刚才输入：{h}\n\n"
        "请按系统指令输出 JSON。"
    )

    try:
        llm = _get_llm(model)
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            f"[mt048B] judge LLM init failed (model={model!r}): {e} — "
            "defaulting to answered=False (bot reply will proceed)"
        )
        return JudgeVerdict(
            answered=False, confidence=0.0,
            reason="llm_init_failed",
            model=model, elapsed_ms=elapsed_ms, error=str(e),
        )

    try:
        # Use ChatOpenAI's invoke with a per-call timeout.  The langchain
        # client doesn't honour kwarg `timeout` everywhere, but the
        # underlying httpx client does via the constructor.  As a safety
        # net we also cap the overall call duration ourselves.
        from langchain_core.messages import SystemMessage, HumanMessage
        deadline_at = time.monotonic() + timeout_s
        result = llm.invoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_prompt)],
            config={"max_concurrency": 1},
        )
        if time.monotonic() > deadline_at:
            # Came back AFTER our deadline; still return what we got but
            # log so ops can tune the timeout.
            logger.info(
                f"[mt048B] judge LLM response arrived after timeout cap "
                f"({timeout_s}s); using it anyway"
            )
        content = getattr(result, "content", "") or ""
        elapsed_ms = int((time.monotonic() - t0) * 1000)
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            f"[mt048B] judge LLM invoke failed (model={model!r}, "
            f"elapsed_ms={elapsed_ms}): {e} — defaulting to answered=False"
        )
        return JudgeVerdict(
            answered=False, confidence=0.0,
            reason="llm_invoke_failed",
            model=model, elapsed_ms=elapsed_ms, error=str(e),
        )

    try:
        verdict = _parse_verdict(content, model, elapsed_ms)
    except Exception as e:
        logger.warning(
            f"[mt048B] judge response parse failed (content={content[:200]!r}): "
            f"{e} — defaulting to answered=False"
        )
        return JudgeVerdict(
            answered=False, confidence=0.0,
            reason="parse_failed",
            model=model, elapsed_ms=elapsed_ms, error=str(e),
        )

    logger.info(
        f"[mt048B] judge verdict: answered={verdict.answered} "
        f"confidence={verdict.confidence:.2f} model={model!r} "
        f"elapsed_ms={elapsed_ms} reason={verdict.reason!r}"
    )
    return verdict


def reset_llm_cache() -> None:
    """Test helper: drop the cached LLM so the next call re-reads env vars."""
    global _JUDGE_LLM_CACHE, _JUDGE_LLM_MODEL_KEY
    with _JUDGE_LLM_LOCK:
        _JUDGE_LLM_CACHE = None
        _JUDGE_LLM_MODEL_KEY = ""


__all__ = [
    "JudgeVerdict",
    "is_enabled",
    "get_min_confidence",
    "judge",
    "reset_llm_cache",
]
