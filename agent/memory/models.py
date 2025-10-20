from __future__ import annotations

from dataclasses import dataclass, field
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