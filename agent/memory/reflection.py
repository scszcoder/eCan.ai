"""
Reflection Module - LLM-based daily reflection and knowledge synthesis.

Analyzes session records to extract patterns, lessons, and knowledge chunks
that are then stored in RAG for future retrieval.

Usage:
    from agent.memory.reflection import ReflectionEngine
    
    engine = ReflectionEngine(llm=my_llm, rag_client=my_rag)
    
    # Generate reflection for today
    reflection = await engine.generate_daily_reflection()
    
    # Or for a specific date
    reflection = await engine.generate_daily_reflection(date_str="2024-12-14")
    
    # Store knowledge in RAG
    await engine.store_knowledge_to_rag(reflection)
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from utils.logger_helper import logger_helper as logger
from agent.memory.models import SessionRecord, DailyReflection
from agent.memory.episodic_store import EpisodicStore


# =============================================================================
# Reflection Prompts
# =============================================================================

REFLECTION_SYSTEM_PROMPT = """You are an AI agent's reflection system. Your job is to analyze the agent's daily work sessions and extract valuable insights.

You will receive summaries of sessions the agent completed today. Analyze them to identify:
1. **Successes**: What worked well? What strategies were effective?
2. **Failures**: What went wrong? What caused errors?
3. **Patterns**: Are there recurring behaviors, common obstacles, or repeated strategies?
4. **Lessons**: What should the agent remember for future tasks?
5. **Improvements**: What could be done better next time?

Be specific and actionable. Focus on insights that will help the agent perform better in the future."""

REFLECTION_USER_PROMPT = """Analyze the following {session_count} sessions from {date}:

{sessions_text}

---

Based on these sessions, provide a structured reflection with:

1. SUCCESSES (list 2-5 things that worked well):
2. FAILURES (list any failures and their causes):
3. PATTERNS (list recurring patterns you noticed):
4. LESSONS (list 3-5 key takeaways for future tasks):
5. IMPROVEMENTS (list suggestions for doing better):
6. KNOWLEDGE (list 3-5 factual knowledge chunks to remember, formatted as standalone statements):

Format your response as JSON:
{{
    "successes": ["...", "..."],
    "failures": ["...", "..."],
    "patterns": ["...", "..."],
    "lessons": ["...", "..."],
    "improvements": ["...", "..."],
    "knowledge_chunks": ["...", "..."]
}}"""


# =============================================================================
# Reflection Engine
# =============================================================================

class ReflectionEngine:
    """
    Generates daily reflections from session records using LLM.
    
    Workflow:
    1. Load sessions for the day
    2. Format sessions into text summaries
    3. Send to LLM for analysis
    4. Parse response into DailyReflection
    5. Store reflection and knowledge chunks
    """
    
    def __init__(
        self,
        llm = None,
        rag_client = None,
        episodic_store: EpisodicStore | None = None,
        agent_id: str = "default",
    ):
        """
        Initialize reflection engine.
        
        Args:
            llm: LangChain-compatible LLM for reflection
            rag_client: RAG client for storing knowledge (e.g., LightRAG)
            episodic_store: EpisodicStore for loading sessions
            agent_id: Agent identifier
        """
        self.llm = llm
        self.rag_client = rag_client
        self.episodic_store = episodic_store or EpisodicStore()
        self.agent_id = agent_id
    
    async def generate_daily_reflection(
        self,
        date_str: str | None = None,
        force: bool = False,
    ) -> Optional[DailyReflection]:
        """
        Generate a daily reflection for the specified date.
        
        Args:
            date_str: Date in YYYY-MM-DD format (defaults to today)
            force: If True, regenerate even if reflection exists
            
        Returns:
            DailyReflection or None if no sessions or LLM unavailable
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        # Check if reflection already exists
        if not force:
            existing = self.episodic_store.load_reflection(date_str)
            if existing:
                logger.info(f"[ReflectionEngine] Reflection for {date_str} already exists")
                return existing
        
        # Load sessions for the date
        sessions = self.episodic_store.load_sessions_for_date(date_str)
        if not sessions:
            logger.info(f"[ReflectionEngine] No sessions found for {date_str}")
            return None
        
        # Check if LLM is available
        if not self.llm:
            logger.warning("[ReflectionEngine] No LLM configured, cannot generate reflection")
            return self._create_basic_reflection(date_str, sessions)
        
        # Generate reflection using LLM
        try:
            reflection = await self._generate_with_llm(date_str, sessions)
            
            # Save reflection
            self.episodic_store.save_reflection(reflection)
            
            logger.info(f"[ReflectionEngine] Generated reflection for {date_str}: "
                       f"{len(reflection.lessons)} lessons, {len(reflection.knowledge_chunks)} knowledge chunks")
            
            return reflection
            
        except Exception as e:
            logger.error(f"[ReflectionEngine] Failed to generate reflection: {e}")
            return self._create_basic_reflection(date_str, sessions)
    
    async def _generate_with_llm(
        self,
        date_str: str,
        sessions: List[SessionRecord],
    ) -> DailyReflection:
        """Generate reflection using LLM."""
        # Format sessions into text
        sessions_text = self._format_sessions_for_prompt(sessions)
        
        # Build prompt
        user_prompt = REFLECTION_USER_PROMPT.format(
            session_count=len(sessions),
            date=date_str,
            sessions_text=sessions_text,
        )
        
        # Call LLM
        from langchain_core.messages import SystemMessage, HumanMessage
        
        messages = [
            SystemMessage(content=REFLECTION_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
        
        # Use ainvoke if available, otherwise invoke in thread
        if hasattr(self.llm, 'ainvoke'):
            response = await self.llm.ainvoke(messages)
        else:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, self.llm.invoke, messages)
        
        # Parse response
        reflection = self._parse_llm_response(date_str, sessions, response.content)
        
        return reflection
    
    def _format_sessions_for_prompt(self, sessions: List[SessionRecord]) -> str:
        """Format sessions into text for the LLM prompt."""
        parts = []
        
        for i, session in enumerate(sessions, 1):
            status = "✓ SUCCESS" if session.success else "✗ FAILED"
            
            session_text = [
                f"### Session {i}: {session.task[:100]}",
                f"Status: {status}",
                f"Steps: {len(session.actions)}",
            ]
            
            if session.final_result:
                session_text.append(f"Result: {session.final_result[:200]}")
            
            if session.errors:
                session_text.append(f"Errors: {', '.join(session.errors[:3])}")
            
            if session.urls_visited:
                session_text.append(f"Sites visited: {', '.join(session.urls_visited[:5])}")
            
            # Include key actions
            if session.actions:
                action_summary = []
                for action in session.actions[:10]:  # First 10 actions
                    action_summary.append(f"  - {action.action_name}: {action.thinking[:50] if action.thinking else 'N/A'}...")
                session_text.append("Key actions:\n" + "\n".join(action_summary))
            
            parts.append("\n".join(session_text))
        
        return "\n\n---\n\n".join(parts)
    
    def _parse_llm_response(
        self,
        date_str: str,
        sessions: List[SessionRecord],
        response_text: str,
    ) -> DailyReflection:
        """Parse LLM response into DailyReflection."""
        import json
        import re
        
        # Try to extract JSON from response
        try:
            # Look for JSON block
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = {}
        except json.JSONDecodeError:
            logger.warning("[ReflectionEngine] Failed to parse LLM response as JSON")
            data = {}
        
        # Create reflection
        reflection = DailyReflection(
            date=date_str,
            agent_id=self.agent_id,
            sessions_reviewed=[s.session_id for s in sessions],
            total_sessions=len(sessions),
            successful_sessions=sum(1 for s in sessions if s.success),
            failed_sessions=sum(1 for s in sessions if s.success is False),
            successes=data.get("successes", []),
            failures=data.get("failures", []),
            patterns=data.get("patterns", []),
            lessons=data.get("lessons", []),
            improvements=data.get("improvements", []),
            knowledge_chunks=data.get("knowledge_chunks", []),
        )
        
        return reflection
    
    def _create_basic_reflection(
        self,
        date_str: str,
        sessions: List[SessionRecord],
    ) -> DailyReflection:
        """Create a basic reflection without LLM (just stats)."""
        return DailyReflection(
            date=date_str,
            agent_id=self.agent_id,
            sessions_reviewed=[s.session_id for s in sessions],
            total_sessions=len(sessions),
            successful_sessions=sum(1 for s in sessions if s.success),
            failed_sessions=sum(1 for s in sessions if s.success is False),
            successes=[],
            failures=[s.errors[0] if s.errors else "Unknown error" for s in sessions if not s.success],
            patterns=[],
            lessons=[],
            improvements=[],
            knowledge_chunks=[],
        )
    
    # =========================================================================
    # RAG Integration
    # =========================================================================
    
    async def store_knowledge_to_rag(self, reflection: DailyReflection) -> int:
        """
        Store knowledge chunks from reflection to RAG.
        
        Args:
            reflection: DailyReflection with knowledge_chunks
            
        Returns:
            Number of chunks stored
        """
        if not self.rag_client:
            logger.warning("[ReflectionEngine] No RAG client configured")
            return 0
        
        if not reflection.knowledge_chunks:
            logger.debug("[ReflectionEngine] No knowledge chunks to store")
            return 0
        
        stored = 0
        for chunk in reflection.knowledge_chunks:
            try:
                # Format chunk with metadata
                formatted_chunk = f"[Learned on {reflection.date}] {chunk}"
                
                # Store to RAG (assumes LightRAG-compatible interface)
                if hasattr(self.rag_client, 'insert'):
                    await self.rag_client.insert(formatted_chunk)
                elif hasattr(self.rag_client, 'ragify'):
                    # MCP tool interface
                    await self.rag_client.ragify(formatted_chunk)
                
                stored += 1
                
            except Exception as e:
                logger.warning(f"[ReflectionEngine] Failed to store chunk: {e}")
        
        logger.info(f"[ReflectionEngine] Stored {stored}/{len(reflection.knowledge_chunks)} knowledge chunks to RAG")
        return stored
    
    async def run_daily_reflection(self, date_str: str | None = None) -> Optional[DailyReflection]:
        """
        Run full daily reflection workflow: generate + store to RAG.
        
        Args:
            date_str: Date in YYYY-MM-DD format (defaults to today)
            
        Returns:
            DailyReflection or None
        """
        reflection = await self.generate_daily_reflection(date_str)
        
        if reflection and reflection.knowledge_chunks:
            await self.store_knowledge_to_rag(reflection)
        
        return reflection
    
    # =========================================================================
    # Batch Processing
    # =========================================================================
    
    async def backfill_reflections(
        self,
        start_date: str,
        end_date: str | None = None,
        force: bool = False,
    ) -> List[DailyReflection]:
        """
        Generate reflections for a date range.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD), defaults to today
            force: If True, regenerate existing reflections
            
        Returns:
            List of generated DailyReflections
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        reflections = []
        current = start
        
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            
            try:
                reflection = await self.generate_daily_reflection(date_str, force=force)
                if reflection:
                    reflections.append(reflection)
                    
                    # Store knowledge to RAG
                    if reflection.knowledge_chunks:
                        await self.store_knowledge_to_rag(reflection)
                        
            except Exception as e:
                logger.error(f"[ReflectionEngine] Failed to process {date_str}: {e}")
            
            current += timedelta(days=1)
        
        logger.info(f"[ReflectionEngine] Backfilled {len(reflections)} reflections")
        return reflections


# =============================================================================
# Convenience Functions
# =============================================================================

async def run_daily_reflection(
    llm = None,
    rag_client = None,
    date_str: str | None = None,
    agent_id: str = "default",
) -> Optional[DailyReflection]:
    """
    Convenience function to run daily reflection.
    
    Args:
        llm: LangChain-compatible LLM
        rag_client: RAG client for storing knowledge
        date_str: Date in YYYY-MM-DD format (defaults to today)
        agent_id: Agent identifier
        
    Returns:
        DailyReflection or None
    """
    engine = ReflectionEngine(
        llm=llm,
        rag_client=rag_client,
        agent_id=agent_id,
    )
    return await engine.run_daily_reflection(date_str)
