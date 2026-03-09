"""
Prompt Store – loads skill-editor sub-agent prompts with a 3-tier fallback:

    1. DynamoDB  (Agent_Prompts table – hot-swappable, no redeploy)
    2. Local .md files  (prompts/ directory – version-controlled, always fresh)
    3. Caller-supplied default string  (inline Python constant – last resort)

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

    # Simple – DynamoDB → .md file → None
    text = prompt_store.get("planner")

    # With inline fallback – DynamoDB → .md file → PLANNER_SYSTEM_PROMPT
    text = prompt_store.get("planner", default=PLANNER_SYSTEM_PROMPT)

The store falls back through the tiers if:
  • the table does not exist / is unreachable, or
  • no item with the given prompt_id is found.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from utils.logger_helper import logger_helper as logger


# ---------------------------------------------------------------------------
# Safe template substitution
# ---------------------------------------------------------------------------

def safe_format(template: str, **kwargs) -> str:
    """Substitute only *known* ``{key}`` placeholders, leaving all other
    braces (e.g. JSON examples inside Markdown) untouched.

    Unlike ``str.format()``, this function will **not** raise on unknown
    placeholders or on literal ``{`` / ``}`` characters.

    Usage::

        safe_format(prompt_text, node_types=desc, canvas_context=ctx)
    """
    if not kwargs:
        return template
    # Build a pattern that matches only the variable names we were given.
    keys_pattern = "|".join(re.escape(k) for k in kwargs)
    return re.sub(
        r"\{(" + keys_pattern + r")\}",
        lambda m: str(kwargs[m.group(1)]),
        template,
    )

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
# Prompt-ID → .md filename mapping
# ---------------------------------------------------------------------------

# Maps each DynamoDB prompt_id to its corresponding .md file under prompts/.
# This allows the store to fall back to version-controlled .md files when
# DynamoDB is unavailable or the row hasn't been seeded yet.
_PROMPT_FILE_MAP: Dict[str, str] = {
    "intent_classifier":        "skill_agent_main_prompt.md",
    "main_orchestrator":        "skill_agent_main_prompt.md",
    "planner":                  "skill_agent_planner_prompt.md",
    "code_gen":                 "skill_agent_coder_prompt.md",
    "edit_flowgram":            "skill_agent_editor_prompt.md",
    "validator":                "skill_agent_validator_prompt.md",
    "requirement_collector":    "skill_agent_requirement_collector_prompt.md",
    "testor":                   "skill_agent_testor_prompt.md",
    "log_analysis_orchestrator": "skill_agent_log_analysis_orchestrator_prompt.md",
    "log_parser":               "skill_agent_log_parser_prompt.md",
    "flowgram_correlator":      "skill_agent_log_skill_correlator_prompt.md",
    "root_cause_analyzer":      "skill_agent_log_cause_analyzer.md",
}

# Directory containing the .md prompt files (relative to this module).
# Resolved lazily so it works both in the repo and inside a Lambda zip.
_PROMPTS_DIR: Optional[Path] = None


def _get_prompts_dir() -> Path:
    """Locate the prompts/ directory relative to this file."""
    global _PROMPTS_DIR
    if _PROMPTS_DIR is not None:
        return _PROMPTS_DIR

    # Two candidate locations:
    #   1. Repo layout:   agent/skill_editor/prompt_store.py
    #      prompts at:    lambda_functions/skill_editor_lambda/prompts/
    #   2. Lambda zip:    agent/skill_editor/prompt_store.py
    #      prompts at:    prompts/  (copied into zip root during build)
    here = Path(__file__).resolve().parent  # agent/skill_editor/

    candidates = [
        here / "prompts",                                   # if copied beside agent code
        here.parent.parent / "lambda_functions" / "skill_editor_lambda" / "prompts",  # repo layout
        here.parent.parent / "prompts",                     # Lambda zip layout
        Path(os.environ.get("LAMBDA_TASK_ROOT", "")) / "prompts",  # explicit Lambda root
    ]

    for cand in candidates:
        if cand.is_dir():
            _PROMPTS_DIR = cand
            logger.info("[PromptStore] Prompt files directory: %s", cand)
            return cand

    # Fallback: return first candidate (will just miss on reads)
    _PROMPTS_DIR = candidates[0]
    logger.warning("[PromptStore] Prompt files directory not found, tried: %s", [str(c) for c in candidates])
    return _PROMPTS_DIR


def _load_prompt_file(prompt_id: str) -> Optional[str]:
    """Load a prompt from its .md file.  Returns None if not found."""
    filename = _PROMPT_FILE_MAP.get(prompt_id)
    if not filename:
        return None
    filepath = _get_prompts_dir() / filename
    try:
        text = filepath.read_text(encoding="utf-8").strip()
        if text:
            logger.info(
                "[PromptStore] Loaded prompt_id=%s from file %s (%d chars)",
                prompt_id, filepath.name, len(text),
            )
            return text
    except FileNotFoundError:
        logger.debug("[PromptStore] File not found for prompt_id=%s: %s", prompt_id, filepath)
    except Exception as exc:
        logger.warning("[PromptStore] Failed to read file for prompt_id=%s: %s", prompt_id, exc)
    return None


def _load_qa_files() -> str:
    """Load all QA .md files from prompts/qa/ and concatenate them.

    Returns a combined string suitable for injecting into planner/coder prompts
    as the ``{domain_questions}`` template variable.
    """
    qa_dir = _get_prompts_dir() / "qa"
    if not qa_dir.is_dir():
        return ""
    parts: List[str] = []
    for md_file in sorted(qa_dir.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8").strip()
            if content:
                parts.append(content)
        except Exception:
            pass
    return "\n\n---\n\n".join(parts)


def _load_sop_files() -> str:
    """Load all SOP .md files from prompts/sop/ and concatenate them."""
    sop_dir = _get_prompts_dir() / "sop"
    if not sop_dir.is_dir():
        return ""
    parts: List[str] = []
    for md_file in sorted(sop_dir.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8").strip()
            if content:
                parts.append(content)
        except Exception:
            pass
    return "\n\n---\n\n".join(parts)


def _load_taxonomy() -> str:
    """Load the promptCategorizationTaxonomy.md reference file."""
    filepath = _get_prompts_dir() / "promptCategorizationTaxonomy.md"
    try:
        return filepath.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _load_qa_for_domain(domain: str) -> str:
    """Load the QA .md file for a specific domain (e.g. 'customer_support').

    Returns the file contents if found, otherwise an empty string.
    """
    qa_dir = _get_prompts_dir() / "qa"
    # Try exact match first, then fuzzy
    candidates = [
        qa_dir / f"{domain}.md",
        qa_dir / f"{domain.replace('_', '-')}.md",
    ]
    for filepath in candidates:
        try:
            content = filepath.read_text(encoding="utf-8").strip()
            if content:
                return content
        except Exception:
            pass
    return ""


def _load_sop_for_domain(domain: str) -> str:
    """Load SOP .md files whose name contains the domain keyword.

    For example, domain='product_listing' matches 'product_listing_sop.md'.
    domain='customer_support' would match 'product_return_sop.md' only if we
    broaden the search — so we also check if the SOP filename starts with any
    word from the domain.

    Returns concatenated SOP content if found.
    """
    sop_dir = _get_prompts_dir() / "sop"
    if not sop_dir.is_dir():
        return ""

    # Build a set of matching keywords from the domain name
    domain_words = set(domain.lower().replace("-", "_").split("_"))

    parts: List[str] = []
    for md_file in sorted(sop_dir.glob("*.md")):
        stem = md_file.stem.lower().replace("-", "_")  # e.g. 'product_listing_sop'
        stem_words = set(stem.split("_"))
        # Match if domain name appears in filename OR significant overlap
        if domain.lower() in stem or len(domain_words & stem_words) >= 1:
            try:
                content = md_file.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(content)
            except Exception:
                pass
    return "\n\n---\n\n".join(parts)


def _load_node_schema() -> str:
    """Load the SKILL_EDITOR_NODE_SCHEMA.md reference file."""
    filepath = _get_prompts_dir() / "SKILL_EDITOR_NODE_SCHEMA.md"
    try:
        return filepath.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _load_mapping_dsl() -> str:
    """Load the mapping-dsl.md reference file.

    Describes how data_mapping.json works so agents can generate
    declarative data-movement rules instead of code nodes.
    """
    filepath = _get_prompts_dir() / "mapping-dsl.md"
    try:
        return filepath.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


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
    """Singleton-ish prompt loader backed by DynamoDB → .md files → inline defaults."""

    def get(self, prompt_id: str, *, default: Optional[str] = None) -> Optional[str]:
        """Return the prompt text for *prompt_id*.

        Fallback order:
          1. In-memory cache (if fresh)
          2. DynamoDB Agent_Prompts table
          3. Local .md file from prompts/ directory
          4. Caller-supplied *default* string
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
            # DynamoDB unreachable or table missing – try file fallback.
            logger.warning(
                "[PromptStore] DynamoDB fetch failed for prompt_id=%s: %s",
                prompt_id,
                exc,
            )

        # 3. File-based fallback (.md files)
        file_text = _load_prompt_file(prompt_id)
        if file_text:
            _cache[prompt_id] = _CacheEntry(file_text)
            return file_text

        # 4. Caller-supplied inline default
        if default is not None:
            _cache[prompt_id] = _CacheEntry(default)
        return default

    def get_domain_qa(self) -> str:
        """Return concatenated domain Q&A content from prompts/qa/*.md."""
        cache_key = "__domain_qa__"
        entry = _cache.get(cache_key)
        if entry is not None and entry.is_fresh():
            return entry.value
        text = _load_qa_files()
        if text:
            _cache[cache_key] = _CacheEntry(text)
        return text

    def get_sop(self) -> str:
        """Return concatenated SOP content from prompts/sop/*.md."""
        cache_key = "__sop__"
        entry = _cache.get(cache_key)
        if entry is not None and entry.is_fresh():
            return entry.value
        text = _load_sop_files()
        if text:
            _cache[cache_key] = _CacheEntry(text)
        return text

    def get_taxonomy(self) -> str:
        """Return the prompt categorization taxonomy (promptCategorizationTaxonomy.md)."""
        cache_key = "__taxonomy__"
        entry = _cache.get(cache_key)
        if entry is not None and entry.is_fresh():
            return entry.value
        text = _load_taxonomy()
        if text:
            _cache[cache_key] = _CacheEntry(text)
        return text

    def get_domain_qa_for(self, domain: str) -> str:
        """Return Q&A content for a specific domain (e.g. 'customer_support')."""
        cache_key = f"__domain_qa__{domain}"
        entry = _cache.get(cache_key)
        if entry is not None and entry.is_fresh():
            return entry.value
        text = _load_qa_for_domain(domain)
        if text:
            _cache[cache_key] = _CacheEntry(text)
        return text

    def get_sop_for(self, domain: str) -> str:
        """Return SOP content matching a specific domain."""
        cache_key = f"__sop__{domain}"
        entry = _cache.get(cache_key)
        if entry is not None and entry.is_fresh():
            return entry.value
        text = _load_sop_for_domain(domain)
        if text:
            _cache[cache_key] = _CacheEntry(text)
        return text

    def get_node_schema(self) -> str:
        """Return the full node schema reference (SKILL_EDITOR_NODE_SCHEMA.md)."""
        cache_key = "__node_schema__"
        entry = _cache.get(cache_key)
        if entry is not None and entry.is_fresh():
            return entry.value
        text = _load_node_schema()
        if text:
            _cache[cache_key] = _CacheEntry(text)
        return text

    def get_mapping_dsl(self) -> str:
        """Return the Mapping DSL reference (mapping-dsl.md)."""
        cache_key = "__mapping_dsl__"
        entry = _cache.get(cache_key)
        if entry is not None and entry.is_fresh():
            return entry.value
        text = _load_mapping_dsl()
        if text:
            _cache[cache_key] = _CacheEntry(text)
        return text

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
        for simplicity, but called once at cold-start).

        For each prompt_id the fallback chain is:
          DynamoDB → .md file → defaults dict → skip
        """
        defaults = defaults or {}
        for pid in prompt_ids:
            self.get(pid, default=defaults.get(pid))

    def seed_from_files(self, prompt_ids: Optional[list[str]] = None) -> Dict[str, bool]:
        """Push .md file contents into DynamoDB for the given prompt_ids.

        If *prompt_ids* is None, seeds all prompts in _PROMPT_FILE_MAP.

        Returns a dict of {prompt_id: success_bool}.
        """
        ids = prompt_ids or list(_PROMPT_FILE_MAP.keys())
        results: Dict[str, bool] = {}
        for pid in ids:
            text = _load_prompt_file(pid)
            if text:
                results[pid] = self.put(pid, text)
            else:
                logger.warning("[PromptStore] No file content for prompt_id=%s, skipping seed", pid)
                results[pid] = False
        return results


# Module-level singleton
prompt_store = PromptStore()
