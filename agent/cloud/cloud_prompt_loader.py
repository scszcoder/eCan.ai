"""Cloud-compatible prompt loader for S3-based prompts.

This module provides prompt loading functionality that works in cloud environments
without requiring PySide6 or local filesystem access.

Structure on S3:
- User prompts: {user_prefix}/prompts/toc.json (index), {user_prefix}/prompts/{prompt_id}.json (individual prompts)
- Public/sample prompts: public/prompts/sample_prompts/toc.json, public/prompts/sample_prompts/{prompt_id}.json
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Generator
from uuid import uuid4

from utils.logger_helper import logger_helper as logger


# Thread-local storage for cloud context
_cloud_context = threading.local()


@dataclass
class CloudPromptContext:
    """Context for cloud prompt loading."""
    bucket: str
    user_prefix: str
    region: str = "us-east-1"


def set_cloud_prompt_context(bucket: str, user_prefix: str, region: str = "us-east-1") -> None:
    """Set the cloud prompt context for the current thread."""
    _cloud_context.ctx = CloudPromptContext(bucket=bucket, user_prefix=user_prefix, region=region)
    logger.debug(f"[cloud_prompts] Set context: bucket={bucket}, user_prefix={user_prefix}")


def get_cloud_prompt_context() -> Optional[CloudPromptContext]:
    """Get the cloud prompt context for the current thread."""
    return getattr(_cloud_context, 'ctx', None)


def clear_cloud_prompt_context() -> None:
    """Clear the cloud prompt context."""
    if hasattr(_cloud_context, 'ctx'):
        delattr(_cloud_context, 'ctx')


@contextmanager
def cloud_prompt_context(bucket: str, user_prefix: str, region: str = "us-east-1") -> Generator[CloudPromptContext, None, None]:
    """Context manager for cloud prompt loading."""
    ctx = CloudPromptContext(bucket=bucket, user_prefix=user_prefix, region=region)
    old_ctx = getattr(_cloud_context, 'ctx', None)
    _cloud_context.ctx = ctx
    try:
        yield ctx
    finally:
        if old_ctx is not None:
            _cloud_context.ctx = old_ctx
        else:
            clear_cloud_prompt_context()


# Section types (same as prompt_handler.py)
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
    "tools_to_use",
)


def _coerce_string_list(value: Any) -> List[str]:
    """Convert any value to a list of strings."""
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
    """Clean section items, ensuring non-empty list."""
    cleaned = ["" if item is None else str(item) for item in items]
    return cleaned if cleaned else [""]


def _normalize_sections(raw_sections: Any, legacy_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize sections from various formats."""
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


def _normalize_prompt(raw: Any, *, source: str, read_only: bool, last_modified_ts: Optional[float] = None) -> Dict[str, Any]:
    """Normalize prompt data to standard format."""
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


class CloudPromptLoader:
    """Load prompts from S3 for cloud worker environments.
    
    Prompt files are named: {prompt_name}_{prompt_id}.json
    e.g., ebay_orders0_pr-92939.json
    
    We search by finding files that contain the prompt_id in the filename.
    """
    
    def __init__(
        self,
        *,
        bucket: str,
        user_prefix: str,
        region: str = "us-east-1",
    ) -> None:
        self.bucket = bucket
        self.user_prefix = user_prefix.rstrip("/")
        self.region = region
        self._client = None
        self._prompt_cache: Dict[str, Dict[str, Any]] = {}  # prompt_id -> normalized prompt
    
    def _get_client(self):
        """Get or create S3 client."""
        if self._client is not None:
            return self._client
        
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:
            raise RuntimeError("boto3 is required for cloud prompt loading") from e
        
        cfg = Config(region_name=self.region, retries={"max_attempts": 3, "mode": "standard"})
        self._client = boto3.client("s3", config=cfg)
        return self._client
    
    def _s3_get_json(self, key: str) -> Optional[Dict[str, Any]]:
        """Get JSON object from S3, returns None if not found."""
        try:
            client = self._get_client()
            obj = client.get_object(Bucket=self.bucket, Key=key)
            body = obj["Body"].read()
            return json.loads(body.decode("utf-8"))
        except Exception as e:
            error_code = getattr(e, 'response', {}).get('Error', {}).get('Code', '')
            if error_code in ('NoSuchKey', '404', 'AccessDenied'):
                return None
            logger.warning(f"[cloud_prompts] Failed to load {key}: {e}")
            return None
    
    def _find_prompt_file_by_id(self, prompt_id: str, prefix: str) -> Optional[str]:
        """
        Find a prompt file by searching for files containing the prompt_id in the filename.
        
        Files are named: {prompt_name}_{prompt_id}.json
        e.g., ebay_orders0_pr-92939.json for prompt_id "pr-92939"
        """
        try:
            client = self._get_client()
            prompts_prefix = f"{prefix}/prompts/"
            
            # List objects in the prompts directory
            paginator = client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prompts_prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    filename = key.split('/')[-1]
                    
                    # Check if filename contains the prompt_id and ends with .json
                    if filename.endswith('.json') and prompt_id in filename:
                        logger.debug(f"[cloud_prompts] Found prompt file: {key}")
                        return key
            
            return None
        except Exception as e:
            logger.warning(f"[cloud_prompts] Error searching for prompt {prompt_id} in {prefix}: {e}")
            return None
    
    def _load_prompt_by_id(self, prompt_id: str, prefix: str, source: str) -> Optional[Dict[str, Any]]:
        """Load a single prompt by ID from S3 by searching filenames."""
        if prompt_id in self._prompt_cache:
            return self._prompt_cache[prompt_id]
        
        # Find the prompt file by searching for filename containing the prompt_id
        prompt_key = self._find_prompt_file_by_id(prompt_id, prefix)
        
        if prompt_key:
            prompt_data = self._s3_get_json(prompt_key)
            if prompt_data:
                normalized = _normalize_prompt(prompt_data, source=source, read_only=(source == "sample_prompts"))
                self._prompt_cache[prompt_id] = normalized
                return normalized
        
        return None
    
    def get_prompt_by_id(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Get a prompt by ID, checking user prompts first, then sample prompts."""
        if not prompt_id:
            return None
        
        # Check cache first
        if prompt_id in self._prompt_cache:
            return self._prompt_cache[prompt_id]
        
        # Try user's prompts first
        prompt = self._load_prompt_by_id(prompt_id, self.user_prefix, source="user_prompts")
        if prompt:
            return prompt
        
        # Fall back to sample prompts (public/prompts/sample_prompts)
        prompt = self._load_prompt_by_id(prompt_id, "public/prompts/sample_prompts", source="sample_prompts")
        if prompt:
            return prompt
        
        logger.warning(f"[cloud_prompts] Prompt not found: {prompt_id}")
        return None


# Global instance for cloud environment (initialized lazily)
_cloud_prompt_loader: Optional[CloudPromptLoader] = None


def get_cloud_prompt_loader(
    bucket: str,
    user_prefix: str,
    region: str = "us-east-1",
) -> CloudPromptLoader:
    """Get or create cloud prompt loader instance."""
    global _cloud_prompt_loader
    
    # Create new instance if params changed or not initialized
    if (
        _cloud_prompt_loader is None
        or _cloud_prompt_loader.bucket != bucket
        or _cloud_prompt_loader.user_prefix != user_prefix
    ):
        _cloud_prompt_loader = CloudPromptLoader(
            bucket=bucket,
            user_prefix=user_prefix,
            region=region,
        )
    
    return _cloud_prompt_loader


def cloud_get_prompt_by_id(prompt_id: str, bucket: str, user_prefix: str, region: str = "us-east-1") -> Optional[Dict[str, Any]]:
    """Convenience function to get a prompt by ID from S3."""
    loader = get_cloud_prompt_loader(bucket=bucket, user_prefix=user_prefix, region=region)
    return loader.get_prompt_by_id(prompt_id)
