"""
Agent database service.

This module provides database service for agent management operations.
"""

from sqlalchemy.orm import sessionmaker
from ..core import get_engine, get_session_factory, Base
from ..models.skill_model import DBAgentSkill
from ..models.agent_model import DBAgent, DBAgentTool, DBAgentTask, DBAgentKnowledge
from .singleton import SingletonMeta
from .base_service import BaseService

from contextlib import contextmanager
from sqlalchemy.exc import SQLAlchemyError
import re


class DBAgentService(BaseService, metaclass=SingletonMeta):
    """Agent database service class providing all agent-related operations"""

    def __init__(self, db_path: str = None, engine=None, session=None):
        """
        Initialize agent service

        Args:
            db_path (str, optional): Database file path
            engine: SQLAlchemy engine instance
            session: SQLAlchemy session instance
        """
        if session is not None:
            self.SessionFactory = lambda: session
        elif engine is not None:
            self.SessionFactory = sessionmaker(bind=engine)
        elif db_path is not None:
            engine = get_engine(db_path)
            self.SessionFactory = get_session_factory(db_path)
            Base.metadata.create_all(engine)
            # Auto-insert initial db_version record and execute database upgrade
            try:
                from ..core.migration import DBMigration
                migrator = DBMigration(db_path)
                # Ensure db_version table and initial record exist
                migrator.get_current_version()
                migrator.upgrade_to_version('2.0.0', description='Auto upgrade to 2.0.0, add chat_notification table')
            except Exception as e:
                print(f"[DBMigration] Database upgrade failed: {e}")
        else:
            raise ValueError("Must provide db_path, engine or session")

    @classmethod
    def initialize(cls, db_manager) -> 'DBAgentService':
        """
        Initialize agent database service instance with database manager.

        Args:
            db_manager: ECanDBManager instance (required)

        Returns:
            DBAgentService: Initialized service instance

        Raises:
            ValueError: If db_manager is None or not properly initialized
        """
        if db_manager is None:
            raise ValueError("db_manager cannot be None")
        
        if not hasattr(db_manager, 'get_engine') or not hasattr(db_manager, 'get_session_factory'):
            raise ValueError("db_manager must have get_engine and get_session_factory methods")
        
        try:
            engine = db_manager.get_engine()
            session_factory = db_manager.get_session_factory()
            
            # Create service instance with engine
            service = cls(engine=engine)
            service.db_manager = db_manager
            
            return service
            
        except Exception as e:
            raise ValueError(f"Failed to initialize DBAgentService: {e}")

    @contextmanager
    def session_scope(self):
        """Transaction manager ensuring thread safety"""
        session = self.SessionFactory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ========== Generic CRUD operations =================================
    
    def _add(self, model, data):
        """Generic add operation"""
        try:
            with self.session_scope() as s:
                obj = model(**data)
                s.add(obj)
                s.flush()
                return {"success": True, "id": obj.id, "data": obj.to_dict(), "error": None}
        except SQLAlchemyError as e:
            return {"success": False, "id": data.get("id"), "data": None, "error": str(e)}

    def _delete(self, model, id_):
        """Generic delete operation"""
        try:
            with self.session_scope() as s:
                obj = s.get(model, id_)
                if obj:
                    s.delete(obj)
                    return {"success": True, "id": id_, "data": None, "error": None}
                else:
                    return {"success": False, "id": id_, "data": None, "error": "Object not found"}
        except SQLAlchemyError as e:
            return {"success": False, "id": id_, "data": None, "error": str(e)}

    def _update(self, model, id_, fields):
        """Generic update operation"""
        try:
            with self.session_scope() as s:
                obj = s.get(model, id_)
                if obj:
                    for k, v in fields.items():
                        if hasattr(obj, k):
                            setattr(obj, k, v)
                    s.flush()
                    return {"success": True, "id": id_, "data": obj.to_dict(), "error": None}
                else:
                    return {"success": False, "id": id_, "data": None, "error": "Object not found"}
        except SQLAlchemyError as e:
            return {"success": False, "id": id_, "data": None, "error": str(e)}

    def _search(self, model, id_: str = None, name: str = None, desc_regex: str = None):
        """Generic search operation"""
        try:
            with self.session_scope() as s:
                q = s.query(model)
                if id_:
                    q = q.filter(model.id == id_)
                if name:
                    q = q.filter(model.name.ilike(f"%{name}%"))
                results = q.all()
                if desc_regex:
                    pattern = re.compile(desc_regex, re.IGNORECASE)
                    results = [r for r in results if pattern.search(getattr(r, 'description', '') or '')]
                return [r.to_dict() for r in results]
        except SQLAlchemyError as e:
            print(f"[SearchError] {e}")
            return []

    # ========== Public CRUD wrappers =================================
    # ---- Agents ----

    def add_agent(self, data):
        """Add a new agent"""
        return self._add(DBAgent, data)

    def delete_agent(self, agent_id):
        """Delete an agent"""
        return self._delete(DBAgent, agent_id)

    def update_agent(self, agent_id, fields):
        """Update an agent"""
        return self._update(DBAgent, agent_id, fields)

    def query_agents(self, id=None, name=None, description=None):
        """Query agents"""
        return {"success": True,
                "data": self._search(DBAgent, id, name, description),
                "error": None}
    
    def search_agents(self, id=None, name=None, description=None):
        """Alias for query_agents for compatibility"""
        result = self.query_agents(id, name, description)
        return result.get("data", [])

    # ---- Skills ----
    def add_skill(self, data):
        """Add a new skill"""
        return self._add(DBAgentSkill, data)

    def delete_skill(self, skill_id):
        """Delete a skill"""
        return self._delete(DBAgentSkill, skill_id)

    def update_skill(self, skill_id, fields):
        """Update a skill"""
        return self._update(DBAgentSkill, skill_id, fields)

    def query_skills(self, id=None, name=None, description=None):
        """Query skills"""
        return {"success": True,
                "data": self._search(DBAgentSkill, id, name, description),
                "error": None}

    # ---- Tasks ----
    def add_task(self, data):
        """Add a new task"""
        return self._add(DBAgentTask, data)

    def delete_task(self, task_id):
        """Delete a task"""
        return self._delete(DBAgentTask, task_id)

    def update_task(self, task_id, fields):
        """Update a task"""
        return self._update(DBAgentTask, task_id, fields)

    def query_tasks(self, id=None, name=None, description=None):
        """Query tasks"""
        return {"success": True,
                "data": self._search(DBAgentTask, id, name, description),
                "error": None}

    # ---- Tools ----
    def add_tool(self, data):
        """Add a new tool"""
        return self._add(DBAgentTool, data)

    def delete_tool(self, tool_id):
        """Delete a tool"""
        return self._delete(DBAgentTool, tool_id)

    def update_tool(self, tool_id, fields):
        """Update a tool"""
        return self._update(DBAgentTool, tool_id, fields)

    def query_tools(self, id=None, name=None, description=None):
        """Query tools"""
        return {"success": True,
                "data": self._search(DBAgentTool, id, name, description),
                "error": None}

    # ---- Knowledge ----
    def add_knowledge(self, data):
        """Add new knowledge"""
        return self._add(DBAgentKnowledge, data)

    def delete_knowledge(self, knowledge_id):
        """Delete knowledge"""
        return self._delete(DBAgentKnowledge, knowledge_id)

    def update_knowledge(self, knowledge_id, fields):
        """Update knowledge"""
        return self._update(DBAgentKnowledge, knowledge_id, fields)

    def query_knowledges(self, id=None, name=None, description=None):
        """Query knowledge"""
        return {"success": True,
                "data": self._search(DBAgentKnowledge, id, name, description),
                "error": None}


# Backward compatibility aliases
AgentService = DBAgentService  # For consistency with new naming
AgentsDBService = DBAgentService  # Legacy compatibility
