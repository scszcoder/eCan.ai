"""
Episodic Store - Persistent storage for session records.

Stores and retrieves SessionRecords as JSON files, organized by date.
Provides methods for querying sessions by date range, agent, success status, etc.

Usage:
    from agent.memory.episodic_store import EpisodicStore
    
    store = EpisodicStore()
    
    # Save a session
    store.save_session(session_record)
    
    # Load sessions for a date
    sessions = store.load_sessions_for_date("2024-12-14")
    
    # Load sessions for date range
    sessions = store.load_sessions_for_range("2024-12-01", "2024-12-14")
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any

from utils.logger_helper import logger_helper as logger
from agent.memory.models import SessionRecord, ActionRecord, DailyReflection


class EpisodicStore:
    """
    Persistent storage for session records (episodic memory).
    
    Stores sessions as JSON files organized by date:
    {base_dir}/
        sessions/
            2024-12-14/
                session_abc123.json
                session_def456.json
        reflections/
            2024-12-14.json
    """
    
    def __init__(self, base_dir: str | None = None):
        """
        Initialize episodic store.
        
        Args:
            base_dir: Base directory for storage. Defaults to appdata/memory/episodic
        """
        if base_dir is None:
            try:
                from config.app_info import app_info
                base_dir = os.path.join(app_info.appdata_path, "memory", "episodic")
            except Exception as e:
                logger.warning(f"[EpisodicStore] Failed to get appdata path: {e}")
                base_dir = os.path.join(os.path.expanduser("~"), ".ecan", "memory", "episodic")
        
        self.base_dir = Path(base_dir)
        self.sessions_dir = self.base_dir / "sessions"
        self.reflections_dir = self.base_dir / "reflections"
        
        # Create directories
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.reflections_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"[EpisodicStore] Initialized at {self.base_dir}")
    
    # =========================================================================
    # Session Storage
    # =========================================================================
    
    def save_session(self, session: SessionRecord) -> str:
        """
        Save a session record to disk.
        
        Args:
            session: SessionRecord to save
            
        Returns:
            Path to saved file
        """
        # Determine date directory
        date_str = session.start_time.strftime("%Y-%m-%d")
        date_dir = self.sessions_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # Save as JSON
        filename = f"session_{session.session_id}.json"
        filepath = date_dir / filename
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
            logger.debug(f"[EpisodicStore] Saved session {session.session_id} to {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"[EpisodicStore] Failed to save session: {e}")
            raise
    
    def load_session(self, session_id: str, date_str: str | None = None) -> Optional[SessionRecord]:
        """
        Load a session by ID.
        
        Args:
            session_id: Session ID to load
            date_str: Optional date hint (YYYY-MM-DD) to speed up lookup
            
        Returns:
            SessionRecord or None if not found
        """
        # If date provided, look directly
        if date_str:
            filepath = self.sessions_dir / date_str / f"session_{session_id}.json"
            if filepath.exists():
                return self._load_session_file(filepath)
        
        # Otherwise search all dates
        for date_dir in sorted(self.sessions_dir.iterdir(), reverse=True):
            if date_dir.is_dir():
                filepath = date_dir / f"session_{session_id}.json"
                if filepath.exists():
                    return self._load_session_file(filepath)
        
        return None
    
    def load_sessions_for_date(self, date_str: str) -> List[SessionRecord]:
        """
        Load all sessions for a specific date.
        
        Args:
            date_str: Date in YYYY-MM-DD format
            
        Returns:
            List of SessionRecords
        """
        date_dir = self.sessions_dir / date_str
        if not date_dir.exists():
            return []
        
        sessions = []
        for filepath in date_dir.glob("session_*.json"):
            session = self._load_session_file(filepath)
            if session:
                sessions.append(session)
        
        # Sort by start time
        sessions.sort(key=lambda s: s.start_time)
        return sessions
    
    def load_sessions_for_range(
        self,
        start_date: str,
        end_date: str,
        agent_id: str | None = None,
        success_only: bool | None = None,
    ) -> List[SessionRecord]:
        """
        Load sessions for a date range with optional filters.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            agent_id: Filter by agent ID
            success_only: If True, only successful sessions; if False, only failed
            
        Returns:
            List of SessionRecords
        """
        sessions = []
        
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            day_sessions = self.load_sessions_for_date(date_str)
            
            for session in day_sessions:
                # Apply filters
                if agent_id and session.agent_id != agent_id:
                    continue
                if success_only is True and not session.success:
                    continue
                if success_only is False and session.success:
                    continue
                sessions.append(session)
            
            current += timedelta(days=1)
        
        return sessions
    
    def get_session_dates(self) -> List[str]:
        """
        Get all dates that have sessions.
        
        Returns:
            List of date strings (YYYY-MM-DD), sorted descending
        """
        dates = []
        for date_dir in self.sessions_dir.iterdir():
            if date_dir.is_dir() and any(date_dir.glob("session_*.json")):
                dates.append(date_dir.name)
        return sorted(dates, reverse=True)
    
    def _load_session_file(self, filepath: Path) -> Optional[SessionRecord]:
        """Load a session from a JSON file."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SessionRecord.from_dict(data)
        except Exception as e:
            logger.warning(f"[EpisodicStore] Failed to load {filepath}: {e}")
            return None
    
    # =========================================================================
    # Reflection Storage
    # =========================================================================
    
    def save_reflection(self, reflection: DailyReflection) -> str:
        """
        Save a daily reflection.
        
        Args:
            reflection: DailyReflection to save
            
        Returns:
            Path to saved file
        """
        filename = f"{reflection.date}.json"
        filepath = self.reflections_dir / filename
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(reflection.to_dict(), f, indent=2, ensure_ascii=False)
            logger.debug(f"[EpisodicStore] Saved reflection for {reflection.date}")
            return str(filepath)
        except Exception as e:
            logger.error(f"[EpisodicStore] Failed to save reflection: {e}")
            raise
    
    def load_reflection(self, date_str: str) -> Optional[DailyReflection]:
        """
        Load a daily reflection.
        
        Args:
            date_str: Date in YYYY-MM-DD format
            
        Returns:
            DailyReflection or None if not found
        """
        filepath = self.reflections_dir / f"{date_str}.json"
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return DailyReflection.from_dict(data)
        except Exception as e:
            logger.warning(f"[EpisodicStore] Failed to load reflection: {e}")
            return None
    
    def get_reflection_dates(self) -> List[str]:
        """
        Get all dates that have reflections.
        
        Returns:
            List of date strings (YYYY-MM-DD), sorted descending
        """
        dates = []
        for filepath in self.reflections_dir.glob("*.json"):
            dates.append(filepath.stem)
        return sorted(dates, reverse=True)
    
    # =========================================================================
    # Statistics
    # =========================================================================
    
    def get_stats(self, date_str: str | None = None) -> Dict[str, Any]:
        """
        Get statistics for sessions.
        
        Args:
            date_str: Optional date to filter (YYYY-MM-DD)
            
        Returns:
            Dict with statistics
        """
        if date_str:
            sessions = self.load_sessions_for_date(date_str)
        else:
            # Load all sessions (expensive for large stores)
            sessions = []
            for date in self.get_session_dates():
                sessions.extend(self.load_sessions_for_date(date))
        
        total = len(sessions)
        successful = sum(1 for s in sessions if s.success)
        failed = sum(1 for s in sessions if s.success is False)
        
        total_actions = sum(len(s.actions) for s in sessions)
        total_errors = sum(len(s.errors) for s in sessions)
        
        return {
            "total_sessions": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total if total > 0 else 0,
            "total_actions": total_actions,
            "total_errors": total_errors,
            "avg_actions_per_session": total_actions / total if total > 0 else 0,
        }


# =============================================================================
# Session Recorder - For use with PrivacyControllableAgent
# =============================================================================

class SessionRecorder:
    """
    Records agent actions into a SessionRecord.
    
    Pass this as history_recorder to PrivacyControllableAgent.
    
    Usage:
        recorder = SessionRecorder(agent_id="my_agent", task="Do something")
        
        agent = PrivacyControllableAgent(
            task="Do something",
            llm=llm,
            history_recorder=recorder,
        )
        
        await agent.run_with_control()
        
        # Save the session
        recorder.finalize(success=True, final_result="Done!")
        recorder.save()
    """
    
    def __init__(
        self,
        agent_id: str,
        task: str,
        session_id: str | None = None,
        store: EpisodicStore | None = None,
    ):
        """
        Initialize session recorder.
        
        Args:
            agent_id: Agent identifier
            task: Task description
            session_id: Optional session ID (auto-generated if None)
            store: Optional EpisodicStore (created if None)
        """
        import uuid
        
        self.store = store or EpisodicStore()
        self.session = SessionRecord(
            session_id=session_id or str(uuid.uuid4())[:8],
            agent_id=agent_id,
            task=task,
            start_time=datetime.now(),
        )
    
    async def record_step(self, step_data) -> None:
        """
        Record a step from PrivacyControllableAgent.
        
        Args:
            step_data: StepData from agent.step_once()
        """
        # Convert StepData to ActionRecord
        action = ActionRecord(
            timestamp=datetime.now(),
            session_id=self.session.session_id,
            step_number=step_data.step_number,
            action_type="browser_action",
            action_name=self._extract_action_name(step_data.action),
            action_input=self._extract_action_input(step_data.action),
            success=step_data.error is None,
            error=step_data.error,
            url=step_data.url,
            page_title=step_data.title,
            thinking=step_data.thinking,
            next_goal=step_data.next_goal,
        )
        
        self.session.add_action(action)
    
    def finalize(
        self,
        success: bool | None = None,
        final_result: str | None = None,
        token_usage: Dict[str, int] | None = None,
    ) -> SessionRecord:
        """
        Finalize the session.
        
        Args:
            success: Whether the task succeeded
            final_result: Final result text
            token_usage: Token usage stats
            
        Returns:
            The finalized SessionRecord
        """
        self.session.end_time = datetime.now()
        self.session.success = success
        self.session.final_result = final_result
        if token_usage:
            self.session.token_usage = token_usage
        return self.session
    
    def save(self) -> str:
        """
        Save the session to the episodic store.
        
        Returns:
            Path to saved file
        """
        return self.store.save_session(self.session)
    
    def _extract_action_name(self, action) -> str:
        """Extract action name from AgentOutput."""
        if not action or not hasattr(action, 'action') or not action.action:
            return "none"
        act = action.action[0] if action.action else None
        if not act:
            return "none"
        try:
            action_data = act.model_dump(exclude_unset=True)
            return next(iter(action_data.keys()), "unknown")
        except Exception:
            return "unknown"
    
    def _extract_action_input(self, action) -> Dict[str, Any]:
        """Extract action parameters from AgentOutput."""
        if not action or not hasattr(action, 'action') or not action.action:
            return {}
        act = action.action[0] if action.action else None
        if not act:
            return {}
        try:
            action_data = act.model_dump(exclude_unset=True)
            action_name = next(iter(action_data.keys()), None)
            return action_data.get(action_name, {}) if action_name else {}
        except Exception:
            return {}
