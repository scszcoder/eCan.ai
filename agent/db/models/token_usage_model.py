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
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_token_usage_timestamp', 'usage_timestamp'),
        Index('idx_token_usage_user', 'user_email'),
        Index('idx_token_usage_source', 'source_type', 'source_id'),
        Index('idx_token_usage_model', 'vendor', 'model'),
        Index('idx_token_usage_month', 'usage_timestamp'),  # For monthly aggregation
    )
    
    def __repr__(self):
        return f"<TokenUsage(id='{self.id}', source='{self.source_type}', model='{self.model}', tokens={self.total_tokens}, cost=${self.cost_usd:.4f})>"
