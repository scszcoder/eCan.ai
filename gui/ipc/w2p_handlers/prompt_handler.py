"""
Prompt handlers: CRUD over IPC (in-memory persistence for app session)
"""
from typing import Any, Optional, Dict, List
from gui.ipc.types import IPCRequest, IPCResponse, create_success_response, create_error_response
from gui.ipc.registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger

# In-memory prompts
PROMPTS: List[Dict[str, Any]] = [
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

@IPCHandlerRegistry.handler('get_prompts')
def handle_get_prompts(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    try:
        return create_success_response(request, {"prompts": PROMPTS})
    except Exception as e:
        logger.error(f"[prompts] get_prompts error: {e}")
        return create_error_response(request, 'GET_PROMPTS_ERROR', str(e))

@IPCHandlerRegistry.handler('save_prompt')
def handle_save_prompt(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    try:
        prompt = (params or {}).get('prompt')
        if not prompt or not isinstance(prompt, dict) or not prompt.get('id'):
            return create_error_response(request, 'INVALID_PARAMS', 'prompt with id is required')
        pid = prompt['id']
        idx = next((i for i, p in enumerate(PROMPTS) if p.get('id') == pid), None)
        if idx is None:
            PROMPTS.insert(0, prompt)
        else:
            PROMPTS[idx] = prompt
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
        before = len(PROMPTS)
        PROMPTS[:] = [p for p in PROMPTS if p.get('id') != pid]
        deleted = len(PROMPTS) != before
        return create_success_response(request, {"deleted": deleted})
    except Exception as e:
        logger.error(f"[prompts] delete_prompt error: {e}")
        return create_error_response(request, 'DELETE_PROMPT_ERROR', str(e))
