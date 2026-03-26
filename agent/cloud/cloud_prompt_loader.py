"""Cloud-compatible prompt loader for DynamoDB-based prompts.

This module provides prompt loading functionality that works in cloud environments
without requiring PySide6 or local filesystem access.

Structure in DynamoDB (Agent_Prompts table):
- Primary Key: owner_id (HASH) + agent_id (RANGE)
- agent_id format: "any~{prompt_id}" for prompts accessible to any agent
- prompt_id: The unique prompt ID (e.g., "pr-848556")
- prompt: JSON string containing the prompt data
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

# Default DynamoDB table name for prompts
DEFAULT_PROMPTS_TABLE = "Agent_Prompts"


@dataclass
class CloudPromptContext:
    """Context for cloud prompt loading."""
    owner_id: str  # User ID (e.g., "songc_yahoo_com")
    region: str = "us-east-1"
    table_name: str = DEFAULT_PROMPTS_TABLE


def set_cloud_prompt_context(owner_id: str, region: str = "us-east-1", table_name: str = DEFAULT_PROMPTS_TABLE) -> None:
    """Set the cloud prompt context for the current thread."""
    _cloud_context.ctx = CloudPromptContext(owner_id=owner_id, region=region, table_name=table_name)
    logger.debug(f"[cloud_prompts] Set context: owner_id={owner_id}, table={table_name}")


def get_cloud_prompt_context() -> Optional[CloudPromptContext]:
    """Get the cloud prompt context for the current thread."""
    return getattr(_cloud_context, 'ctx', None)


def clear_cloud_prompt_context() -> None:
    """Clear the cloud prompt context."""
    if hasattr(_cloud_context, 'ctx'):
        delattr(_cloud_context, 'ctx')


@contextmanager
def cloud_prompt_context(owner_id: str, region: str = "us-east-1", table_name: str = DEFAULT_PROMPTS_TABLE) -> Generator[CloudPromptContext, None, None]:
    """Context manager for cloud prompt loading."""
    ctx = CloudPromptContext(owner_id=owner_id, region=region, table_name=table_name)
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
    
    # Preserve format and mdContent for markdown-mode prompts
    fmt = data.get("format")
    if fmt in ("json", "md"):
        prompt["format"] = fmt
    md_content = data.get("mdContent")
    if md_content:
        prompt["mdContent"] = str(md_content)
        logger.info(f"[cloud_prompts] ✅ Preserved mdContent for prompt '{prompt.get('id')}' ({len(str(md_content))} chars)")
        logger.debug(f"[cloud_prompts] mdContent preview: {str(md_content)[:200]}...")
    else:
        logger.debug(f"[cloud_prompts] No mdContent for prompt '{prompt.get('id')}', will use sections")

    return prompt


class CloudPromptLoader:
    """Load prompts from DynamoDB for cloud worker environments.
    
    DynamoDB table schema (Agent_Prompts):
    - Primary Key: owner_id (HASH) + agent_id (RANGE)
    - agent_id format: "any~{prompt_id}" for prompts accessible to any agent
    - prompt_id: The unique prompt ID (e.g., "pr-848556")
    - prompt: JSON string containing the prompt data
    """
    
    def __init__(
        self,
        *,
        owner_id: str,
        region: str = "us-east-1",
        table_name: str = DEFAULT_PROMPTS_TABLE,
    ) -> None:
        self.owner_id = owner_id
        self.region = region
        self.table_name = table_name
        self._client = None
        self._prompt_cache: Dict[str, Dict[str, Any]] = {}  # prompt_id -> normalized prompt
    
    def _get_client(self):
        """Get or create DynamoDB client."""
        if self._client is not None:
            return self._client
        
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:
            raise RuntimeError("boto3 is required for cloud prompt loading") from e
        
        cfg = Config(region_name=self.region, retries={"max_attempts": 3, "mode": "standard"})
        self._client = boto3.client("dynamodb", config=cfg)
        return self._client
    
    def _get_prompt_from_dynamodb(self, owner_id: str, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Get a prompt from DynamoDB by owner_id and prompt_id."""
        try:
            client = self._get_client()
            # agent_id format is "any~{prompt_id}"
            agent_id = f"any~{prompt_id}"
            
            response = client.get_item(
                TableName=self.table_name,
                Key={
                    "owner_id": {"S": owner_id},
                    "agent_id": {"S": agent_id}
                }
            )
            
            item = response.get("Item")
            if not item:
                logger.debug(f"[cloud_prompts] Prompt not found in DynamoDB: owner={owner_id}, prompt_id={prompt_id}")
                return None
            
            # Parse the prompt JSON string
            prompt_str = item.get("prompt", {}).get("S", "{}")
            prompt_data = json.loads(prompt_str)
            
            # Add id if not present (use prompt_id from the record)
            if "id" not in prompt_data:
                prompt_data["id"] = item.get("prompt_id", {}).get("S", prompt_id)
            
            logger.info(f"[cloud_prompts] 📥 Found prompt in DynamoDB: owner={owner_id}, prompt_id={prompt_id}")
            logger.debug(f"[cloud_prompts] Raw data has mdContent: {bool(prompt_data.get('mdContent'))}, has sections: {bool(prompt_data.get('sections'))}")
            if prompt_data.get('mdContent'):
                logger.debug(f"[cloud_prompts] mdContent preview from DynamoDB: {str(prompt_data['mdContent'])[:200]}...")
            if prompt_data.get('sections'):
                logger.debug(f"[cloud_prompts] sections count from DynamoDB: {len(prompt_data['sections'])}")
                if prompt_data['sections']:
                    logger.warning(f"[cloud_prompts] First section type: {prompt_data['sections'][0].get('type')}")
            
            return prompt_data
            
        except Exception as e:
            error_code = getattr(e, 'response', {}).get('Error', {}).get('Code', '')
            if error_code in ('ResourceNotFoundException', 'ValidationException'):
                logger.debug(f"[cloud_prompts] DynamoDB error: {error_code}")
                return None
            logger.warning(f"[cloud_prompts] Failed to load prompt {prompt_id} from DynamoDB: {e}")
            return None
    
    def _load_prompt_by_id(self, prompt_id: str, owner_id: str, source: str) -> Optional[Dict[str, Any]]:
        """Load a single prompt by ID from DynamoDB."""
        if prompt_id in self._prompt_cache:
            return self._prompt_cache[prompt_id]
        
        prompt_data = self._get_prompt_from_dynamodb(owner_id, prompt_id)
        
        if prompt_data:
            normalized = _normalize_prompt(prompt_data, source=source, read_only=(source == "sample_prompts"))
            self._prompt_cache[prompt_id] = normalized
            return normalized
        
        return None
    
    def get_prompt_by_id(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Get a prompt by ID, checking user prompts first, then sample/public prompts."""
        if not prompt_id:
            return None
        
        # Check cache first
        if prompt_id in self._prompt_cache:
            return self._prompt_cache[prompt_id]
        
        # Try user's prompts first
        prompt = self._load_prompt_by_id(prompt_id, self.owner_id, source="user_prompts")
        if prompt:
            return prompt
        
        # Fall back to public/sample prompts (stored with owner_id "public")
        prompt = self._load_prompt_by_id(prompt_id, "public", source="sample_prompts")
        if prompt:
            return prompt
        
        logger.warning(f"[cloud_prompts] Prompt not found: {prompt_id}")
        return None


# Global instance for cloud environment (initialized lazily)
_cloud_prompt_loader: Optional[CloudPromptLoader] = None


def get_cloud_prompt_loader(
    owner_id: str,
    region: str = "us-east-1",
    table_name: str = DEFAULT_PROMPTS_TABLE,
) -> CloudPromptLoader:
    """Get or create cloud prompt loader instance."""
    global _cloud_prompt_loader
    
    # Create new instance if params changed or not initialized
    if (
        _cloud_prompt_loader is None
        or _cloud_prompt_loader.owner_id != owner_id
        or _cloud_prompt_loader.table_name != table_name
    ):
        _cloud_prompt_loader = CloudPromptLoader(
            owner_id=owner_id,
            region=region,
            table_name=table_name,
        )
    
    return _cloud_prompt_loader


def cloud_get_prompt_by_id(prompt_id: str, owner_id: str, region: str = "us-east-1", table_name: str = DEFAULT_PROMPTS_TABLE) -> Optional[Dict[str, Any]]:
    """Convenience function to get a prompt by ID from DynamoDB."""
    loader = get_cloud_prompt_loader(owner_id=owner_id, region=region, table_name=table_name)
    return loader.get_prompt_by_id(prompt_id)

