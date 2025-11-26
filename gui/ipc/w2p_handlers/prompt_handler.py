"""Prompt handlers: IPC persistence for prompt editor."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional, Dict, List

from gui.ipc.types import IPCRequest, IPCResponse, create_success_response, create_error_response
from gui.ipc.registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = PROJECT_ROOT / "prompts"

LIST_FIELDS = [
    "goals",
    "guidelines",
    "rules",
    "instructions",
    "sysInputs",
    "humanInputs",
]


def _normalize_prompt(raw: Any) -> Dict[str, Any]:
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
    if not PROMPTS_DIR.exists():
        return []
    for file_path in PROMPTS_DIR.glob("*.json"):
        try:
            with file_path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict):
                normalized = _normalize_prompt(data)
                if normalized.get("id"):
                    if not normalized.get("title"):
                        normalized["title"] = normalized["id"]
                    if not normalized.get("topic"):
                        normalized["topic"] = normalized["title"]
                    mtime = file_path.stat().st_mtime
                    pid = normalized["id"]
                    if pid not in by_id or mtime >= mtimes.get(pid, 0):
                        by_id[pid] = normalized
                        mtimes[pid] = mtime
        except Exception as exc:
            logger.warning(f"[prompts] failed to load {file_path.name}: {exc}")
    # Preserve deterministic ordering: newest first
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


def _write_prompt_to_file(prompt: Dict[str, Any]) -> Path:
    _ensure_prompts_dir()
    prompt = _normalize_prompt(prompt)
    prompt_id = str(prompt.get("id") or "").strip()
    if not prompt_id:
        raise ValueError("prompt id is required for persistence")

    if not prompt.get("title"):
        prompt["title"] = prompt_id
    if not prompt.get("topic"):
        prompt["topic"] = prompt["title"]

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

    return target_path

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
        persisted_path = _write_prompt_to_file(prompt)
        logger.debug(f"[prompts] saved prompt {prompt.get('id')} to {persisted_path}")
        return create_success_response(request, {"prompt": prompt})
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
