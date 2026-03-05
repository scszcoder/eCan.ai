"""
Prompt Store – loads skill-editor sub-agent prompts from the existing
Agent_Prompts DynamoDB table with an in-memory cache so we pay the
DynamoDB cost at most once per cold start.

DynamoDB table: Agent_Prompts  (configurable via env PROMPT_TABLE_NAME)

Existing Schema
---------------
Partition key : owner_id  (S)
Sort key      : agent_id  (S)

For skill-editor system prompts we use:
    owner_id = "system"
    agent_id = "skill_editor~<prompt_id>"
        e.g. "skill_editor~intent_classifier", "skill_editor~planner",
             "skill_editor~code_gen", "skill_editor~edit_flowgram",
             "skill_editor~validator"

The prompt text is stored in the `prompt` attribute (S).

Usage
-----
    from agent.skill_editor.prompt_store import prompt_store
    text = prompt_store.get("planner", default=PLANNER_SYSTEM_PROMPT)

The store falls back to the caller-supplied default if:
  • the table does not exist / is unreachable, or
  • no item with the given prompt_id is found.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Dict, Optional

from utils.logger_helper import logger_helper as logger

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TABLE_NAME = os.environ.get("PROMPT_TABLE_NAME", "Agent_Prompts")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# owner_id used for all skill-editor system prompts
SYSTEM_OWNER_ID = os.environ.get("PROMPT_OWNER_ID", "system")

# Prefix added to prompt_id to form the agent_id sort key
AGENT_ID_PREFIX = "skill_editor~"

# How long (seconds) a cached value is considered fresh.  Set to 0 to disable
# TTL (cache lives until Lambda cold-starts again).
CACHE_TTL_SECONDS = int(os.environ.get("PROMPT_CACHE_TTL", "0"))

# ---------------------------------------------------------------------------
# Internal cache
# ---------------------------------------------------------------------------

_cache: Dict[str, "_CacheEntry"] = {}


class _CacheEntry:
    __slots__ = ("value", "fetched_at")

    def __init__(self, value: str):
        self.value = value
        self.fetched_at = time.monotonic()

    def is_fresh(self) -> bool:
        if CACHE_TTL_SECONDS <= 0:
            return True  # never expire
        return (time.monotonic() - self.fetched_at) < CACHE_TTL_SECONDS


# ---------------------------------------------------------------------------
# Lazy boto3 client
# ---------------------------------------------------------------------------

_ddb_client = None


def _get_client():
    global _ddb_client
    if _ddb_client is None:
        import boto3
        _ddb_client = boto3.client("dynamodb", region_name=AWS_REGION)
    return _ddb_client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class PromptStore:
    """Singleton-ish prompt loader backed by DynamoDB."""

    def get(self, prompt_id: str, *, default: Optional[str] = None) -> Optional[str]:
        """Return the prompt text for *prompt_id*.

        Falls back to *default* when DynamoDB is unavailable or the item is
        missing.
        """
        # 1. Check cache
        entry = _cache.get(prompt_id)
        if entry is not None and entry.is_fresh():
            return entry.value

        # 2. Fetch from DynamoDB
        agent_id = f"{AGENT_ID_PREFIX}{prompt_id}"
        try:
            client = _get_client()
            resp = client.get_item(
                TableName=TABLE_NAME,
                Key={
                    "owner_id": {"S": SYSTEM_OWNER_ID},
                    "agent_id": {"S": agent_id},
                },
                ProjectionExpression="prompt",
            )
            item = resp.get("Item")
            if item and "prompt" in item:
                text = item["prompt"].get("S", "")
                if text:
                    _cache[prompt_id] = _CacheEntry(text)
                    logger.info(
                        "[PromptStore] Loaded prompt_id=%s from DynamoDB (%d chars)",
                        prompt_id,
                        len(text),
                    )
                    return text
        except Exception as exc:
            # DynamoDB unreachable or table missing – fall back silently.
            logger.warning(
                "[PromptStore] DynamoDB fetch failed for prompt_id=%s: %s",
                prompt_id,
                exc,
            )

        # 3. Fallback
        if default is not None:
            _cache[prompt_id] = _CacheEntry(default)
        return default

    def put(self, prompt_id: str, prompt_text: str, *, version: str = "1") -> bool:
        """Write a prompt to DynamoDB (convenience for seeding / admin)."""
        import datetime as _dt

        agent_id = f"{AGENT_ID_PREFIX}{prompt_id}"
        try:
            client = _get_client()
            client.put_item(
                TableName=TABLE_NAME,
                Item={
                    "owner_id": {"S": SYSTEM_OWNER_ID},
                    "agent_id": {"S": agent_id},
                    "prompt_id": {"S": prompt_id},
                    "prompt": {"S": prompt_text},
                    "prompt_name": {"S": f"skill_editor_{prompt_id}"},
                    "suitable_modes": {"S": "all"},
                    "metadata": {"S": "{}"},
                    "last_mod_date": {"S": _dt.datetime.utcnow().isoformat() + "Z"},
                },
            )
            _cache[prompt_id] = _CacheEntry(prompt_text)
            logger.info("[PromptStore] Wrote prompt_id=%s (%d chars)", prompt_id, len(prompt_text))
            return True
        except Exception as exc:
            logger.error("[PromptStore] put failed for prompt_id=%s: %s", prompt_id, exc)
            return False

    def invalidate(self, prompt_id: Optional[str] = None) -> None:
        """Clear cache for one prompt or all prompts."""
        if prompt_id:
            _cache.pop(prompt_id, None)
        else:
            _cache.clear()

    def preload(self, prompt_ids: list[str], defaults: Optional[Dict[str, str]] = None) -> None:
        """Bulk-load multiple prompts in one shot (still individual GetItem calls
        for simplicity, but called once at cold-start)."""
        defaults = defaults or {}
        for pid in prompt_ids:
            self.get(pid, default=defaults.get(pid))


# Module-level singleton
prompt_store = PromptStore()
