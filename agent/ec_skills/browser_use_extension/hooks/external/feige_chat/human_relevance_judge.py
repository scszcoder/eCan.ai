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

# CN builds name the app logger "eCan.cn" (propagate=False) — a bare
# getLogger("eCan") record never reaches its handlers, silencing this
# module's entire log output in packaged CN apps (v0.9.95u incident:
# the WS reader looked dead because none of its lines could land).
from utils.logger_helper import logger_helper as logger


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


# 2026-05-27 mt050I — heuristic fast-path.  Most "human did NOT answer"
# cases are short greetings / acknowledgements / holding phrases that
# a regex check classifies instantly without an LLM call.  Live trace
# 2026-05-27 15:36:35: customer typed "嗯嗯" → mt048B judge invoke
# took 129.7 s (timed out, mt050D dropped bot reply).  Skipping the
# LLM for these cases avoids both the latency and the timeout risk.
#
# Match policy:
#   * Trim whitespace, normalise to lowercase
#   * If the message equals or starts with one of these prefixes
#     AND total length <= 8 chars (Chinese), classify as NOT-answer
#     with high confidence (judge result: answered=False, confidence
#     0.95).  Length cap keeps "在的，没货" (which IS an answer) from
#     getting mis-classified just because it starts with "在的".
_NON_ANSWER_FAST_PATH_PREFIXES = (
    "嗯", "嗯嗯", "哦", "好", "好的", "好嘞", "好滴",
    "在", "在的", "在呢", "稍等", "请稍等", "稍微等", "等一下", "等等",
    "马上", "马上回", "马上来", "查一下", "我查查", "查询中",
    "收到", "明白", "知道了", "ok", "okay", "嗯哼",
    "亲", "亲亲", "您好", "你好",
)
_NON_ANSWER_FAST_PATH_MAX_CHARS = 8


def _heuristic_non_answer(human_text: str) -> bool:
    """Return True when *human_text* is an obvious non-answer that the
    LLM judge would (almost certainly) classify as ``answered=False``.

    Conservative — only short ack-style strings trigger this.  Anything
    with substantive content (>8 chars OR not starting with an ack
    phrase) falls through to the LLM judge.
    """
    s = (human_text or "").strip().lower()
    if not s or len(s) > _NON_ANSWER_FAST_PATH_MAX_CHARS:
        return False
    for prefix in _NON_ANSWER_FAST_PATH_PREFIXES:
        if s == prefix or s.startswith(prefix):
            return True
    return False


def judge(customer_question: str, human_text: str) -> JudgeVerdict:
    """One-shot LLM classification.  Never raises.

    Returns ``answered=False`` on any failure (disabled, empty inputs,
    LLM error, timeout, malformed JSON) so the caller's safe default
    (let the bot reply through) takes effect.

    2026-05-27 mt050I — short ack-style ``human_text`` is classified
    by the heuristic fast-path WITHOUT calling the LLM.  Eliminates
    the timeout-then-drop cascade observed when the LLM was slow.
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

    # mt050I heuristic fast-path — bypass the LLM for obvious non-answers.
    if _heuristic_non_answer(h):
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            f"[mt048B] heuristic fast-path: human_text={h[:30]!r} "
            f"classified as non-answer (mt050I) elapsed_ms={elapsed_ms}"
        )
        return JudgeVerdict(
            answered=False,
            confidence=0.95,
            reason="mt050I_heuristic_non_answer",
            model=model + "+heuristic",
            elapsed_ms=elapsed_ms,
            error="",  # NOT an error — clean classification
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

    # 2026-05-27 mt050I — REAL timeout enforcement.  ``llm.invoke`` is
    # sync, so previous "deadline_at vs time.monotonic()" check was
    # advisory only.  Live trace 2026-05-27 15:36 saw a single invoke
    # block for 129.7 s while the 3.0 s timeout was logged but ignored,
    # then mt050D's drop-on-failure dropped a bot reply we shouldn't
    # have dropped.  Now: run the invoke in a thread, wait at most
    # ``timeout_s``, cancel the future on timeout.
    import concurrent.futures as _cf
    try:
        from langchain_core.messages import SystemMessage, HumanMessage

        def _do_invoke():
            return llm.invoke(
                [
                    SystemMessage(content=_SYSTEM_PROMPT),
                    HumanMessage(content=user_prompt),
                ],
                config={"max_concurrency": 1},
            )

        # Dedicated single-shot thread so the cancel actually frees the
        # slot.  We intentionally don't share a thread pool — keeps
        # judge concurrency naturally bounded by the caller.
        with _cf.ThreadPoolExecutor(max_workers=1) as _ex:
            _fut = _ex.submit(_do_invoke)
            try:
                result = _fut.result(timeout=timeout_s)
            except _cf.TimeoutError:
                # Best-effort cancel; if the call already left for the
                # network it'll keep running in the background until the
                # underlying httpx times out.  That's fine — we've
                # returned a verdict to the caller already.
                _fut.cancel()
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                logger.warning(
                    f"[mt048B] judge LLM timed out after {timeout_s}s "
                    f"(model={model!r}, elapsed_ms={elapsed_ms}) — "
                    f"defaulting to answered=False (mt050I real timeout)"
                )
                return JudgeVerdict(
                    answered=False, confidence=0.0,
                    reason="llm_invoke_timeout",
                    model=model, elapsed_ms=elapsed_ms,
                    error=f"timeout after {timeout_s}s",
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


async def judge_async(
    customer_text: str,
    human_reply_text: str,
    *,
    timeout_s: float | None = None,
    model: str | None = None,
) -> "JudgeVerdict":
    """mt054A (2026-05-31): true-async sibling of :func:`judge`.

    Background: ``judge`` runs ``llm.invoke`` inside a thread pool and
    blocks the calling thread on ``_fut.result(timeout=timeout_s)``.
    When called from async code (which is how the only production
    caller at ``runner.py:4820`` uses it), this BLOCKS THE EVENT LOOP
    for up to ``timeout_s`` (default 3 s) plus ThreadPoolExecutor
    shutdown wait (which awaits the running thread on `with` exit even
    after cancel).  Live customer trace 2026-05-31 12:02→12:09: a 76 s
    EventMonitor heartbeat gap followed by a 194 s gap, both proving
    the event loop was wedged.  Code comments at lines 317-323 confirm
    a prior 129.7 s judge invoke blocking the loop.

    The blocked event loop causes CDP WebSocket keepalive ping misses
    → Chrome closes the connection with code 1011 → SessionManager
    clears all owned data → reconnect storm → mt053K's recovery has to
    fire repeatedly to keep things running.  Switching judge to true
    async (``await llm.ainvoke`` wrapped in ``asyncio.wait_for``) lets
    the event loop process other work (WebSocket pings, EventMonitor
    heartbeats, other dispatches) while the LLM HTTP request is
    in-flight.

    Behaviour is otherwise identical to ``judge``; uses the same prompt
    template, parser, and JudgeVerdict shape.  Old ``judge`` retained
    for non-async callers / tests.
    """
    import asyncio
    if model is None:
        model = _judge_model()
    if timeout_s is None:
        timeout_s = _judge_timeout_s()
    t0 = time.monotonic()
    user_prompt = (
        f"## 客户问题\n{customer_text.strip() or '(空)'}\n\n"
        f"## 人工最近一条消息\n{human_reply_text.strip() or '(空)'}\n\n"
        "请按系统指令输出 JSON。"
    )
    try:
        llm = _get_llm(model)
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            f"[mt054A] judge_async LLM init failed (model={model!r}): {e} — "
            "defaulting to answered=False"
        )
        return JudgeVerdict(
            answered=False, confidence=0.0,
            reason="llm_init_failed",
            model=model, elapsed_ms=elapsed_ms, error=str(e),
        )
    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        # ainvoke is non-blocking — it awaits HTTP I/O via async stack
        # so the event loop keeps servicing CDP ping/pong, EventMonitor
        # heartbeats, and other dispatch work concurrently.
        result = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(content=_SYSTEM_PROMPT),
                    HumanMessage(content=user_prompt),
                ],
                config={"max_concurrency": 1},
            ),
            timeout=timeout_s,
        )
        content = getattr(result, "content", "") or ""
        elapsed_ms = int((time.monotonic() - t0) * 1000)
    except asyncio.TimeoutError:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            f"[mt054A] judge_async LLM timed out after {timeout_s}s "
            f"(model={model!r}, elapsed_ms={elapsed_ms}) — "
            f"defaulting to answered=False"
        )
        return JudgeVerdict(
            answered=False, confidence=0.0,
            reason="llm_invoke_timeout",
            model=model, elapsed_ms=elapsed_ms,
            error=f"timeout after {timeout_s}s",
        )
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            f"[mt054A] judge_async LLM invoke failed (model={model!r}, "
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
            f"[mt054A] judge_async response parse failed "
            f"(content={content[:200]!r}): {e} — defaulting to answered=False"
        )
        return JudgeVerdict(
            answered=False, confidence=0.0,
            reason="parse_failed",
            model=model, elapsed_ms=elapsed_ms, error=str(e),
        )
    logger.info(
        f"[mt054A] judge_async verdict: answered={verdict.answered} "
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
