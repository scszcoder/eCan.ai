"""Prompt handlers: IPC persistence for prompt editor."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple, Set

from gui.ipc.types import IPCRequest, IPCResponse, create_success_response, create_error_response
from gui.ipc.registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = PROJECT_ROOT / "my_prompts"
SAMPLE_PROMPTS_PRIMARY_DIR = PROJECT_ROOT / "resource" / "systems" / "sample_prompts"
SAMPLE_PROMPTS_FALLBACK_DIR = PROJECT_ROOT / "sample_prompts"

SYSTEM_SECTION_TYPES = {
    "roleCharacter",
    "tone",
    "background",
    "goals",
    "guidelines",
    "rules",
    "examples",
    "instructions",
    "variables",
}

LIST_FIELDS = [
    "goals",
    "guidelines",
    "rules",
    "instructions",
    "sysInputs",
    "humanInputs",
]


def _normalize_prompt(raw: Any, *, inherited_read_only: bool = False) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}

    def _coerce_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            iterable = value
        elif isinstance(value, (set, tuple)):
            iterable = list(value)
        else:
            iterable = [value]
        return ["" if v is None else str(v) for v in iterable]

    def _normalize_sections(value: Any, default_read_only: bool) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []

        normalized: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        for idx, raw_section in enumerate(value):
            if not isinstance(raw_section, dict):
                continue
            section_type = str(raw_section.get("type") or "").strip()
            if section_type not in SYSTEM_SECTION_TYPES:
                continue

            items = _coerce_list(raw_section.get("items"))
            if not items and section_type not in {"roleCharacter", "tone", "background", "examples", "variables"}:
                # Allow empty only for descriptive blocks; skip otherwise to reduce noise
                continue

            section_id = str(raw_section.get("id") or "").strip()
            if not section_id:
                section_id = f"{section_type}_{idx + 1}"
            if section_id in seen_ids:
                section_id = f"{section_id}_{len(normalized) + 1}"
            seen_ids.add(section_id)

            section_read_only = bool(raw_section.get("readOnly")) or default_read_only

            section_payload: Dict[str, Any] = {
                "id": section_id,
                "type": section_type,
                "items": items,
            }
            if section_read_only:
                section_payload["readOnly"] = True

            normalized.append(section_payload)

        return normalized

    prompt: Dict[str, Any] = {}
    prompt["id"] = str(data.get("id") or "").strip()
    prompt["title"] = str(data.get("title") or "").strip()
    prompt["topic"] = str(data.get("topic") or "").strip()

    usage_count = data.get("usageCount", 0)
    try:
        prompt["usageCount"] = int(usage_count)
    except (TypeError, ValueError):
        prompt["usageCount"] = 0

    prompt["roleToneContext"] = str(data.get("roleToneContext") or "")

    for field in LIST_FIELDS:
        prompt[field] = _coerce_list(data.get(field))

    sections = _normalize_sections(data.get("systemSections"), bool(data.get("readOnly")) or inherited_read_only)
    prompt["systemSections"] = sections
    prompt["examples"] = _coerce_list(data.get("examples"))
    prompt["readOnly"] = bool(data.get("readOnly")) or inherited_read_only

    last_modified = data.get("lastModified")
    if isinstance(last_modified, (int, float)):
        prompt["lastModified"] = datetime.fromtimestamp(last_modified).isoformat()
    elif last_modified:
        prompt["lastModified"] = str(last_modified)
    else:
        prompt["lastModified"] = ""

    return prompt


DEFAULT_PROMPTS: List[Dict[str, Any]] = [
    {
        "id": "pr-1",
        "title": "Write a marketing email",
        "topic": "Marketing email",
        "usageCount": 12,
        "roleToneContext": "You are a helpful marketing assistant. Tone: friendly, concise.",
        "goals": ["Introduce new product", "Encourage click-through"],
        "guidelines": ["Keep under 150 words", "Use American English"],
        "rules": ["No false claims", "Avoid spammy phrases"],
        "instructions": ["Start with a hook", "Add a CTA at the end"],
        "sysInputs": ["Product name", "Key features"],
        "humanInputs": ["Audience segment", "Special offers"],
    },
    {
        "id": "pr-2",
        "title": "Summarize research paper",
        "topic": "Research summary",
        "usageCount": 7,
        "roleToneContext": "You are a scientific assistant. Tone: neutral, precise.",
        "goals": ["Capture main contributions", "Note limitations"],
        "guidelines": ["Use bullet points", "Cite key sections if available"],
        "rules": ["Avoid speculation"],
        "instructions": ["Provide 3-5 bullets", "Include 1-sentence abstract"],
        "sysInputs": ["Paper URL", "Discipline"],
        "humanInputs": ["Desired length"],
    },
]


def _ensure_prompts_dir() -> None:
    try:
        PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"[prompts] failed to create prompts directory: {exc}")


def _slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9\-_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_-")
    return value or "prompt"


def _load_prompts_from_disk() -> List[Dict[str, Any]]:
    _ensure_prompts_dir()
    by_id: Dict[str, Dict[str, Any]] = {}
    mtimes: Dict[str, float] = {}

    directories: List[Tuple[Path, bool]] = []
    seen: Set[Path] = set()

    for candidate, read_only in [
        (SAMPLE_PROMPTS_PRIMARY_DIR, True),
        (SAMPLE_PROMPTS_FALLBACK_DIR, True),
        (PROMPTS_DIR, False),
    ]:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        directories.append((candidate, read_only))

    for base_dir, read_only in directories:
        if not base_dir.exists():
            continue
        for file_path in base_dir.glob("*.json"):
            try:
                with file_path.open("r", encoding="utf-8") as fp:
                    data = json.load(fp)
                if not isinstance(data, dict):
                    continue
                normalized = _normalize_prompt(data, inherited_read_only=read_only)
                if not normalized.get("id"):
                    continue

                if not normalized.get("title"):
                    normalized["title"] = normalized["id"]
                if not normalized.get("topic"):
                    normalized["topic"] = normalized["title"]

                pid = normalized["id"]
                mtime = file_path.stat().st_mtime
                normalized["lastModified"] = datetime.fromtimestamp(mtime).isoformat()
                normalized["location"] = base_dir.name
                if read_only:
                    normalized["readOnly"] = True

                existing_mtime = mtimes.get(pid)
                existing_prompt = by_id.get(pid)

                should_replace = False
                if existing_prompt is None:
                    should_replace = True
                elif read_only and not existing_prompt.get("readOnly"):
                    # keep writable prompt over read-only fallback
                    should_replace = False
                elif not read_only and existing_prompt.get("readOnly"):
                    should_replace = True
                elif existing_mtime is None or mtime >= existing_mtime:
                    should_replace = True

                if should_replace:
                    by_id[pid] = normalized
                    mtimes[pid] = mtime
            except Exception as exc:
                logger.warning(f"[prompts] failed to load {file_path.name}: {exc}")

    ordered = sorted(by_id.values(), key=lambda item: mtimes.get(item["id"], 0), reverse=True)
    return ordered


def _find_prompt_file_by_id(prompt_id: str) -> Optional[Path]:
    if not prompt_id:
        return None
    if not PROMPTS_DIR.exists():
        return None
    for file_path in PROMPTS_DIR.glob("*.json"):
        try:
            with file_path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict) and data.get("id") == prompt_id:
                return file_path
        except Exception as exc:
            logger.warning(f"[prompts] failed to inspect {file_path.name}: {exc}")
    return None


def _write_prompt_to_file(prompt: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_prompts_dir()
    prompt = _normalize_prompt(prompt)
    prompt_id = str(prompt.get("id") or "").strip()
    if not prompt_id:
        raise ValueError("prompt id is required for persistence")

    if prompt.get("readOnly"):
        raise ValueError("cannot persist read-only prompts")

    if not prompt.get("title"):
        prompt["title"] = prompt_id
    if not prompt.get("topic"):
        prompt["topic"] = prompt["title"]

    prompt["lastModified"] = datetime.utcnow().isoformat()

    # Do not persist runtime-only flags
    prompt.pop("readOnly", None)

    id_slug = _slugify(prompt_id) or "prompt"
    base_label = str(prompt.get("title") or prompt.get("topic") or "prompt")
    name_slug = _slugify(base_label) or "prompt"
    filename_base = f"{name_slug}_{id_slug}"
    target_path = PROMPTS_DIR / f"{filename_base}.json"

    existing_path = _find_prompt_file_by_id(prompt_id)
    if existing_path and existing_path.exists() and existing_path.resolve() != target_path.resolve():
        try:
            existing_path.unlink()
        except Exception as exc:
            logger.warning(f"[prompts] failed to remove stale prompt file {existing_path.name}: {exc}")

    logger.debug(f"[prompts] writing prompt to {target_path}")
    try:
        with target_path.open("w", encoding="utf-8") as fp:
            json.dump(prompt, fp, indent=2, ensure_ascii=False)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"[prompts] failed to write prompt to {target_path}: {exc}")
        raise

    prompt["location"] = PROMPTS_DIR.name
    return prompt

def _bootstrap_prompts() -> List[Dict[str, Any]]:
    prompts = _load_prompts_from_disk()
    if prompts:
        return prompts

    seeded: List[Dict[str, Any]] = []
    for default_prompt in DEFAULT_PROMPTS:
        prompt_copy = _normalize_prompt(deepcopy(default_prompt))
        if not prompt_copy.get("id"):
            continue
        if not prompt_copy.get("title"):
            prompt_copy["title"] = prompt_copy["id"]
        if not prompt_copy.get("topic"):
            prompt_copy["topic"] = prompt_copy["title"]
        try:
            _write_prompt_to_file(prompt_copy)
            seeded.append(prompt_copy)
        except Exception as exc:
            logger.error(f"[prompts] failed seeding default prompt {prompt_copy.get('id')}: {exc}")

    prompts = _load_prompts_from_disk()
    return prompts if prompts else seeded


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
            return create_error_response(request, 'READ_ONLY_PROMPT', 'Cannot modify a read-only prompt')
        saved_prompt = _write_prompt_to_file(prompt)
        logger.debug(f"[prompts] saved prompt {saved_prompt.get('id')} to {PROMPTS_DIR}")
        return create_success_response(request, {"prompt": saved_prompt})
    except Exception as e:
        logger.error(f"[prompts] save_prompt error: {e}")
        return create_error_response(request, 'SAVE_PROMPT_ERROR', str(e))

@IPCHandlerRegistry.handler('delete_prompt')
def handle_delete_prompt(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    try:
        pid = (params or {}).get('id')
        if not pid:
            return create_error_response(request, 'INVALID_PARAMS', 'id is required')
        deleted = _delete_prompt_file(str(pid))
        return create_success_response(request, {"deleted": deleted})
    except Exception as e:
        logger.error(f"[prompts] delete_prompt error: {e}")
        return create_error_response(request, 'DELETE_PROMPT_ERROR', str(e))
