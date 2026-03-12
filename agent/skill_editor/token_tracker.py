"""
Token Tracker — lightweight per-request accumulator for LLM token usage.

Records input/output token counts from every LLM call during a single
Lambda invocation and flushes a summary to S3 at the end.

S3 layout
---------
    s3://skill-editor-agent/<yyyymmdd>/tokens_<hhmmssmsmsms>

Each file is a JSON object with per-call entries plus a totals section.

Usage
-----
    from agent.skill_editor.token_tracker import token_tracker

    # After every LLM call, record usage from the AIMessage:
    token_tracker.record(response, agent="CodeAgent", action="generate")

    # At the end of the Lambda handler:
    token_tracker.flush_to_s3(owner="user@example.com", session_id="sess-123")
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_S3_BUCKET = os.environ.get("TOKEN_TRACKER_BUCKET", "skill-editor-agent")


class TokenTracker:
    """Thread-local-safe token accumulator (Lambda runs single-threaded)."""

    def __init__(self) -> None:
        self.reset()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        response: Any,
        *,
        agent: str = "",
        action: str = "",
        model: str = "",
    ) -> None:
        """Extract token counts from a LangChain ``AIMessage`` and append an entry.

        Works with ``langchain_openai.ChatOpenAI`` responses which expose
        ``usage_metadata`` (preferred) or ``response_metadata.token_usage``.
        """
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        model_name = model

        # --- Try usage_metadata first (langchain-core ≥ 0.2) ---------
        usage = getattr(response, "usage_metadata", None)
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", 0) or 0
            output_tokens = usage.get("output_tokens", 0) or 0
            total_tokens = usage.get("total_tokens", 0) or (input_tokens + output_tokens)

        # --- Fallback to response_metadata.token_usage ----------------
        if total_tokens == 0:
            resp_meta = getattr(response, "response_metadata", None) or {}
            token_usage = resp_meta.get("token_usage") or resp_meta.get("usage") or {}
            if isinstance(token_usage, dict):
                input_tokens = token_usage.get("prompt_tokens", 0) or token_usage.get("input_tokens", 0) or 0
                output_tokens = token_usage.get("completion_tokens", 0) or token_usage.get("output_tokens", 0) or 0
                total_tokens = token_usage.get("total_tokens", 0) or (input_tokens + output_tokens)
            if not model_name:
                model_name = resp_meta.get("model_name", "") or resp_meta.get("model", "")

        entry: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "action": action,
            "model": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
        self._entries.append(entry)
        self._total_input += input_tokens
        self._total_output += output_tokens
        self._total += total_tokens

        logger.info(
            "[TokenTracker] %s.%s  in=%d  out=%d  total=%d  (cumulative: %d)",
            agent, action, input_tokens, output_tokens, total_tokens, self._total,
        )

    def flush_to_s3(
        self,
        *,
        owner: str = "",
        session_id: str = "",
        request_summary: str = "",
    ) -> Optional[str]:
        """Write accumulated entries to S3 and reset.

        Returns the S3 key on success, ``None`` on failure / nothing to flush.
        """
        if not self._entries:
            logger.debug("[TokenTracker] Nothing to flush.")
            return None

        now = datetime.now(timezone.utc)
        date_dir = now.strftime("%Y%m%d")
        # tokens_hhmmssmsmsms  →  ms = milliseconds (3 digits), msms = microseconds (6 digits)
        # Using microseconds for uniqueness:  hhmmss + 6-digit microseconds
        file_name = f"tokens_{now.strftime('%H%M%S')}{now.strftime('%f')}"

        s3_key = f"{date_dir}/{file_name}"

        payload: Dict[str, Any] = {
            "owner": owner,
            "session_id": session_id,
            "request_summary": request_summary[:200] if request_summary else "",
            "lambda_start": self._start_iso,
            "flush_time": now.isoformat(),
            "elapsed_seconds": round(time.monotonic() - self._start_mono, 2),
            "totals": {
                "input_tokens": self._total_input,
                "output_tokens": self._total_output,
                "total_tokens": self._total,
                "llm_calls": len(self._entries),
            },
            "entries": self._entries,
        }

        try:
            import boto3
            s3 = boto3.client("s3")
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            s3.put_object(
                Bucket=_S3_BUCKET,
                Key=s3_key,
                Body=body,
                ContentType="application/json",
            )
            logger.info(
                "[TokenTracker] Flushed %d entries (%d total tokens) → s3://%s/%s",
                len(self._entries), self._total, _S3_BUCKET, s3_key,
            )
            self.reset()
            return s3_key
        except Exception as exc:
            logger.warning("[TokenTracker] Failed to flush to S3: %s", exc)
            return None

    def reset(self) -> None:
        """Clear all accumulated data (called automatically after flush)."""
        self._entries: List[Dict[str, Any]] = []
        self._total_input: int = 0
        self._total_output: int = 0
        self._total: int = 0
        self._start_mono: float = time.monotonic()
        self._start_iso: str = datetime.now(timezone.utc).isoformat()

    # Convenience properties
    @property
    def total_input(self) -> int:
        return self._total_input

    @property
    def total_output(self) -> int:
        return self._total_output

    @property
    def total(self) -> int:
        return self._total

    @property
    def call_count(self) -> int:
        return len(self._entries)


# Module-level singleton — shared across all agents within a single invocation.
token_tracker = TokenTracker()
