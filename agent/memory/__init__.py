"""
Agent Memory Module - Layered memory system for agentic AI.

This module provides:
1. Working Memory - In-session context (via state/ContextBuilder)
2. Episodic Memory - Session records and action history
3. Semantic Memory - RAG-stored knowledge from reflections

Components:
- models.py: Data schemas (ActionRecord, SessionRecord, DailyReflection)
- service.py: MemoryManager with Chroma vector store
- episodic_store.py: Persistent session storage
- reflection.py: LLM-based daily reflection and knowledge synthesis
- embedding_utils.py: Embedding factory utilities

Usage:
    # Record a session
    from agent.memory import SessionRecorder, EpisodicStore
    
    recorder = SessionRecorder(agent_id="my_agent", task="Do something")
    # ... agent runs with recorder as history_recorder ...
    recorder.finalize(success=True)
    recorder.save()
    
    # Generate daily reflection
    from agent.memory import ReflectionEngine
    
    engine = ReflectionEngine(llm=my_llm, rag_client=my_rag)
    reflection = await engine.run_daily_reflection()
    
    # Query past sessions
    store = EpisodicStore()
    sessions = store.load_sessions_for_date("2024-12-14")
"""

# Models
from agent.memory.models import (
    MemoryNamespaces,
    MemoryItem,
    RetrievalQuery,
    RetrievedMemory,
    # Agentic memory schemas
    ActionRecord,
    SessionRecord,
    DailyReflection,
)

# Service
from agent.memory.service import (
    MemoryManager,
    MemorySettings,
)

# Episodic Store
from agent.memory.episodic_store import (
    EpisodicStore,
    SessionRecorder,
)

# Reflection
from agent.memory.reflection import (
    ReflectionEngine,
    run_daily_reflection,
)

__all__ = [
    # Models
    "MemoryNamespaces",
    "MemoryItem",
    "RetrievalQuery",
    "RetrievedMemory",
    "ActionRecord",
    "SessionRecord",
    "DailyReflection",
    # Service
    "MemoryManager",
    "MemorySettings",
    # Episodic Store
    "EpisodicStore",
    "SessionRecorder",
    # Reflection
    "ReflectionEngine",
    "run_daily_reflection",
]
