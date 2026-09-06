"""
Token Tracker for Skills

Centralized token usage tracking for skill execution.
Records token usage from LLM nodes, browser automation nodes, and MCP tools.
"""

from typing import Optional, Dict, Any
from datetime import datetime
import json
from pathlib import Path

from utils.logger_helper import logger_helper as logger


class TokenTracker:
    """
    Singleton token tracker for recording LLM token usage across skills.
    
    This tracker collects token usage data and stores it in the database
    for cost tracking and usage analytics.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TokenTracker, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._token_service = None
        self._jsonl_path = None
    
    def _get_token_service(self):
        """Lazy load token usage service to avoid circular imports."""
        if self._token_service is None:
            try:
                from app_context import AppContext
                ec_db_mgr = AppContext.get_ec_db_mgr()
                if ec_db_mgr and hasattr(ec_db_mgr, 'token_usage_service'):
                    self._token_service = ec_db_mgr.token_usage_service
                    logger.debug("[TokenTracker] Token usage service initialized")
                else:
                    logger.warning("[TokenTracker] Token usage service not available in ECDBMgr")
            except Exception as e:
                logger.error(f"[TokenTracker] Error getting token service: {e}")
        return self._token_service

    def _get_jsonl_path(self) -> Path:
        """Resolve the token usage booking ledger path lazily."""
        if self._jsonl_path is None:
            try:
                from app_context import AppContext
                ctx = AppContext.get_ctx()
                runlogs_dir = Path(ctx.get_runlogs_dir()) if ctx else Path("runlogs")
            except Exception:
                runlogs_dir = Path("runlogs")
            runlogs_dir.mkdir(parents=True, exist_ok=True)
            self._jsonl_path = runlogs_dir / "token_usage_bookings.jsonl"
        return self._jsonl_path

    def _append_jsonl(self, payload: Dict[str, Any]) -> None:
        """Append one structured usage record to the durable JSONL ledger."""
        try:
            path = self._get_jsonl_path()
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")
        except Exception as e:
            logger.warning(f"[TokenTracker] Failed to append JSONL token ledger: {e}")
    
    def record_llm_usage(
        self,
        response: Any,
        source_type: str = "skill_llm_node",
        source_id: Optional[str] = None,
        source_name: Optional[str] = None,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
        node_type: Optional[str] = "llm",
        metadata: Optional[Dict[str, Any]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        duration_ms: Optional[int] = None,
        skill_name: Optional[str] = None,
    ) -> bool:
        """
        Record token usage from an LLM response.
        
        Args:
            response: LangChain AIMessage or similar response object
            source_type: Type of source (skill_llm_node, skill_browser_node, etc.)
            source_id: Source identifier (skill_id, task_id, etc.)
            source_name: Human-readable source name
            user_email: User email for attribution
            session_id: Session ID if applicable
            node_type: Node type (llm, browser_automation)
            
        Returns:
            bool: True if recorded successfully, False otherwise
        """
        try:
            # Extract token counts from response
            input_tokens, output_tokens, model_name, vendor = self._extract_token_info(response)
            
            if input_tokens == 0 and output_tokens == 0:
                logger.debug("[TokenTracker] No token usage found in response")
                return False
            
            # Calculate cost
            cost_usd = self._calculate_cost(vendor, model_name, input_tokens, output_tokens)
            
            # Get token service
            service = self._get_token_service()
            if not service:
                logger.warning("[TokenTracker] Token service not available, cannot record usage")
                return False
            
            usage_timestamp = datetime.utcnow()

            # Record usage
            usage = service.record_usage(
                source_type=source_type,
                vendor=vendor,
                model=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                source_id=source_id,
                source_name=source_name,
                user_email=user_email,
                session_id=session_id,
                node_type=node_type,
                usage_timestamp=usage_timestamp,
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                skill_name=skill_name
            )

            jsonl_payload = {
                "ts": usage_timestamp.isoformat() + "Z",
                "source_type": source_type,
                "source_id": source_id,
                "source_name": source_name,
                "user_email": user_email,
                "session_id": session_id,
                "node_type": node_type,
                "vendor": vendor,
                "model": model_name,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cost_usd": cost_usd,
                "start_time": start_time.isoformat() + "Z" if start_time else None,
                "end_time": end_time.isoformat() + "Z" if end_time else None,
                "duration_ms": duration_ms,
                "skill_name": skill_name,
                "metadata": metadata or {},
            }
            self._append_jsonl(jsonl_payload)
            
            if usage:
                logger.info(f"[TokenTracker] Recorded: {source_type} - {model_name} - {input_tokens + output_tokens} tokens (${cost_usd:.4f})")
                return True
            else:
                logger.error("[TokenTracker] Failed to record usage")
                return False
                
        except Exception as e:
            logger.error(f"[TokenTracker] Error recording LLM usage: {e}")
            return False
    
    def record_mcp_usage(
        self,
        metadata: Dict[str, Any],
        source_type: str = "mcp_tool",
        source_id: Optional[str] = None,
        source_name: Optional[str] = None,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
        operation: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        duration_ms: Optional[int] = None,
        skill_name: Optional[str] = None
    ) -> bool:
        """
        Record token usage from MCP tool metadata.
        
        Expected metadata format:
        {
            "token_usage": {
                "vendor": "openai",
                "model": "text-embedding-3-small",
                "in_tokens": 1000,
                "out_tokens": 0,
                "cost": 0.0001
            }
        }
        
        Args:
            metadata: Metadata dict containing token_usage
            source_type: Type of source (mcp_rag, mcp_image_gen, etc.)
            source_id: Source identifier
            source_name: Human-readable source name
            user_email: User email for attribution
            session_id: Session ID if applicable
            operation: Operation type (embedding, re-ranking, generation, etc.)
            
        Returns:
            bool: True if recorded successfully, False otherwise
        """
        try:
            # Extract token usage from metadata
            token_usage = metadata.get('token_usage')
            if not token_usage:
                logger.debug("[TokenTracker] No token_usage in metadata")
                return False
            
            vendor = token_usage.get('vendor', 'unknown')
            model = token_usage.get('model', 'unknown')
            input_tokens = int(token_usage.get('in_tokens', 0))
            output_tokens = int(token_usage.get('out_tokens', 0))
            cost_usd = float(token_usage.get('cost', 0.0))
            
            if input_tokens == 0 and output_tokens == 0:
                logger.debug("[TokenTracker] No tokens in metadata")
                return False
            
            # Get token service
            service = self._get_token_service()
            if not service:
                logger.warning("[TokenTracker] Token service not available, cannot record usage")
                return False
            
            usage_timestamp = datetime.utcnow()

            # Record usage
            usage = service.record_usage(
                source_type=source_type,
                vendor=vendor,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                source_id=source_id,
                source_name=source_name,
                user_email=user_email,
                session_id=session_id,
                operation=operation,
                usage_timestamp=usage_timestamp,
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                skill_name=skill_name
            )

            jsonl_payload = {
                "ts": usage_timestamp.isoformat() + "Z",
                "source_type": source_type,
                "source_id": source_id,
                "source_name": source_name,
                "user_email": user_email,
                "session_id": session_id,
                "node_type": None,
                "operation": operation,
                "vendor": vendor,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cost_usd": cost_usd,
                "start_time": start_time.isoformat() + "Z" if start_time else None,
                "end_time": end_time.isoformat() + "Z" if end_time else None,
                "duration_ms": duration_ms,
                "skill_name": skill_name,
                "metadata": metadata or {},
            }
            self._append_jsonl(jsonl_payload)
            
            if usage:
                logger.info(f"[TokenTracker] Recorded MCP: {source_type} - {model} - {input_tokens + output_tokens} tokens (${cost_usd:.4f})")
                return True
            else:
                logger.error("[TokenTracker] Failed to record MCP usage")
                return False
                
        except Exception as e:
            logger.error(f"[TokenTracker] Error recording MCP usage: {e}")
            return False
    
    def _extract_token_info(self, response: Any) -> tuple:
        """
        Extract token information from LangChain response.
        
        Returns:
            tuple: (input_tokens, output_tokens, model_name, vendor)
        """
        input_tokens = 0
        output_tokens = 0
        model_name = "unknown"
        vendor = "unknown"
        
        try:
            # Try usage_metadata first (langchain-core >= 0.2)
            usage = getattr(response, "usage_metadata", None)
            if isinstance(usage, dict):
                input_tokens = usage.get("input_tokens", 0) or 0
                output_tokens = usage.get("output_tokens", 0) or 0

            # Raw OpenAI-style response objects expose .usage with prompt/completion tokens.
            if input_tokens == 0 and output_tokens == 0:
                raw_usage = getattr(response, "usage", None)
                if raw_usage is not None:
                    input_tokens = (
                        getattr(raw_usage, "prompt_tokens", 0)
                        or getattr(raw_usage, "input_tokens", 0)
                        or 0
                    )
                    output_tokens = (
                        getattr(raw_usage, "completion_tokens", 0)
                        or getattr(raw_usage, "output_tokens", 0)
                        or 0
                    )
            
            # Fallback to response_metadata.token_usage
            resp_meta = getattr(response, "response_metadata", None) or {}
            if input_tokens == 0 and output_tokens == 0:
                token_usage = resp_meta.get("token_usage") or resp_meta.get("usage") or {}
                if isinstance(token_usage, dict):
                    input_tokens = token_usage.get("prompt_tokens", 0) or token_usage.get("input_tokens", 0) or 0
                    output_tokens = token_usage.get("completion_tokens", 0) or token_usage.get("output_tokens", 0) or 0
            
            # Always extract model name from response_metadata
            model_name = resp_meta.get("model_name", "") or resp_meta.get("model", "") or "unknown"
            if model_name == "unknown":
                model_name = getattr(response, "model", "") or getattr(response, "model_name", "") or "unknown"
            
            # Determine vendor from model name
            vendor = self._determine_vendor(model_name)
            
        except Exception as e:
            logger.error(f"[TokenTracker] Error extracting token info: {e}")
        
        return input_tokens, output_tokens, model_name, vendor
    
    def _determine_vendor(self, model_name: str) -> str:
        """Determine vendor from model name."""
        model_lower = model_name.lower()
        if 'gpt' in model_lower or 'o1' in model_lower or 'o3' in model_lower or 'o4' in model_lower or 'davinci' in model_lower:
            return 'openai'
        elif 'claude' in model_lower:
            return 'anthropic'
        elif 'deepseek' in model_lower:
            return 'deepseek'
        elif 'gemini' in model_lower or 'palm' in model_lower:
            return 'google'
        elif 'llama' in model_lower or 'mistral' in model_lower or 'qwen' in model_lower:
            return 'ollama'
        else:
            return 'unknown'
    
    def _calculate_cost(self, vendor: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD. Pricing is the single source of truth in
        agent/ec_skills/llm_pricing.py (shared with the billing handlers)."""
        from agent.ec_skills.llm_pricing import calc_cost
        return calc_cost(vendor, model, input_tokens, output_tokens)


# Global singleton instance
token_tracker = TokenTracker()
