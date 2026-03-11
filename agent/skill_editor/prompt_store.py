"""
Prompt Store - loads skill-editor sub-agent prompts with a 2-tier fallback:

    1. Local .md files  (prompts/ directory - version-controlled, always fresh)
    2. Caller-supplied default string  (inline Python constant - last resort)

Usage
-----
    from agent.skill_editor.prompt_store import prompt_store

    # Simple - .md file -> None
    text = prompt_store.get("planner")

    # With inline fallback - .md file -> PLANNER_SYSTEM_PROMPT
    text = prompt_store.get("planner", default=PLANNER_SYSTEM_PROMPT)
"""

from __future__ import annotations

import logging
import os
import re
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
# Prompt-ID → .md filename mapping
# ---------------------------------------------------------------------------

# Maps each prompt_id to its corresponding .md file under prompts/.
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
# Public API
# ---------------------------------------------------------------------------


class PromptStore:
    """Prompt loader backed by .md files → inline defaults."""

    def get(self, prompt_id: str, *, default: Optional[str] = None) -> Optional[str]:
        """Return the prompt text for *prompt_id*.

        Fallback order:
          1. Local .md file from prompts/ directory
          2. Caller-supplied *default* string
        """
        # 1. File-based (.md files)
        file_text = _load_prompt_file(prompt_id)
        if file_text:
            return file_text

        # 2. Caller-supplied inline default
        return default

    def get_domain_qa(self) -> str:
        """Return concatenated domain Q&A content from prompts/qa/*.md."""
        return _load_qa_files()

    def get_sop(self) -> str:
        """Return concatenated SOP content from prompts/sop/*.md."""
        return _load_sop_files()

    def get_taxonomy(self) -> str:
        """Return the prompt categorization taxonomy (promptCategorizationTaxonomy.md)."""
        return _load_taxonomy()

    def get_domain_qa_for(self, domain: str) -> str:
        """Return Q&A content for a specific domain (e.g. 'customer_support')."""
        return _load_qa_for_domain(domain)

    def get_sop_for(self, domain: str) -> str:
        """Return SOP content matching a specific domain."""
        return _load_sop_for_domain(domain)

    def get_node_schema(self) -> str:
        """Return the full node schema reference (SKILL_EDITOR_NODE_SCHEMA.md)."""
        return _load_node_schema()

    def get_mapping_dsl(self) -> str:
        """Return the Mapping DSL reference (mapping-dsl.md)."""
        return _load_mapping_dsl()


# Module-level singleton
prompt_store = PromptStore()
