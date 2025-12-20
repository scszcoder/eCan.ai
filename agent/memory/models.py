from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, List, Tuple
from pydantic import BaseModel


class MemoryNamespaces:
    """Common logical namespaces for routing memories.
    Adjust/extend as needed by skills/tasks.
    """
    DEFAULT = "default"
    CHAT = "chat"
    TASK = "task"
    DOCS = "docs"
    # New namespaces for agentic memory
    EPISODIC = "episodic"       # Session records
    PROCEDURAL = "procedural"   # Learned procedures/patterns
    SEMANTIC = "semantic"       # RAG-stored knowledge
    REFLECTION = "reflection"   # Daily reflections


# =============================================================================
# Agentic Memory Schemas
# =============================================================================

@dataclass
class ActionRecord:
    """A single action taken by an agent during a session.
    
    Captures the full context of what happened at each step.
    """
    timestamp: datetime
    session_id: str
    step_number: int
    action_type: str              # "browser_action", "tool_call", "llm_response"
    action_name: str              # "click", "input_text", "navigate", etc.
    action_input: Dict[str, Any] = field(default_factory=dict)
    action_output: Any = None
    success: bool = True
    error: Optional[str] = None
    url: Optional[str] = None
    page_title: Optional[str] = None
    thinking: Optional[str] = None      # LLM's reasoning
    next_goal: Optional[str] = None
    duration_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "session_id": self.session_id,
            "step_number": self.step_number,
            "action_type": self.action_type,
            "action_name": self.action_name,
            "action_input": self.action_input,
            "action_output": str(self.action_output) if self.action_output else None,
            "success": self.success,
            "error": self.error,
            "url": self.url,
            "page_title": self.page_title,
            "thinking": self.thinking,
            "next_goal": self.next_goal,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionRecord":
        """Create from dictionary."""
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        elif ts is None:
            ts = datetime.now()
        return cls(
            timestamp=ts,
            session_id=data.get("session_id", ""),
            step_number=data.get("step_number", 0),
            action_type=data.get("action_type", "unknown"),
            action_name=data.get("action_name", "unknown"),
            action_input=data.get("action_input", {}),
            action_output=data.get("action_output"),
            success=data.get("success", True),
            error=data.get("error"),
            url=data.get("url"),
            page_title=data.get("page_title"),
            thinking=data.get("thinking"),
            next_goal=data.get("next_goal"),
            duration_ms=data.get("duration_ms", 0),
            metadata=data.get("metadata", {}),
        )
    
    def to_text(self) -> str:
        """Convert to text for embedding/RAG storage."""
        parts = [
            f"Step {self.step_number}: {self.action_name}",
        ]
        if self.url:
            parts.append(f"URL: {self.url}")
        if self.thinking:
            parts.append(f"Thinking: {self.thinking}")
        if self.next_goal:
            parts.append(f"Goal: {self.next_goal}")
        if self.error:
            parts.append(f"Error: {self.error}")
        elif self.success:
            parts.append("Result: Success")
        return " | ".join(parts)


@dataclass
class SessionRecord:
    """A complete session/task execution record.
    
    Contains all actions taken during a single task execution.
    """
    session_id: str
    agent_id: str
    task: str
    start_time: datetime
    end_time: Optional[datetime] = None
    success: Optional[bool] = None
    final_result: Optional[str] = None
    actions: List[ActionRecord] = field(default_factory=list)
    urls_visited: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    token_usage: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "task": self.task,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "success": self.success,
            "final_result": self.final_result,
            "actions": [a.to_dict() for a in self.actions],
            "urls_visited": self.urls_visited,
            "errors": self.errors,
            "token_usage": self.token_usage,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionRecord":
        """Create from dictionary."""
        start = data.get("start_time")
        end = data.get("end_time")
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.fromisoformat(end)
        
        actions = [ActionRecord.from_dict(a) for a in data.get("actions", [])]
        
        return cls(
            session_id=data.get("session_id", ""),
            agent_id=data.get("agent_id", ""),
            task=data.get("task", ""),
            start_time=start or datetime.now(),
            end_time=end,
            success=data.get("success"),
            final_result=data.get("final_result"),
            actions=actions,
            urls_visited=data.get("urls_visited", []),
            errors=data.get("errors", []),
            token_usage=data.get("token_usage", {}),
            metadata=data.get("metadata", {}),
        )
    
    def to_summary_text(self) -> str:
        """Convert to summary text for embedding."""
        status = "✓ Success" if self.success else "✗ Failed"
        parts = [
            f"Task: {self.task}",
            f"Status: {status}",
            f"Steps: {len(self.actions)}",
        ]
        if self.final_result:
            parts.append(f"Result: {self.final_result[:200]}")
        if self.errors:
            parts.append(f"Errors: {', '.join(self.errors[:3])}")
        if self.urls_visited:
            parts.append(f"Sites: {', '.join(self.urls_visited[:5])}")
        return " | ".join(parts)
    
    def add_action(self, action: ActionRecord) -> None:
        """Add an action to the session."""
        self.actions.append(action)
        if action.url and action.url not in self.urls_visited:
            self.urls_visited.append(action.url)
        if action.error and action.error not in self.errors:
            self.errors.append(action.error)


@dataclass
class DailyReflection:
    """Daily reflection synthesized from session records.
    
    Contains lessons learned, patterns, and knowledge to be RAG-stored.
    """
    date: str                           # YYYY-MM-DD
    agent_id: str
    sessions_reviewed: List[str] = field(default_factory=list)
    total_sessions: int = 0
    successful_sessions: int = 0
    failed_sessions: int = 0
    
    # Synthesized insights
    successes: List[str] = field(default_factory=list)      # What worked well
    failures: List[str] = field(default_factory=list)       # What failed and why
    patterns: List[str] = field(default_factory=list)       # Recurring patterns
    lessons: List[str] = field(default_factory=list)        # Key takeaways
    improvements: List[str] = field(default_factory=list)   # Suggested improvements
    
    # Knowledge chunks for RAG storage
    knowledge_chunks: List[str] = field(default_factory=list)
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "date": self.date,
            "agent_id": self.agent_id,
            "sessions_reviewed": self.sessions_reviewed,
            "total_sessions": self.total_sessions,
            "successful_sessions": self.successful_sessions,
            "failed_sessions": self.failed_sessions,
            "successes": self.successes,
            "failures": self.failures,
            "patterns": self.patterns,
            "lessons": self.lessons,
            "improvements": self.improvements,
            "knowledge_chunks": self.knowledge_chunks,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DailyReflection":
        """Create from dictionary."""
        return cls(
            date=data.get("date", ""),
            agent_id=data.get("agent_id", ""),
            sessions_reviewed=data.get("sessions_reviewed", []),
            total_sessions=data.get("total_sessions", 0),
            successful_sessions=data.get("successful_sessions", 0),
            failed_sessions=data.get("failed_sessions", 0),
            successes=data.get("successes", []),
            failures=data.get("failures", []),
            patterns=data.get("patterns", []),
            lessons=data.get("lessons", []),
            improvements=data.get("improvements", []),
            knowledge_chunks=data.get("knowledge_chunks", []),
            metadata=data.get("metadata", {}),
        )
    
    def to_text(self) -> str:
        """Convert to text for storage/display."""
        parts = [
            f"Daily Reflection: {self.date}",
            f"Sessions: {self.total_sessions} ({self.successful_sessions} success, {self.failed_sessions} failed)",
        ]
        if self.lessons:
            parts.append(f"Lessons: {'; '.join(self.lessons[:5])}")
        if self.patterns:
            parts.append(f"Patterns: {'; '.join(self.patterns[:3])}")
        return " | ".join(parts)


# =============================================================================
# Original Memory Models (preserved)
# =============================================================================

@dataclass
class MemoryItem:
    """A single memory item to be stored in the vector DB.

    - text: primary text content for embedding and retrieval
    - metadata: arbitrary metadata (agent/task/chat ids, timestamps, types, etc.)
    - namespace: logical partition, maps to a vector collection space
    - id: optional stable id for upserts
    """
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    namespace: Tuple[str, ...] = (MemoryNamespaces.DEFAULT,)
    id: Optional[str] = None


class RetrievalQuery(BaseModel):
    """Query model for retrieval requests."""
    query: str
    k: int = 5
    namespace: Tuple[str, ...] = (MemoryNamespaces.DEFAULT,)
    filters: Optional[Dict[str, Any]] = None


class RetrievedMemory(BaseModel):
    """Standardized return structure for retrieved memories."""
    id: Optional[str] = None
    text: str
    score: float
    metadata: Dict[str, Any] = {}