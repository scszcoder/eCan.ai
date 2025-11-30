"""Prompt handlers: IPC persistence for prompt editor."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple
from uuid import uuid4

from gui.ipc.types import IPCRequest, IPCResponse, create_success_response, create_error_response
from gui.ipc.registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SYSTEMS_DIR = PROJECT_ROOT / "systems"
MY_PROMPTS_DIR = PROJECT_ROOT / "my_prompts"
SAMPLE_PROMPTS_DIR = PROJECT_ROOT / "resource" / "systems" / "sample_prompts"

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
    "custom",
)


def _ensure_prompt_dirs() -> None:
    try:
        MY_PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
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
        (SAMPLE_PROMPTS_DIR, "sample_prompts", True),
        (MY_PROMPTS_DIR, "my_prompts", False),
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
    if not MY_PROMPTS_DIR.exists():
        return None
    for file_path in MY_PROMPTS_DIR.glob("*.json"):
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
        sections.append({
            "id": sec_id,
            "type": sec_type,
            "items": _clean_section_items(_coerce_string_list(items)),
        })

    data["sections"] = sections
    return data


def _write_prompt_to_file(prompt: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_prompt_dirs()
    prompt = deepcopy(prompt if isinstance(prompt, dict) else {})
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
    target_path = MY_PROMPTS_DIR / f"{filename_base}.json"

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
        return prompts

    # No prompts found on disk – fall back to defaults (read-only, sample source)
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
        prompts = _bootstrap_prompts()
        return create_success_response(request, {"prompts": prompts})
    except Exception as e:
        logger.error(f"[prompts] get_prompts error: {e}")
        return create_error_response(request, 'GET_PROMPTS_ERROR', str(e))

@IPCHandlerRegistry.handler('save_prompt')
def handle_save_prompt(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    try:
        prompt = (params or {}).get('prompt')
        if not prompt or not isinstance(prompt, dict) or not prompt.get('id'):
            return create_error_response(request, 'INVALID_PARAMS', 'prompt with id is required')
        if prompt.get('readOnly'):
            return create_error_response(request, 'READ_ONLY', 'Cannot modify read-only prompt')
        normalized = _write_prompt_to_file(prompt)
        logger.debug(f"[prompts] saved prompt {normalized.get('id')} to my_prompts")
        return create_success_response(request, {"prompt": normalized})
    except Exception as e:
        logger.error(f"[prompts] save_prompt error: {e}")
        return create_error_response(request, 'SAVE_PROMPT_ERROR', str(e))

@IPCHandlerRegistry.handler('delete_prompt')
def handle_delete_prompt(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    try:
        pid = (params or {}).get('id')
        if not pid:
            return create_error_response(request, 'INVALID_PARAMS', 'id is required')
        prompt_meta = None
        for prompt in _load_all_prompts():
            if prompt.get('id') == pid:
                prompt_meta = prompt
                break
        if prompt_meta and prompt_meta.get('readOnly'):
            return create_error_response(request, 'READ_ONLY', 'Cannot delete read-only prompt')

        deleted = _delete_prompt_file(str(pid))
        return create_success_response(request, {"deleted": deleted})
    except Exception as e:
        logger.error(f"[prompts] delete_prompt error: {e}")
        return create_error_response(request, 'DELETE_PROMPT_ERROR', str(e))
