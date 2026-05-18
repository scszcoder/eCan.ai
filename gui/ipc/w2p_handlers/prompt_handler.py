"""Prompt handlers: IPC persistence for prompt editor."""

from __future__ import annotations

import json
import re
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple
from uuid import uuid4

from gui.ipc.types import IPCRequest, IPCResponse, create_success_response, create_error_response
from gui.ipc.registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger
from utils.user_path_helper import get_user_data_dir
# Cloud sync import - guarded to prevent import failures from breaking IPC
try:
    from gui.ipc.w2p_handlers.prompt_cloud_sync import (
        sync_prompt_to_cloud,
        delete_prompt_from_cloud,
        delete_prompt_from_cloud_sync,
        sync_all_prompts_to_cloud,
        fetch_cloud_prompts,
        invalidate_cloud_prompts_cache,
    )
    _CLOUD_SYNC_AVAILABLE = True
except Exception as _sync_import_err:
    import logging as _logging
    logger.warning(f"[prompts] Cloud sync not available: {_sync_import_err}")
    _CLOUD_SYNC_AVAILABLE = False
    def sync_prompt_to_cloud(*a, **kw): pass
    def delete_prompt_from_cloud(*a, **kw): pass

    def delete_prompt_from_cloud_sync(*a, **kw): return False
    def sync_all_prompts_to_cloud(*a, **kw): pass
    def fetch_cloud_prompts() -> list: return []
    def invalidate_cloud_prompts_cache(*a, **kw): pass

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SYSTEMS_DIR = PROJECT_ROOT / "systems"
# User prompts are stored in user_data directory (production-safe)
MY_PROMPTS_DIR = None  # Will be set dynamically based on current user
SAMPLE_PROMPTS_DIR = PROJECT_ROOT / "resource" / "systems" / "sample_prompts"

def _get_my_prompts_dir() -> Path:
    """Get user-specific prompts directory (production-safe)."""
    global MY_PROMPTS_DIR
    if MY_PROMPTS_DIR is None:
        user_data_dir = get_user_data_dir(subdir="my_prompts")
        MY_PROMPTS_DIR = Path(user_data_dir)
    return MY_PROMPTS_DIR

SECTION_TYPES: Tuple[str, ...] = (
    "role",
    "tone",
    "background",
    "goals",
    "guidelines",
    "rules",
    "instructions",
    "examples",
    "variables",
    "additional",
    "exceptions",
    "extra_attentions",
    "custom",
    "tools_to_use",
)


def _ensure_prompt_dirs() -> None:
    try:
        prompts_dir = _get_my_prompts_dir()
        # Check if directory exists before trying to create
        if not prompts_dir.exists():
            prompts_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"[prompts] Created my_prompts directory: {prompts_dir}")
        else:
            logger.debug(f"[prompts] my_prompts directory already exists: {prompts_dir}")
    except PermissionError as exc:
        logger.error(f"[prompts] Permission denied creating my_prompts directory: {exc}")
        logger.error(f"[prompts] Directory path: {_get_my_prompts_dir()}")
        logger.error(f"[prompts] Parent exists: {_get_my_prompts_dir().parent.exists() if _get_my_prompts_dir().parent else 'N/A'}")
        logger.error(f"[prompts] Parent writable: {os.access(_get_my_prompts_dir().parent, os.W_OK) if _get_my_prompts_dir().parent else False}")
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"[prompts] failed to create my_prompts directory: {exc}")


def _coerce_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        iterable = value
    elif isinstance(value, (set, tuple)):
        iterable = list(value)
    else:
        iterable = [value]
    return ["" if v is None else str(v) for v in iterable]


def _clean_section_items(items: List[str]) -> List[str]:
    cleaned = ["" if item is None else str(item) for item in items]
    return cleaned if cleaned else [""]


def _normalize_sections(raw_sections: Any, legacy_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []

    if isinstance(raw_sections, list) and raw_sections:
        for entry in raw_sections:
            if not isinstance(entry, dict):
                continue
            sec_type = str(entry.get("type") or "").strip().lower()
            if sec_type not in SECTION_TYPES:
                continue
            sec_id = str(entry.get("id") or uuid4().hex)
            items = entry.get("items", [])
            if not isinstance(items, list):
                items = [items]
            section_data = {
                "id": sec_id,
                "type": sec_type,
                "items": _clean_section_items(items),
            }
            # Preserve customLabel for custom sections
            if sec_type == "custom" and "customLabel" in entry:
                section_data["customLabel"] = str(entry["customLabel"])
            sections.append(section_data)
        if sections:
            return sections

    # Legacy format fallback
    legacy_map: List[Tuple[str, Any]] = [
        ("background", legacy_data.get("roleToneContext")),
        ("goals", legacy_data.get("goals")),
        ("guidelines", legacy_data.get("guidelines")),
        ("rules", legacy_data.get("rules")),
        ("instructions", legacy_data.get("instructions")),
        ("variables", legacy_data.get("sysInputs")),
        ("examples", legacy_data.get("examples")),
    ]

    for sec_type, value in legacy_map:
        if sec_type not in SECTION_TYPES:
            continue
        values = _coerce_string_list(value)
        if not values:
            continue
        sections.append({
            "id": uuid4().hex,
            "type": sec_type,
            "items": _clean_section_items(values),
        })

    return sections


# Cache for skill_editor default prompts (loaded once from Python source constants)
_skill_editor_defaults: Optional[Dict[str, str]] = None

def _get_skill_editor_default_prompt(prompt_id: str, title: str) -> Optional[str]:
    """Load default prompt text for skill_editor system prompts from Python source constants.
    
    These prompts are stored in Agent_Prompts DynamoDB (inaccessible from desktop),
    but their defaults are hardcoded in the skill_editor agent source files.
    """
    global _skill_editor_defaults
    if _skill_editor_defaults is None:
        _skill_editor_defaults = {}
        try:
            from agent.skill_editor.planner_agent import PLANNER_SYSTEM_PROMPT
            _skill_editor_defaults["planner"] = PLANNER_SYSTEM_PROMPT
        except Exception:
            pass
        try:
            from agent.skill_editor.code_agent import CODE_GENERATION_PROMPT, EDIT_FLOWGRAM_PROMPT
            _skill_editor_defaults["code_gen"] = CODE_GENERATION_PROMPT
            _skill_editor_defaults["edit_flowgram"] = EDIT_FLOWGRAM_PROMPT
        except Exception:
            pass
        try:
            from agent.skill_editor.validator_agent import VALIDATOR_SYSTEM_PROMPT
            _skill_editor_defaults["validator"] = VALIDATOR_SYSTEM_PROMPT
        except Exception:
            pass
        try:
            from agent.skill_editor.skill_editor_agent import INTENT_CLASSIFIER_SYSTEM_PROMPT
            _skill_editor_defaults["intent_classifier"] = INTENT_CLASSIFIER_SYSTEM_PROMPT
        except Exception:
            pass
        # Log-analysis prompts are DynamoDB-only (no Python source constants).
        # Inline defaults extracted from skill_editor_agent.py and named by purpose.
        _skill_editor_defaults.setdefault("log_parser", (
            "You are a Log Parser for eCan.ai, an AI agent / workflow automation platform.\n\n"
            "Your job is to parse raw log files and extract structured information:\n"
            "- Timestamps, log levels, component names\n"
            "- Error messages and stack traces\n"
            "- Request/response pairs and their status codes\n"
            "- Node execution timings and outcomes\n\n"
            "Output a structured summary with categorised log entries."
        ))
        _skill_editor_defaults.setdefault("log_analysis_orchestrator", (
            "You are a Log Analysis Orchestrator for eCan.ai.\n\n"
            "You coordinate multi-step log analysis by:\n"
            "1. Dispatching the raw log to the Log Parser for structured extraction\n"
            "2. Sending parsed data to the Root Cause Analyzer for diagnosis\n"
            "3. Correlating findings with flowgram execution via the Flowgram Correlator\n"
            "4. Producing a consolidated analysis report with prioritised recommendations\n\n"
            "Ensure each sub-agent receives the context it needs and aggregate their outputs."
        ))
        _skill_editor_defaults.setdefault("root_cause_analyzer", (
            "You are a Root Cause Analyzer for eCan.ai.\n\n"
            "Given parsed log entries (errors, warnings, exceptions), your job is to:\n"
            "1. Identify the root cause of failures — distinguish setup issues, code bugs, and backend errors\n"
            "2. Trace cascading failures back to their origin (e.g. an auth failure causing downstream timeouts)\n"
            "3. Classify each issue: setup issue (customer config), code bug, or backend issue\n"
            "4. Provide a prioritised list of recommended fixes\n\n"
            "Be specific — quote relevant log lines when referencing errors."
        ))
        _skill_editor_defaults.setdefault("flowgram_correlator", (
            "You are a Flowgram Correlator for eCan.ai.\n\n"
            "Given log analysis results and a flowgram (workflow graph), your job is to:\n"
            "1. Map each log error/warning to the specific flowgram node that produced it\n"
            "2. Identify which edges (transitions) failed or were never reached\n"
            "3. Highlight bottleneck nodes (high duration or frequent retries)\n"
            "4. Suggest flowgram modifications to improve reliability\n\n"
            "Output a node-by-node status report with correlations to log findings."
        ))
        logger.info(f"[prompts] Loaded {len(_skill_editor_defaults)} skill_editor default prompts: {list(_skill_editor_defaults.keys())}")

    # Try prompt_id directly (e.g. "planner")
    text = _skill_editor_defaults.get(prompt_id)
    if text:
        return text
    # Try stripping "skill_editor_" prefix from title (e.g. "skill_editor_planner" -> "planner")
    if title.startswith("skill_editor_"):
        short = title[len("skill_editor_"):]
        text = _skill_editor_defaults.get(short)
        if text:
            return text
    return None


def _normalize_prompt(raw: Any, *, source: str, read_only: bool, last_modified_ts: Optional[float]) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}

    prompt: Dict[str, Any] = {}
    prompt["id"] = str(data.get("id") or "").strip()
    prompt["title"] = str(data.get("title") or "").strip()
    prompt["topic"] = str(data.get("topic") or "").strip()

    usage_count = data.get("usageCount", 0)
    try:
        prompt["usageCount"] = int(usage_count)
    except (TypeError, ValueError):
        prompt["usageCount"] = 0

    prompt["sections"] = _normalize_sections(data.get("sections"), data)
    prompt["userSections"] = _normalize_sections(data.get("userSections"), {})
    prompt["humanInputs"] = _coerce_string_list(data.get("humanInputs") or data.get("human_inputs"))

    if isinstance(last_modified_ts, (int, float)):
        prompt["lastModified"] = datetime.fromtimestamp(last_modified_ts).isoformat()
    else:
        last_modified = data.get("lastModified")
        if isinstance(last_modified, (int, float)):
            prompt["lastModified"] = datetime.fromtimestamp(last_modified).isoformat()
        elif last_modified:
            prompt["lastModified"] = str(last_modified)
        else:
            prompt["lastModified"] = ""

    prompt["source"] = source
    prompt["readOnly"] = bool(read_only or data.get("readOnly"))

    # Determine owner: preserve from raw data, or detect system prompts by title/id prefix
    owner = data.get("owner", "")
    title = prompt.get("title", "")
    pid = prompt.get("id", "")
    is_skill_editor = title.startswith("skill_editor_") or pid.startswith("skill_editor_")
    if not owner and is_skill_editor:
        owner = "system"
    prompt["owner"] = owner

    # Preserve rawContent for prompts that are plain text (not structured JSON sections)
    raw_content = data.get("rawContent")

    # For skill_editor system prompts with empty sections and no rawContent,
    # load the default prompt text from the hardcoded Python constants
    if not raw_content and is_skill_editor and not prompt.get("sections"):
        raw_content = _get_skill_editor_default_prompt(pid, title)

    if raw_content:
        prompt["rawContent"] = str(raw_content)

    # Preserve format and mdContent for markdown-mode prompts
    fmt = data.get("format")
    if fmt in ("json", "md"):
        prompt["format"] = fmt
    md_content = data.get("mdContent")
    if md_content:
        prompt["mdContent"] = str(md_content)

    # Preserve agentChatHistory (per-prompt conversation with the prompt agent).
    # Each entry is { id, role: 'user'|'assistant', content, timestamp }.
    chat_history = data.get("agentChatHistory")
    if isinstance(chat_history, list) and chat_history:
        sanitized: List[Dict[str, Any]] = []
        for entry in chat_history:
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or "").strip().lower()
            if role not in ("user", "assistant"):
                continue
            content = str(entry.get("content") or "")
            if not content:
                continue
            sanitized.append({
                "id": str(entry.get("id") or uuid4().hex),
                "role": role,
                "content": content,
                "timestamp": str(entry.get("timestamp") or ""),
            })
        if sanitized:
            prompt["agentChatHistory"] = sanitized

    return prompt


DEFAULT_PROMPTS: List[Dict[str, Any]] = [
    {
        "id": "pr-1",
        "title": "Write a marketing email",
        "topic": "Marketing email",
        "usageCount": 12,
        "sections": [
            {
                "id": "pr-1-background",
                "type": "background",
                "items": ["You are a helpful marketing assistant. Tone: friendly, concise."],
            },
            {
                "id": "pr-1-goals",
                "type": "goals",
                "items": ["Introduce new product", "Encourage click-through"],
            },
            {
                "id": "pr-1-guidelines",
                "type": "guidelines",
                "items": ["Keep under 150 words", "Use American English"],
            },
            {
                "id": "pr-1-rules",
                "type": "rules",
                "items": ["No false claims", "Avoid spammy phrases"],
            },
            {
                "id": "pr-1-instructions",
                "type": "instructions",
                "items": ["Start with a hook", "Add a CTA at the end"],
            },
            {
                "id": "pr-1-variables",
                "type": "variables",
                "items": ["Product name", "Key features"],
            },
        ],
        "humanInputs": ["Audience segment", "Special offers"],
    },
    {
        "id": "pr-2",
        "title": "Summarize research paper",
        "topic": "Research summary",
        "usageCount": 7,
        "sections": [
            {
                "id": "pr-2-background",
                "type": "background",
                "items": ["You are a scientific assistant. Tone: neutral, precise."],
            },
            {
                "id": "pr-2-goals",
                "type": "goals",
                "items": ["Capture main contributions", "Note limitations"],
            },
            {
                "id": "pr-2-guidelines",
                "type": "guidelines",
                "items": ["Use bullet points", "Cite key sections if available"],
            },
            {
                "id": "pr-2-rules",
                "type": "rules",
                "items": ["Avoid speculation"],
            },
            {
                "id": "pr-2-instructions",
                "type": "instructions",
                "items": ["Provide 3-5 bullets", "Include 1-sentence abstract"],
            },
            {
                "id": "pr-2-variables",
                "type": "variables",
                "items": ["Paper URL", "Discipline"],
            },
        ],
        "humanInputs": ["Desired length"],
    },
]


def _slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9\-_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_-")
    return value or "prompt"


def _load_prompts_from_directory(dir_path: Path, *, source: str, read_only: bool) -> List[Tuple[Dict[str, Any], float]]:
    prompts: List[Tuple[Dict[str, Any], float]] = []
    # For MY_PROMPTS_DIR, ensure it's initialized
    if source == "my_prompts" and dir_path is None:
        dir_path = _get_my_prompts_dir()
    if not dir_path.exists():
        return prompts

    for file_path in dir_path.glob("*.json"):
        try:
            with file_path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            if not isinstance(data, dict):
                continue
            mtime = file_path.stat().st_mtime
            normalized = _normalize_prompt(data, source=source, read_only=read_only, last_modified_ts=mtime)
            if not normalized.get("id"):
                continue
            prompts.append((normalized, mtime))
        except Exception as exc:
            logger.warning(f"[prompts] failed to load {file_path.name}: {exc}")
    return prompts


def _load_all_prompts() -> List[Dict[str, Any]]:
    _ensure_prompt_dirs()

    combined: Dict[str, Dict[str, Any]] = {}
    mtimes: Dict[str, float] = {}

    directories = [
        (SAMPLE_PROMPTS_DIR, "sample_prompts", False),  # Changed to editable
        (_get_my_prompts_dir(), "my_prompts", False),
    ]

    for dir_path, source, read_only in directories:
        for prompt, mtime in _load_prompts_from_directory(dir_path, source=source, read_only=read_only):
            pid = prompt.get("id")
            if not pid:
                continue
            prev = combined.get(pid)
            prev_mtime = mtimes.get(pid, 0)
            should_replace = False

            if prev is None:
                should_replace = True
            elif (not prev.get("readOnly") and prompt.get("readOnly")):
                # Keep editable prompt over read-only duplicates
                should_replace = False
            elif (prev.get("readOnly") and not prompt.get("readOnly")):
                should_replace = True
            elif mtime >= prev_mtime:
                should_replace = True

            if should_replace:
                combined[pid] = prompt
                mtimes[pid] = mtime

    ordered = sorted(combined.values(), key=lambda item: mtimes.get(item["id"], 0), reverse=True)
    return ordered


def _find_prompt_file_by_id(prompt_id: str) -> Optional[Path]:
    if not prompt_id:
        return None
    my_prompts_dir = _get_my_prompts_dir()
    if not my_prompts_dir.exists():
        return None
    for file_path in my_prompts_dir.glob("*.json"):
        try:
            with file_path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict) and data.get("id") == prompt_id:
                return file_path
        except Exception as exc:
            logger.warning(f"[prompts] failed to inspect {file_path.name}: {exc}")
    return None


def _serialize_prompt_for_storage(prompt: Dict[str, Any]) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": prompt.get("id", ""),
        "title": prompt.get("title", ""),
        "topic": prompt.get("topic", ""),
        "usageCount": int(prompt.get("usageCount") or 0),
        "humanInputs": _coerce_string_list(prompt.get("humanInputs")),
    }

    sections: List[Dict[str, Any]] = []
    for entry in prompt.get("sections", []) or []:
        if not isinstance(entry, dict):
            continue
        sec_type = str(entry.get("type") or "").strip().lower()
        if sec_type not in SECTION_TYPES:
            continue
        sec_id = str(entry.get("id") or uuid4().hex)
        items = entry.get("items", [])
        if not isinstance(items, list):
            items = [items]
        section_payload = {
            "id": sec_id,
            "type": sec_type,
            "items": _clean_section_items(_coerce_string_list(items)),
        }
        if sec_type == "custom" and entry.get("customLabel"):
            section_payload["customLabel"] = str(entry.get("customLabel"))
        sections.append(section_payload)

    data["sections"] = sections

    user_sections: List[Dict[str, Any]] = []
    for entry in prompt.get("userSections", []) or []:
        if not isinstance(entry, dict):
            continue
        sec_type = str(entry.get("type") or "").strip().lower()
        if sec_type not in SECTION_TYPES:
            continue
        sec_id = str(entry.get("id") or uuid4().hex)
        items = entry.get("items", [])
        if not isinstance(items, list):
            items = [items]
        section_payload = {
            "id": sec_id,
            "type": sec_type,
            "items": _clean_section_items(_coerce_string_list(items)),
        }
        if sec_type == "custom" and entry.get("customLabel"):
            section_payload["customLabel"] = str(entry.get("customLabel"))
        user_sections.append(section_payload)

    data["userSections"] = user_sections

    # Preserve rawContent for plain-text prompts (not yet converted to structured sections)
    raw_content = prompt.get("rawContent")
    if raw_content:
        data["rawContent"] = str(raw_content)

    # Preserve format and mdContent for markdown-mode prompts
    fmt = prompt.get("format")
    if fmt in ("json", "md"):
        data["format"] = fmt
    md_content = prompt.get("mdContent")
    if md_content:
        data["mdContent"] = str(md_content)

    # Persist agentChatHistory (per-prompt conversation with the prompt agent).
    # Cap to last 100 entries to keep prompt JSON from ballooning.
    chat_history = prompt.get("agentChatHistory")
    if isinstance(chat_history, list) and chat_history:
        sanitized: List[Dict[str, Any]] = []
        for entry in chat_history[-100:]:
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or "").strip().lower()
            if role not in ("user", "assistant"):
                continue
            content = str(entry.get("content") or "")
            if not content:
                continue
            sanitized.append({
                "id": str(entry.get("id") or uuid4().hex),
                "role": role,
                "content": content,
                "timestamp": str(entry.get("timestamp") or ""),
            })
        if sanitized:
            data["agentChatHistory"] = sanitized

    return data


def _write_prompt_to_file(prompt: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_prompt_dirs()
    prompt = deepcopy(prompt if isinstance(prompt, dict) else {})
    logger.debug("prompt to be saved:", prompt)
    prompt_id = str(prompt.get("id") or "").strip()
    if not prompt_id:
        raise ValueError("prompt id is required for persistence")

    if not prompt.get("title"):
        prompt["title"] = prompt_id
    if not prompt.get("topic"):
        prompt["topic"] = prompt["title"]

    serialized = _serialize_prompt_for_storage(prompt)
    serialized["lastModified"] = datetime.utcnow().isoformat()

    id_slug = _slugify(prompt_id) or "prompt"
    base_label = str(serialized.get("title") or serialized.get("topic") or "prompt")
    name_slug = _slugify(base_label) or "prompt"
    filename_base = f"{name_slug}_{id_slug}"
    my_prompts_dir = _get_my_prompts_dir()
    target_path = my_prompts_dir / f"{filename_base}.json"

    existing_path = _find_prompt_file_by_id(prompt_id)
    if existing_path and existing_path.exists() and existing_path.resolve() != target_path.resolve():
        try:
            existing_path.unlink()
        except Exception as exc:
            logger.warning(f"[prompts] failed to remove stale prompt file {existing_path.name}: {exc}")

    logger.debug(f"[prompts] writing prompt to {target_path}")
    try:
        with target_path.open("w", encoding="utf-8") as fp:
            json.dump(serialized, fp, indent=2, ensure_ascii=False)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"[prompts] failed to write prompt to {target_path}: {exc}")
        raise

    normalized = _normalize_prompt(serialized, source="my_prompts", read_only=False, last_modified_ts=target_path.stat().st_mtime)
    return normalized

def _bootstrap_prompts() -> List[Dict[str, Any]]:
    prompts = _load_all_prompts()
    if prompts:
        logger.info(f"[prompts] Loaded {len(prompts)} prompts from disk")
        # Log prompt IDs for debugging
        prompt_ids = [p.get('id', 'unknown') for p in prompts]
        logger.debug(f"[prompts] Prompt IDs: {prompt_ids}")
        return prompts

    # No prompts found on disk – fall back to defaults (read-only, sample source)
    logger.warning("[prompts] No prompts found on disk, using default prompts")
    fallback: List[Dict[str, Any]] = []
    for default_prompt in DEFAULT_PROMPTS:
        normalized = _normalize_prompt(
            deepcopy(default_prompt),
            source="sample_prompts",
            read_only=True,
            last_modified_ts=None,
        )
        normalized["readOnly"] = True
        fallback.append(normalized)
    logger.info(f"[prompts] Created {len(fallback)} default prompts")
    return fallback


def _delete_prompt_file(prompt_id: str) -> bool:
    target = _find_prompt_file_by_id(prompt_id)
    if target and target.exists():
        try:
            target.unlink()
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"[prompts] failed to delete {target.name}: {exc}")
    return False


@IPCHandlerRegistry.handler('get_prompts')
def handle_get_prompts(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    try:
        total_start = time.perf_counter()

        local_start = time.perf_counter()
        local_prompts = _bootstrap_prompts()
        logger.info(f"[Perf][prompts] local bootstrap: {(time.perf_counter() - local_start) * 1000:.1f}ms")
        local_by_id = {p["id"]: p for p in local_prompts if p.get("id")}

        # ── Bidirectional sync: merge cloud prompts (superset policy) ──
        cloud_only_prompts: List[Dict[str, Any]] = []
        if _CLOUD_SYNC_AVAILABLE:
            try:
                cloud_start = time.perf_counter()
                cloud_prompts = fetch_cloud_prompts()
                logger.info(f"[Perf][prompts] cloud fetch: {(time.perf_counter() - cloud_start) * 1000:.1f}ms")
                logger.info(f"[prompts] Cloud returned {len(cloud_prompts)} prompts, local has {len(local_by_id)}")
                merge_start = time.perf_counter()
                for cp in cloud_prompts:
                    cid = cp.get("id")
                    if not cid:
                        continue
                    # Decide whether to use cloud version:
                    # 1. Prompt doesn't exist locally
                    # 2. Local version has empty sections AND no rawContent (lost data),
                    #    but cloud version has rawContent — prefer cloud
                    local_prompt = local_by_id.get(cid)
                    use_cloud = False
                    if local_prompt is None:
                        use_cloud = True
                    elif (not local_prompt.get("sections") and not local_prompt.get("rawContent")
                          and cp.get("rawContent")):
                        use_cloud = True
                        logger.info(f"[prompts] Local prompt '{cid}' has empty content, replacing with cloud version that has rawContent")

                    if use_cloud:
                        try:
                            saved = _write_prompt_to_file(cp)
                            local_by_id[cid] = saved
                            cloud_only_prompts.append(saved)
                            logger.info(f"[prompts] Downloaded cloud prompt '{cid}' ('{cp.get('title')}') to local")
                        except Exception as save_exc:
                            logger.warning(f"[prompts] Failed to save cloud prompt '{cid}' locally: {save_exc}")
                            local_by_id[cid] = cp
                            cloud_only_prompts.append(cp)
                logger.info(f"[Perf][prompts] cloud merge/writeback: {(time.perf_counter() - merge_start) * 1000:.1f}ms")
            except Exception as fetch_exc:
                logger.warning(f"[prompts] Cloud prompt fetch skipped: {fetch_exc}")

        prompts = list(local_by_id.values())

        # Push local-only prompts to cloud (non-blocking, fire-and-forget)
        if _CLOUD_SYNC_AVAILABLE:
            try:
                sync_start = time.perf_counter()
                sync_all_prompts_to_cloud(prompts)
                logger.info(f"[Perf][prompts] schedule bulk sync: {(time.perf_counter() - sync_start) * 1000:.1f}ms")
            except Exception as sync_exc:
                logger.debug(f"[prompts] bulk cloud sync skipped: {sync_exc}")

        if cloud_only_prompts:
            logger.info(f"[prompts] Merged {len(cloud_only_prompts)} cloud-only prompts into local set (total: {len(prompts)})")

        logger.info(f"[Perf][prompts] total get_prompts: {(time.perf_counter() - total_start) * 1000:.1f}ms")
        return create_success_response(request, {"prompts": prompts})
    except Exception as e:
        logger.error(f"[prompts] get_prompts error: {e}")
        return create_error_response(request, 'GET_PROMPTS_ERROR', str(e))

@IPCHandlerRegistry.handler('save_prompt')
def handle_save_prompt(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    try:
        params = params or {}

        # Support multiple input formats:
        # 1. Direct: { prompt: {...} }
        # 2. GraphQL format: { input: [{ id, owner, prompt: JSON_STRING, version }] }
        prompt = params.get('prompt')

        if not prompt:
            # Try GraphQL format: { input: [{ id, owner, prompt: JSON_STRING, version }] }
            # Frontend always sends id via api.ts savePrompt(): id: id || `pr-${random}`
            input_list = params.get('input')
            if input_list and isinstance(input_list, list) and len(input_list) > 0:
                graphql_prompt = input_list[0]
                if isinstance(graphql_prompt, dict):
                    prompt_id = graphql_prompt.get('id')
                    prompt_owner = graphql_prompt.get('owner')
                    prompt_json_str = graphql_prompt.get('prompt')

                    if prompt_json_str and isinstance(prompt_json_str, str):
                        try:
                            prompt_data = json.loads(prompt_json_str)
                        except json.JSONDecodeError:
                            prompt_data = {}
                    elif isinstance(prompt_json_str, dict):
                        prompt_data = prompt_json_str
                    else:
                        prompt_data = {}

                    # Flatten to expected format
                    prompt = {
                        'id': prompt_id,
                        'owner': prompt_owner,
                        **prompt_data
                    }

        if not prompt or not isinstance(prompt, dict) or not prompt.get('id'):
            logger.warning(f"[prompts] save_prompt invalid params: {list(params.keys())}")
            return create_error_response(request, 'INVALID_PARAMS', 'prompt with id is required')
        if prompt.get('readOnly'):
            return create_error_response(request, 'READ_ONLY', 'Cannot modify read-only prompt')
        normalized = _write_prompt_to_file(prompt)
        logger.debug(f"[prompts] saved prompt {normalized.get('id')} to my_prompts")
        invalidate_cloud_prompts_cache(normalized.get('owner'))
        # Sync to cloud in background
        sync_prompt_to_cloud(normalized)
        return create_success_response(request, {"prompt": normalized})
    except Exception as e:
        logger.error(f"[prompts] save_prompt error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'SAVE_PROMPT_ERROR', str(e))

@IPCHandlerRegistry.handler('delete_prompt')
def handle_delete_prompt(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    try:
        params = params or {}

        # Support multiple input formats:
        # 1. Direct: { id: 'xxx' }
        # 2. GraphQL format: { input: ['xxx'] }
        pid = params.get('id')

        if not pid:
            # Try GraphQL format: input is an array of IDs
            input_list = params.get('input')
            if input_list and isinstance(input_list, list) and len(input_list) > 0:
                pid = input_list[0]

        if not pid:
            logger.warning(f"[prompts] delete_prompt invalid params: {list(params.keys())}")
            return create_error_response(request, 'INVALID_PARAMS', 'id is required')
        prompt_meta = None
        for prompt in _load_all_prompts():
            if prompt.get('id') == pid:
                prompt_meta = prompt
                break
        if prompt_meta and prompt_meta.get('readOnly'):
            return create_error_response(request, 'READ_ONLY', 'Cannot delete read-only prompt')

        deleted = _delete_prompt_file(str(pid))
        cloud_deleted = False
        if _CLOUD_SYNC_AVAILABLE:
            cloud_deleted = delete_prompt_from_cloud_sync(str(pid))
        owner = prompt_meta.get('owner') if prompt_meta else None
        if owner:
            invalidate_cloud_prompts_cache(owner)
        else:
            invalidate_cloud_prompts_cache(None)
        return create_success_response(
            request,
            {"deleted": deleted, "cloudDeleted": cloud_deleted},
        )
    except Exception as e:
        logger.error(f"[prompts] delete_prompt error: {e}")
        return create_error_response(request, 'DELETE_PROMPT_ERROR', str(e))
