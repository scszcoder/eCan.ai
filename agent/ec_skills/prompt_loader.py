"""
Utility functions for loading and constructing prompts from saved prompt files.
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any
from utils.logger_helper import logger_helper as logger
from utils.user_path_helper import get_user_data_dir

# Define prompt directories
PROJECT_ROOT = Path(__file__).resolve().parents[2]
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

def load_prompt_by_id(prompt_id: str) -> Optional[Dict[str, Any]]:
    """
    Load a prompt JSON file by its ID from my_prompts or sample_prompts directories.
    
    Args:
        prompt_id: The ID of the prompt to load
        
    Returns:
        The prompt data dictionary if found, None otherwise
    """
    if not prompt_id or prompt_id == "in-line":
        return None

    # Search in my_prompts first
    for directory in [_get_my_prompts_dir(), SAMPLE_PROMPTS_DIR]:
        if not directory.exists():
            continue
            
        for file_path in directory.glob("*.json"):
            try:
                with file_path.open("r", encoding="utf-8") as fp:
                    data = json.load(fp)
                if isinstance(data, dict) and data.get("id") == prompt_id:
                    logger.debug(f"[prompt_loader] Loaded prompt {prompt_id} from {file_path}")
                    return data
            except Exception as exc:
                logger.warning(f"[prompt_loader] Failed to load {file_path.name}: {exc}")
    
    logger.warning(f"[prompt_loader] Prompt with ID '{prompt_id}' not found")
    return None


def construct_prompt_from_data(prompt_data: Dict[str, Any]) -> str:
    """
    Construct a prompt string from prompt data (mdContent or sections and humanInputs).
    
    Prioritizes mdContent if present (markdown mode), otherwise uses sections (JSON mode).
    
    Args:
        prompt_data: Dictionary containing prompt sections and humanInputs
        
    Returns:
        Constructed prompt string
    """
    if not prompt_data:
        return ""
    
    # If mdContent exists and is not empty, use it directly (markdown mode)
    md_content = prompt_data.get("mdContent", "").strip()
    if md_content:
        logger.warning(f"[prompt_loader] ✅ Using mdContent for prompt (markdown mode)")
        logger.warning(f"[prompt_loader] mdContent length: {len(md_content)} chars")
        logger.warning(f"[prompt_loader] mdContent preview: {md_content[:200]}...")
        return md_content
    
    # Otherwise, construct from sections (JSON mode)
    logger.warning(f"[prompt_loader] ⚠️ No mdContent, constructing from sections (JSON mode)")
    logger.warning(f"[prompt_loader] Sections count: {len(prompt_data.get('sections', []))}")
    lines = []
    
    # Add title if present
    title = prompt_data.get("title", "").strip()
    if title:
        lines.append(f"# {title}")
        lines.append("")
    
    # Process sections
    sections = prompt_data.get("sections", [])
    if sections:
        for section in sections:
            if not isinstance(section, dict):
                continue
            
            section_type = section.get("type", "")
            items = section.get("items", [])
            
            if not items:
                continue
            
            # Add section header
            section_labels = {
                "role": "Role / Character",
                "tone": "Tone",
                "background": "Background",
                "goals": "Goals",
                "guidelines": "Guidelines",
                "rules": "Rules",
                "instructions": "Instructions",
                "examples": "Examples",
                "variables": "Variables",
            }
            label = section_labels.get(section_type, section_type.title())
            lines.append(f"{label}:")
            
            # Add items
            for item in items:
                item_str = str(item).strip()
                if not item_str:
                    continue
                
                # Some sections use bullet points, others don't
                if section_type in ["role", "tone", "background"]:
                    lines.append(item_str)
                else:
                    lines.append(f"- {item_str}")
            
            lines.append("")  # Empty line between sections
    
    # Add human inputs section if present
    human_inputs = prompt_data.get("humanInputs", [])
    if human_inputs:
        lines.append("Human Inputs:")
        for inp in human_inputs:
            inp_str = str(inp).strip()
            if inp_str:
                lines.append(f"- {inp_str}")
        lines.append("")
    
    return "\n".join(lines).strip()


def get_prompt_content(prompt_id: Optional[str], inline_content: Optional[str] = None) -> str:
    """
    Get prompt content either from a saved prompt file or from inline content.
    
    Args:
        prompt_id: The ID of the saved prompt, or "in-line" for inline content
        inline_content: The inline prompt content to use if prompt_id is "in-line" or None
        
    Returns:
        The prompt content string
    """
    # If no prompt_id or it's "in-line", use inline content
    if not prompt_id or prompt_id == "in-line":
        return inline_content or ""
    
    # Try to load from saved prompt
    prompt_data = load_prompt_by_id(prompt_id)
    if prompt_data:
        return construct_prompt_from_data(prompt_data)
    
    # Fallback to inline content if prompt not found
    logger.warning(f"[prompt_loader] Prompt ID '{prompt_id}' not found, using inline content")
    return inline_content or ""
