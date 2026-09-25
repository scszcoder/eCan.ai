"""
Token Usage Model

Tracks LLM token usage across all components:
- Skills (LLM nodes, browser_automation nodes)
- MCP tools (RAG embedding/re-ranking, image/video generation)
- Skill editor usage
"""

from sqlalchemy import Column, String, Integer, Float, DateTime, Index
from datetime import datetime
from .base_model import BaseModel


class TokenUsage(BaseModel):
    """
    Token usage tracking model.
    
    Records token consumption from various sources with metadata
    for cost calculation and usage analytics.
    """
    __tablename__ = 'token_usage'
    
    # Source information
    source_type = Column(String, nullable=False, comment="Source type: skill_llm_node, skill_browser_node, mcp_rag, mcp_image_gen, mcp_video_gen, skill_editor")
    source_id = Column(String, nullable=True, comment="Source identifier (skill_id, task_id, etc.)")
    source_name = Column(String, nullable=True, comment="Human-readable source name")
    
    # User/session information
    user_email = Column(String, nullable=True, comment="User email for attribution")
    session_id = Column(String, nullable=True, comment="Session ID if applicable")
    
    # Model information
    vendor = Column(String, nullable=False, comment="LLM vendor: openai, anthropic, azure, deepseek, ollama, etc.")
    model = Column(String, nullable=False, comment="Model name: gpt-4, claude-3-opus, etc.")
    
    # Token counts
    input_tokens = Column(Integer, nullable=False, default=0, comment="Input/prompt tokens")
    output_tokens = Column(Integer, nullable=False, default=0, comment="Output/completion tokens")
    total_tokens = Column(Integer, nullable=False, default=0, comment="Total tokens (input + output)")
    
    # Cost information
    cost_usd = Column(Float, nullable=False, default=0.0, comment="Calculated cost in USD")
    
    # Timestamp (usage time, not created_at)
    usage_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, comment="When the tokens were used")
    
    # Additional metadata
    node_type = Column(String, nullable=True, comment="For skills: node type (llm, browser_automation)")
    operation = Column(String, nullable=True, comment="Operation type: embedding, re-ranking, generation, chat, etc.")

    # Fine-grained timing
    start_time = Column(DateTime, nullable=True, comment="LLM call start time (ms precision)")
    end_time = Column(DateTime, nullable=True, comment="LLM call end time (ms precision)")
    duration_ms = Column(Integer, nullable=True, comment="Duration in milliseconds")

    # Skill name for analytics grouping
    skill_name = Column(String, nullable=True, comment="Skill name for per-skill analytics")

    # Store / run attribution. source_id holds whatever the call site happened
    # to pass (a skill id here, a task id there) and user_email is one customer
    # across all of their stores, so neither can answer "what did THIS store
    # cost?". These mirror the same three columns on usage_event, so cost and
    # outcome join on one dimension: cost per delivered reply, per store.
    store_id = Column(String, nullable=True, comment="Store this usage belongs to (NULL = recorded before stores were distinguished)")
    agent_id = Column(String, nullable=True, comment="Agent that made the call")
    task_id = Column(String, nullable=True, comment="Task the call ran under")

    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_token_usage_timestamp', 'usage_timestamp'),
        Index('idx_token_usage_user', 'user_email'),
        Index('idx_token_usage_source', 'source_type', 'source_id'),
        Index('idx_token_usage_model', 'vendor', 'model'),
        Index('idx_token_usage_month', 'usage_timestamp'),  # For monthly aggregation
        Index('idx_token_usage_skill', 'skill_name'),
        Index('idx_token_usage_store', 'store_id'),
        Index('idx_token_usage_agent', 'agent_id'),
        Index('idx_token_usage_task', 'task_id'),
    )
    
    def __repr__(self):
        return f"<TokenUsage(id='{self.id}', source='{self.source_type}', model='{self.model}', tokens={self.total_tokens}, cost=${self.cost_usd:.4f})>"
