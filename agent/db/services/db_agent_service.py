"""
Agent database service.

This module provides database service for agent management operations.
"""

from sqlalchemy.orm import sessionmaker, joinedload
from ..models.skill_model import DBAgentSkill
from ..models.agent_model import DBAgent, DBAgentTool, DBAgentTask, DBAgentKnowledge
from ..models.org_model import DBAgentOrg
from ..models.vehicle_model import DBAgentVehicle
from ..models.association_models import (
    DBAgentOrgRel, DBAgentSkillRel, DBAgentTaskRel,
    DBSkillToolRel, DBAgentSkillKnowledgeRel, DBAgentTaskSkillRel
)
from .base_service import BaseService

from contextlib import contextmanager
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import and_, or_, func
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import re
import json
from utils.logger_helper import logger_helper as logger


# def get_default_avatar(agent_id: str, owner: str = None) -> Optional[Dict[str, Any]]:
#     """
#     Public helper function to generate a default random system avatar
    
#     This is a simple wrapper that delegates to DBAvatarService.
    
#     Args:
#         agent_id: Agent ID (used as seed for consistent random selection)
#         owner: Owner username (optional)
        
#     Returns:
#         dict: Avatar information or None
#     """
#     from .db_avatar_service import DBAvatarService
#     return DBAvatarService.generate_default_avatar(agent_id, owner)


class DBAgentService(BaseService):
    """Agent database service class providing all agent-related operations"""
    
    @staticmethod
    def _serialize_pydantic_model(obj, exclude_fields=None):
        """
        Serialize a Pydantic model to dict (Pydantic v2)
        
        Args:
            obj: Pydantic model instance
            exclude_fields: Set of field names to exclude
            
        Returns:
            dict: Serialized model
            
        Raises:
            TypeError: If object is not a Pydantic v2 model
        """
        if exclude_fields is None:
            # Default: exclude non-serializable fields
            # - EC_Skill: work_flow, runnable, diagram, mcp_client, mapping_rules
            # - ManagedTask: skill, task, pause_event, cancellation_event, queue
            exclude_fields = {
                'skill', 'task', 'pause_event', 'cancellation_event', 'queue',
                'work_flow', 'runnable', 'diagram', 'mcp_client', 'mapping_rules'
            }
        
        # Pydantic v2 (project uses pydantic==2.12.3)
        if hasattr(obj, 'model_dump'):
            return obj.model_dump(exclude=exclude_fields, mode='json')
        else:
            # Not a Pydantic v2 model
            logger.error(f"[DBAgentService] Object is not a Pydantic v2 model! Type: {type(obj)}, ID: {getattr(obj, 'id', 'UNKNOWN')}")
            raise TypeError(f"Expected Pydantic v2 model, got {type(obj)}")
    
    @staticmethod
    def _validate_items_exist(session, item_ids, db_model, memory_attr, item_type):
        """
        Validate that items exist in database or memory (for code-generated items).
        
        Args:
            session: SQLAlchemy session
            item_ids: List of item IDs to validate
            db_model: Database model class (DBAgentSkill or DBAgentTask)
            memory_attr: Attribute name in mainwin ('agent_skills' or 'agent_tasks')
            item_type: Item type name for logging ('skill' or 'task')
            
        Returns:
            tuple: (valid_ids, invalid_ids)
        """
        valid_ids = []
        invalid_ids = []
        
        for item_id in item_ids:
            if not item_id:
                continue
                
            # Check if item exists in database
            exists_in_db = session.query(db_model).filter(db_model.id == item_id).first()
            
            # Check if item exists in memory (code-generated items)
            exists_in_memory = False
            try:
                from app_context import AppContext
                mainwin = AppContext.get_main_window()
                if mainwin and hasattr(mainwin, memory_attr):
                    memory_items = getattr(mainwin, memory_attr)
                    exists_in_memory = any(
                        getattr(item, 'id', None) == item_id 
                        for item in memory_items
                    )
            except Exception as e:
                logger.debug(f"[DBAgentService] Could not check memory {item_type}s: {e}")
            
            # Validate
            if exists_in_db or exists_in_memory:
                valid_ids.append(item_id)
                if exists_in_memory and not exists_in_db:
                    logger.debug(f"[DBAgentService] {item_type.capitalize()} {item_id} is code-generated (not in DB, but valid)")
            else:
                invalid_ids.append(item_id)
                logger.warning(f"[DBAgentService] {item_type.capitalize()} not found (neither in DB nor in memory): {item_id}")
        
        return valid_ids, invalid_ids
    
    def __init__(self, engine=None, session=None):
        """
        Initialize agent service.
        
        Args:
            engine: SQLAlchemy engine instance (required)
            session: SQLAlchemy session instance (optional)
        """
        # Call parent class initialization
        super().__init__(engine, session)


    def _get_avatar_service(self):
        """
        Get avatar service from ECDBMgr.
        
        Returns:
            DBAvatarService: Avatar service instance or None if not available
        """
        try:
            from app_context import AppContext
            main_window = AppContext.get_main_window()
            if main_window and hasattr(main_window, 'ec_db_mgr'):
                return main_window.ec_db_mgr.avatar_service
            return None
        except Exception as e:
            logger.warning(f"[DBAgentService] Failed to get avatar service: {e}")
            return None
    
    def session_scope(self):
        """
        Provide a transactional scope around a series of operations.

        Yields:
            Session: SQLAlchemy session instance
        """
        # Use BaseService's session management
        return super().session_scope()

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

    def create_agent_from_data(self, agent_data: Dict[str, Any], username: str) -> Dict[str, Any]:
        """
        Create a new agent from frontend data

        Args:
            agent_data: Agent data from frontend with structure:
                {
                    'name': str,
                    'description': str,  # agent description text
                    'extra_data': str,  # additional notes/extra data
                    'gender': str,  # 'gender_options.male' etc
                    'birthday': str,
                    'title': list or str,
                    'personalities': list,  # personality traits
                    'supervisor_id': str,  # single supervisor ID
                    'org_id': str,  # organization ID
                    'tasks': list,  # [task_id, ...]
                    'skills': list,  # [skill_id, ...]
                    'vehicle_id': str,  # vehicle_id - used in task associations
                }
            username: Username of the agent owner

        Returns:
            dict: Result with success status, created agent data, and error if any
                {
                    'success': bool,
                    'id': str,
                    'data': dict,  # Complete agent data including auto-generated fields
                    'error': str or None
                }

        Note:
            - Frontend 'description' (text) maps to DBAgent.description (Text field)
            - Frontend 'extra_data' (text) is stored in DBAgent.extra_data.notes (JSON field)
            - vehicle_id is used in task associations (DBAgentTaskRel.vehicle_id)
            - DBAgent.extra_data (JSON) stores structured data like notes, preferences, etc.
        """
        try:
            # Extract and process agent data
            agent_name = agent_data.get('name', '').strip()
            if not agent_name:
                return {
                    'success': False,
                    'id': None,
                    'data': None,
                    'error': 'Agent name is required'
                }

            # Process gender field
            gender = agent_data.get('gender', '').replace('gender_options.', '')

            # Process title field (can be list or string)
            title_data = agent_data.get('title', [])
            title = ','.join(title_data) if isinstance(title_data, list) else str(title_data) if title_data else ''
            supervisor_id = agent_data.get('supervisor_id') or None
            personalities = agent_data.get('personalities', [])
            description = agent_data.get('description', '')
            frontend_extra_data = agent_data.get('extra_data', '')

            # Extract relationship IDs
            org_id = agent_data.get('org_id', '')
            task_ids = agent_data.get('tasks', [])
            skill_ids = agent_data.get('skills', [])
            vehicle_id = agent_data.get('vehicle_id', '')

            # Build extra_data JSON from frontend data
            extra_data = {}
            if frontend_extra_data:
                extra_data['notes'] = frontend_extra_data

            # Create DBAgent model object (ID will be auto-generated)
            db_agent = DBAgent(
                name=agent_name,
                owner=username,
                description=description,  # description text from frontend
                gender=gender,
                birthday=agent_data.get('birthday', ''),
                title=title,
                personalities=personalities,
                supervisor_id=supervisor_id,
                vehicle_id=vehicle_id or None,  # Set vehicle_id directly on DBAgent
                status='active',
                extra_data=extra_data
            )

            # Save agent and create relationships in a transaction
            with self.session_scope() as session:
                # Add and flush agent to get ID
                session.add(db_agent)
                session.flush()

                created_agent_id = db_agent.id

                # Create organization relationship if org_id provided
                if org_id:
                    org_rel = DBAgentOrgRel(
                        agent_id=created_agent_id,
                        org_id=org_id,
                        role='member',
                        status='active'
                    )
                    session.add(org_rel)

                # Create skill relationships
                # Frontend sends: ['skill_id1', 'skill_id2', ...]
                for skill_id in skill_ids:
                    if skill_id:
                        skill_rel = DBAgentSkillRel(
                            agent_id=created_agent_id,
                            skill_id=skill_id,
                            proficiency_level='beginner',
                            status='active'
                        )
                        session.add(skill_rel)

                # Create task relationships (with vehicle)
                # Frontend sends: ['task_id1', 'task_id2', ...]
                for task_id in task_ids:
                    if task_id and vehicle_id:
                        task_rel = DBAgentTaskRel(
                            agent_id=created_agent_id,
                            task_id=task_id,
                            vehicle_id=vehicle_id,
                            status='pending',
                            priority='medium'
                        )
                        session.add(task_rel)

                session.flush()

                # Get the created agent data
                created_agent_data = db_agent.to_dict()
                
                # Add org_id to the returned data (not stored in DBAgent model)
                if org_id:
                    created_agent_data['org_id'] = org_id

            return {
                'success': True,
                'id': created_agent_id,
                'data': created_agent_data,
                'error': None
            }

        except SQLAlchemyError as e:
            return {
                'success': False,
                'id': None,
                'data': None,
                'error': f'Database error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'id': None,
                'data': None,
                'error': f'Error creating agent: {str(e)}'
            }

    def create_agents_batch(self, agents_data: List[Dict[str, Any]], username: str) -> Dict[str, Any]:
        """
        Create multiple agents in batch

        Args:
            agents_data: List of agent data from frontend
            username: Username of the agent owner

        Returns:
            dict: Result with success status, created agents, and errors
                {
                    'success': bool,
                    'created_count': int,
                    'agents': List[dict],  # List of created agents
                    'errors': List[str]    # List of error messages
                }
        """
        created_agents = []
        errors = []

        for agent_data in agents_data:
            agent_name = agent_data.get('name', 'Unknown')
            try:
                result = self.create_agent_from_data(agent_data, username)

                if result['success']:
                    created_agents.append({
                        'id': result['id'],
                        'name': agent_name,
                        'data': result['data']
                    })
                else:
                    error_msg = result.get('error', 'Unknown error')
                    errors.append(f"Failed to create agent {agent_name}: {error_msg}")
                    logger.error(f"Failed to create agent {agent_name}: {error_msg}")

            except Exception as e:
                logger.error(f"Error creating agent {agent_name}: {e}")
                errors.append(f"Error creating agent {agent_name}: {str(e)}")

        return {
            'success': len(errors) == 0,
            'created_count': len(created_agents),
            'agents': created_agents,
            'errors': errors
        }

    def delete_agent(self, agent_id):
        """
        Delete an agent and all its associations
        
        Args:
            agent_id: Agent ID to delete
            
        Returns:
            dict: Result with success status
        """
        try:
            with self.session_scope() as session:
                # Get the agent
                agent = session.get(DBAgent, agent_id)
                if not agent:
                    return {"success": False, "id": agent_id, "data": None, "error": "Agent not found"}
                
                # Delete all association records first (to avoid foreign key constraints)
                # 1. Delete agent-org relationships
                deleted_org_rels = session.query(DBAgentOrgRel).filter(DBAgentOrgRel.agent_id == agent_id).delete()
                logger.debug(f"[DBAgentService] Deleted {deleted_org_rels} agent-org relationships")
                
                # 2. Delete agent-skill relationships
                deleted_skill_rels = session.query(DBAgentSkillRel).filter(DBAgentSkillRel.agent_id == agent_id).delete()
                logger.debug(f"[DBAgentService] Deleted {deleted_skill_rels} agent-skill relationships")
                
                # 3. Delete agent-task relationships
                deleted_task_rels = session.query(DBAgentTaskRel).filter(DBAgentTaskRel.agent_id == agent_id).delete()
                logger.debug(f"[DBAgentService] Deleted {deleted_task_rels} agent-task relationships")
                
                # Note: DBAgentSkillKnowledgeRel and DBAgentTaskSkillRel don't have agent_id
                # They are indirect relationships (skill-knowledge, task-skill) and will be cleaned up separately if needed
                
                # Finally, delete the agent itself
                session.delete(agent)
                session.flush()
                
                logger.info(f"[DBAgentService] Successfully deleted agent {agent_id} and all associations")
                return {"success": True, "id": agent_id, "data": None, "error": None}
                
        except SQLAlchemyError as e:
            logger.error(f"[DBAgentService] Failed to delete agent {agent_id}: {e}")
            return {"success": False, "id": agent_id, "data": None, "error": str(e)}


    def query_agents(self, id=None, name=None, description=None):
        """Query agents"""
        return {"success": True,
                "data": self._search(DBAgent, id, name, description),
                "error": None}
    
    def search_agents(self, id=None, name=None, description=None):
        """Alias for query_agents for compatibility"""
        result = self.query_agents(id, name, description)
        return result.get("data", [])
    
    def get_agents_by_owner(self, owner: str) -> Dict[str, Any]:
        """
        Get all agents for a specific owner with their organization relationships
        
        Args:
            owner: Owner username/email
        
        Returns:
            dict: Query result with success status and agent data list
                {
                    'success': bool,
                    'data': List[dict],  # List of agent dicts with org_id field
                    'error': str or None
                }
        """
        try:
            with self.session_scope() as session:
                from agent.db.models.association_models import DBAgentOrgRel
                
                # Query agents by owner
                db_agent_records = session.query(DBAgent).filter(
                    DBAgent.owner == owner
                ).all()
                
                # Query all agent-org relationships for these agents
                agent_ids = [agent.id for agent in db_agent_records]
                org_rels = session.query(DBAgentOrgRel).filter(
                    DBAgentOrgRel.agent_id.in_(agent_ids)
                ).all()
                org_rel_map = {rel.agent_id: rel.org_id for rel in org_rels}
                
                # Query all agent-skill relationships
                skill_rels = session.query(DBAgentSkillRel).filter(
                    DBAgentSkillRel.agent_id.in_(agent_ids)
                ).all()
                
                # Build skill map: agent_id -> [skill_objects]
                skill_map = {}
                for rel in skill_rels:
                    if rel.agent_id not in skill_map:
                        skill_map[rel.agent_id] = []
                    # Get full skill object (not just name)
                    if rel.skill:
                        skill_map[rel.agent_id].append(rel.skill.to_dict())
                
                # Query all agent-task relationships
                task_rels = session.query(DBAgentTaskRel).filter(
                    DBAgentTaskRel.agent_id.in_(agent_ids)
                ).all()
                
                # Build task map: agent_id -> [task_objects]
                task_map = {}
                for rel in task_rels:
                    if rel.agent_id not in task_map:
                        task_map[rel.agent_id] = []
                    # Get full task object (not just name)
                    if rel.task:
                        task_map[rel.agent_id].append(rel.task.to_dict())
                
                # Convert to dict list and add relationships
                agents_data = []
                for agent in db_agent_records:
                    agent_dict = agent.to_dict()
                    # Add org_id from relationship table
                    agent_dict['org_id'] = org_rel_map.get(agent.id)
                    # Add skills from relationship table (override JSON field)
                    agent_dict['skills'] = skill_map.get(agent.id, [])
                    # Add tasks from relationship table (override JSON field)
                    agent_dict['tasks'] = task_map.get(agent.id, [])
                    
                    # Add avatar information
                    avatar_service = self._get_avatar_service()
                    if avatar_service:
                        avatar_info = avatar_service.get_agent_avatar_info(agent, owner)
                        if avatar_info:
                            agent_dict['avatar'] = avatar_info
                    
                    agents_data.append(agent_dict)
                
                return {
                    "success": True,
                    "data": agents_data,
                    "error": None
                }
                
        except SQLAlchemyError as e:
            logger.error(f"[DBAgentService] Database query failed for owner {owner}: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"[DBAgentService] Failed to get agents for owner {owner}: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }
    
    def query_agents_with_org(self):
        """
        Query all agents with their organization relationships
        
        Returns:
            dict: Query result with success status and data
                  Each agent dict will include 'org_id' field from agent_org_rels table
        """
        try:
            with self.session_scope() as session:
                from agent.db.models.agent_model import DBAgent
                from agent.db.models.association_models import DBAgentOrgRel
                
                # Query all agents
                agents_query = session.query(DBAgent).all()
                
                # Query all agent-org relationships
                org_rels = session.query(DBAgentOrgRel).all()
                org_rel_map = {rel.agent_id: rel.org_id for rel in org_rels}
                
                # Convert agents to dict and add org_id from relationship table
                result_data = []
                for agent in agents_query:
                    agent_dict = agent.to_dict(deep=False)
                    # Add org_id from relationship table
                    agent_dict['org_id'] = org_rel_map.get(agent.id)
                    result_data.append(agent_dict)
                
                return {
                    "success": True,
                    "data": result_data,
                    "error": None
                }
                
        except Exception as e:
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    def query_agents_with_relations(self, id=None, name=None, org_id=None, include_skills=True, include_tasks=True, include_org=True):
        """
        Query agents with related data for frontend display

        Args:
            id (str, optional): Agent ID filter
            name (str, optional): Agent name filter (partial match)
            org_id (str, optional): Organization ID filter
            include_skills (bool): Include agent skills
            include_tasks (bool): Include agent tasks
            include_org (bool): Include organization info

        Returns:
            dict: Query result with success status and data
        """
        try:
            with self.session_scope() as s:
                # Build base query
                query = s.query(DBAgent)

                # Add eager loading for relationships (using correct backref names)
                if include_org:
                    query = query.options(joinedload(DBAgent.org_rels))
                if include_skills:
                    # Use nested joinedload to load skill_rels AND the actual skill objects
                    from ..models.association_models import DBAgentSkillRel
                    query = query.options(joinedload(DBAgent.skill_rels).joinedload(DBAgentSkillRel.skill))
                if include_tasks:
                    # Use nested joinedload to load task_rels AND the actual task objects
                    from ..models.association_models import DBAgentTaskRel
                    query = query.options(joinedload(DBAgent.task_rels).joinedload(DBAgentTaskRel.task))
                # Always eager load avatar_resource to avoid N+1 queries
                query = query.options(joinedload(DBAgent.avatar_resource))

                # Apply filters
                if id:
                    query = query.filter(DBAgent.id == id)
                if name:
                    query = query.filter(DBAgent.name.ilike(f"%{name}%"))
                if org_id:
                    query = query.filter(DBAgent.org_id == org_id)

                # Execute query
                agents = query.all()

                # Convert to dict with deep relationships
                result_data = []
                for agent in agents:
                    agent_dict = agent.to_dict(deep=True)

                    # Add code-generated skills/tasks from memory (not in database)
                    if include_skills and hasattr(agent, 'skill_rels') and agent.skill_rels:
                        try:
                            from app_context import AppContext
                            mainwin = AppContext.get_main_window()
                            if mainwin and hasattr(mainwin, 'agent_skills'):
                                # Get skill IDs from relationships
                                skill_ids = [rel.skill_id for rel in agent.skill_rels]
                                # Find skills in memory (including code-generated ones)
                                memory_skills = []
                                for skill_id in skill_ids:
                                    # First check if already in agent_dict['skills'] (from DB)
                                    if 'skills' in agent_dict and any(s.get('id') == skill_id for s in agent_dict['skills']):
                                        continue
                                    # Check memory for code-generated skills
                                    memory_skill = next((s for s in mainwin.agent_skills if getattr(s, 'id', None) == skill_id), None)
                                    if memory_skill:
                                        # Serialize the skill using helper function
                                        skill_dict = self._serialize_pydantic_model(memory_skill)
                                        memory_skills.append(skill_dict)
                                # Add memory skills to agent_dict
                                if memory_skills:
                                    agent_dict.setdefault('skills', []).extend(memory_skills)
                                    logger.debug(f"[DBAgentService] Added {len(memory_skills)} code-generated skills for agent {agent.id}")
                        except Exception as e:
                            logger.debug(f"[DBAgentService] Could not add memory skills: {e}")
                    
                    if include_tasks and hasattr(agent, 'task_rels') and agent.task_rels:
                        try:
                            from app_context import AppContext
                            mainwin = AppContext.get_main_window()
                            if mainwin and hasattr(mainwin, 'agent_tasks'):
                                # Get task IDs from relationships
                                task_ids = [rel.task_id for rel in agent.task_rels]
                                # Find tasks in memory (including code-generated ones)
                                memory_tasks = []
                                for task_id in task_ids:
                                    # First check if already in agent_dict['tasks'] (from DB)
                                    if 'tasks' in agent_dict and any(t.get('id') == task_id for t in agent_dict['tasks']):
                                        continue
                                    # Check memory for code-generated tasks
                                    memory_task = next((t for t in mainwin.agent_tasks if getattr(t, 'id', None) == task_id), None)
                                    if memory_task:
                                        # Serialize the task using helper function
                                        task_dict = self._serialize_pydantic_model(memory_task)
                                        memory_tasks.append(task_dict)
                                # Add memory tasks to agent_dict
                                if memory_tasks:
                                    agent_dict.setdefault('tasks', []).extend(memory_tasks)
                                    logger.debug(f"[DBAgentService] Added {len(memory_tasks)} code-generated tasks for agent {agent.id}")
                        except Exception as e:
                            logger.debug(f"[DBAgentService] Could not add memory tasks: {e}")

                    # Add additional computed fields for frontend (using correct backref names)
                    agent_dict['skills_count'] = len(agent.skill_rels) if hasattr(agent, 'skill_rels') and agent.skill_rels else 0
                    agent_dict['tasks_count'] = len(agent.task_rels) if hasattr(agent, 'task_rels') and agent.task_rels else 0
                    agent_dict['active_tasks_count'] = len([t for t in (agent.task_rels or []) if t.status in ['pending', 'running']])
                    
                    # Add avatar information (needed for agent_converter)
                    avatar_service = self._get_avatar_service()
                    if avatar_service:
                        avatar_info = avatar_service.get_agent_avatar_info(agent, owner=None)
                        if avatar_info:
                            agent_dict['avatar'] = avatar_info

                    result_data.append(agent_dict)

                return {
                    "success": True,
                    "data": result_data,
                    "total": len(result_data),
                    "error": None
                }

        except Exception as e:
            return {
                "success": False,
                "data": [],
                "total": 0,
                "error": str(e)
            }

    # ---- Skills ----
    def add_skill(self, data):
        """Add a new skill"""
        return self._add(DBAgentSkill, data)

    def delete_skill(self, skill_id):
        """Delete a skill and all its relationships"""
        try:
            with self.session_scope() as s:
                # First, delete all related records to avoid foreign key constraint issues
                # Delete agent-skill relationships
                s.query(DBAgentSkillRel).filter(DBAgentSkillRel.skill_id == skill_id).delete()
                
                # Delete skill-tool relationships
                s.query(DBSkillToolRel).filter(DBSkillToolRel.skill_id == skill_id).delete()
                
                # Delete skill-knowledge relationships
                s.query(DBAgentSkillKnowledgeRel).filter(DBAgentSkillKnowledgeRel.skill_id == skill_id).delete()
                
                # Delete task-skill relationships
                s.query(DBAgentTaskSkillRel).filter(DBAgentTaskSkillRel.skill_id == skill_id).delete()
                
                # Finally, delete the skill itself
                skill = s.get(DBAgentSkill, skill_id)
                if skill:
                    s.delete(skill)
                    s.flush()
                    return {"success": True, "id": skill_id, "data": None, "error": None}
                else:
                    return {"success": False, "id": skill_id, "data": None, "error": "Skill not found"}
        except SQLAlchemyError as e:
            return {"success": False, "id": skill_id, "data": None, "error": str(e)}

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

    def query_tasks_with_relations(self, id=None, name=None, agent_id=None, org_id=None, status=None, include_agent=True, include_org=True):
        """
        Query tasks with related data for frontend display

        Args:
            id (str, optional): Task ID filter
            name (str, optional): Task name filter (partial match)
            agent_id (str, optional): Agent ID filter
            org_id (str, optional): Organization ID filter
            status (str, optional): Task status filter
            include_agent (bool): Include agent info
            include_org (bool): Include organization info

        Returns:
            dict: Query result with success status and data
        """
        try:
            with self.session_scope() as s:
                # Build base query
                query = s.query(DBAgentTask)

                # Add eager loading for relationships
                if include_agent:
                    query = query.options(joinedload(DBAgentTask.agent))
                if include_org:
                    query = query.options(joinedload(DBAgentTask.organization))

                # Apply filters
                if id:
                    query = query.filter(DBAgentTask.id == id)
                if name:
                    query = query.filter(DBAgentTask.name.ilike(f"%{name}%"))
                if agent_id:
                    query = query.filter(DBAgentTask.agent_id == agent_id)
                if org_id:
                    query = query.filter(DBAgentTask.org_id == org_id)
                if status:
                    query = query.filter(DBAgentTask.status == status)

                # Execute query
                tasks = query.all()

                # Convert to dict with deep relationships
                result_data = []
                for task in tasks:
                    task_dict = task.to_dict(deep=True)
                    result_data.append(task_dict)

                return {
                    "success": True,
                    "data": result_data,
                    "total": len(result_data),
                    "error": None
                }

        except Exception as e:
            return {
                "success": False,
                "data": [],
                "total": 0,
                "error": str(e)
            }

    def get_org_tasks(self, org_id, status=None, unassigned_only=False):
        """
        Get tasks for a specific organization

        Args:
            org_id (str): Organization ID
            status (str, optional): Filter by task status
            unassigned_only (bool): Only return tasks not assigned to any agent

        Returns:
            dict: Query result with tasks data
        """
        try:
            with self.session_scope() as s:
                query = s.query(DBAgentTask).filter(DBAgentTask.org_id == org_id)

                if status:
                    query = query.filter(DBAgentTask.status == status)

                if unassigned_only:
                    query = query.filter(DBAgentTask.agent_id.is_(None))

                tasks = query.all()
                result_data = [task.to_dict() for task in tasks]

                return {
                    "success": True,
                    "data": result_data,
                    "total": len(result_data),
                    "error": None
                }

        except Exception as e:
            return {
                "success": False,
                "data": [],
                "total": 0,
                "error": str(e)
            }

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

    # ========== Agent-Skill Relationship Management =================

    def add_agent_skill(self, agent_id, skill_id):
        """Add skill to agent"""
        try:
            with self.session_scope() as s:
                # Check if agent exists
                agent = s.get(DBAgent, agent_id)
                if not agent:
                    return {"success": False, "error": f"Agent {agent_id} not found"}

                # Check if skill exists
                skill = s.get(DBAgentSkill, skill_id)
                if not skill:
                    return {"success": False, "error": f"Skill {skill_id} not found"}

                # Check if relationship already exists
                if skill in agent.skills:
                    return {"success": False, "error": "Agent already has this skill"}

                # Add skill to agent
                agent.skills.append(skill)
                s.flush()

                return {"success": True, "error": None}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def remove_agent_skill(self, agent_id, skill_id):
        """Remove skill from agent"""
        try:
            with self.session_scope() as s:
                # Check if agent exists
                agent = s.get(DBAgent, agent_id)
                if not agent:
                    return {"success": False, "error": f"Agent {agent_id} not found"}

                # Check if skill exists
                skill = s.get(DBAgentSkill, skill_id)
                if not skill:
                    return {"success": False, "error": f"Skill {skill_id} not found"}

                # Check if relationship exists
                if skill not in agent.skills:
                    return {"success": False, "error": "Agent does not have this skill"}

                # Remove skill from agent
                agent.skills.remove(skill)
                s.flush()

                return {"success": True, "error": None}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_agent_skills(self, agent_id):
        """Get all skills for an agent"""
        try:
            with self.session_scope() as s:
                agent = s.query(DBAgent).options(joinedload(DBAgent.skills)).filter(DBAgent.id == agent_id).first()
                if not agent:
                    return {"success": False, "data": [], "error": f"Agent {agent_id} not found"}

                skills_data = [skill.to_dict() for skill in agent.skills]
                return {"success": True, "data": skills_data, "error": None}

        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    # ========== Association Table Management =================

    def assign_agent_to_org(self, agent_id: str, org_id: str, role: str = 'member', 
                           permissions: List[str] = None, access_level: str = 'read') -> Dict[str, Any]:
        """Assign an agent to an organization"""
        try:
            with self.session_scope() as s:
                # Check if association already exists
                existing = s.query(DBAgentOrgRel).filter(
                    and_(DBAgentOrgRel.agent_id == agent_id,
                         DBAgentOrgRel.org_id == org_id)
                ).first()
                
                if existing:
                    # Update existing association
                    existing.role = role
                    existing.permissions = permissions or []
                    existing.access_level = access_level
                    existing.status = 'active'
                    s.flush()
                    return {"success": True, "data": existing.to_dict(), "error": None}
                
                # Create new association
                association = DBAgentOrgRel(
                    agent_id=agent_id,
                    org_id=org_id,
                    role=role,
                    permissions=permissions or [],
                    access_level=access_level
                )
                s.add(association)
                s.flush()
                return {"success": True, "data": association.to_dict(), "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def assign_skill_to_agent(self, agent_id: str, skill_id: str, 
                             proficiency_level: str = 'beginner',
                             priority: int = 0) -> Dict[str, Any]:
        """Assign a skill to an agent"""
        try:
            with self.session_scope() as s:
                # Check if association already exists
                existing = s.query(DBAgentSkillRel).filter(
                    and_(DBAgentSkillRel.agent_id == agent_id,
                         DBAgentSkillRel.skill_id == skill_id)
                ).first()
                
                if existing:
                    # Update existing association
                    existing.proficiency_level = proficiency_level
                    existing.priority = priority
                    existing.status = 'active'
                    s.flush()
                    return {"success": True, "data": existing.to_dict(), "error": None}
                
                # Create new association
                association = DBAgentSkillRel(
                    agent_id=agent_id,
                    skill_id=skill_id,
                    proficiency_level=proficiency_level,
                    priority=priority
                )
                s.add(association)
                s.flush()
                return {"success": True, "data": association.to_dict(), "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def assign_task_to_agent(self, agent_id: str, task_id: str, vehicle_id: str,
                            priority: str = 'medium', 
                            execution_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Assign a task to an agent on a specific vehicle"""
        try:
            with self.session_scope() as s:
                # Check for existing running task for same agent-task combination
                existing_running = s.query(DBAgentTaskRel).filter(
                    and_(DBAgentTaskRel.agent_id == agent_id,
                         DBAgentTaskRel.task_id == task_id,
                         DBAgentTaskRel.status == 'running')
                ).first()
                
                if existing_running:
                    return {"success": False, "data": None, 
                           "error": f"Task {task_id} is already running on agent {agent_id}"}
                
                # Create new task assignment
                association = DBAgentTaskRel(
                    agent_id=agent_id,
                    task_id=task_id,
                    vehicle_id=vehicle_id,
                    priority=priority,
                    execution_context=execution_context or {}
                )
                s.add(association)
                s.flush()
                return {"success": True, "data": association.to_dict(), "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def get_agent_organizations(self, agent_id: str) -> Dict[str, Any]:
        """Get all organizations an agent belongs to"""
        try:
            with self.session_scope() as s:
                associations = s.query(DBAgentOrgRel).filter(
                    DBAgentOrgRel.agent_id == agent_id
                ).all()
                return {"success": True, "data": [assoc.to_dict() for assoc in associations], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_agent_skill_associations(self, agent_id: str, status: str = 'active') -> Dict[str, Any]:
        """Get all skills assigned to an agent"""
        try:
            with self.session_scope() as s:
                query = s.query(DBAgentSkillRel).filter(
                    DBAgentSkillRel.agent_id == agent_id
                )
                if status:
                    query = query.filter(DBAgentSkillRel.status == status)
                associations = query.all()
                return {"success": True, "data": [assoc.to_dict() for assoc in associations], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_agent_task_associations(self, agent_id: str, status: str = None) -> Dict[str, Any]:
        """Get all tasks assigned to an agent"""
        try:
            with self.session_scope() as s:
                query = s.query(DBAgentTaskRel).filter(
                    DBAgentTaskRel.agent_id == agent_id
                )
                if status:
                    query = query.filter(DBAgentTaskRel.status == status)
                associations = query.order_by(DBAgentTaskRel.created_at.desc()).all()
                return {"success": True, "data": [assoc.to_dict() for assoc in associations], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_running_tasks(self, agent_id: str) -> Dict[str, Any]:
        """Get all currently running tasks for an agent"""
        return self.get_agent_task_associations(agent_id, status='running')

    def update_task_status(self, agent_id: str, task_id: str, vehicle_id: str, 
                          status: str, result: Dict[str, Any] = None,
                          error_message: str = None) -> Dict[str, Any]:
        """Update the status of a task execution"""
        try:
            with self.session_scope() as s:
                association = s.query(DBAgentTaskRel).filter(
                    and_(DBAgentTaskRel.agent_id == agent_id,
                         DBAgentTaskRel.task_id == task_id,
                         DBAgentTaskRel.vehicle_id == vehicle_id)
                ).first()
                
                if association:
                    association.status = status
                    if result:
                        association.result = result
                    if error_message:
                        association.error_message = error_message
                    
                    # Set completion time for finished tasks
                    if status in ['completed', 'failed', 'cancelled']:
                        association.actual_end = datetime.utcnow()
                    
                    s.flush()
                    return {"success": True, "data": association.to_dict(), "error": None}
                else:
                    return {"success": False, "data": None, "error": "Task assignment not found"}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def get_agent_statistics(self, agent_id: str) -> Dict[str, Any]:
        """Get comprehensive statistics for an agent"""
        try:
            with self.session_scope() as s:
                agent = s.get(DBAgent, agent_id)
                if not agent:
                    return {"success": False, "data": {}, "error": "Agent not found"}
                
                # Count organizations
                org_count = s.query(DBAgentOrgRel).filter(
                    and_(DBAgentOrgRel.agent_id == agent_id,
                         DBAgentOrgRel.status == 'active')
                ).count()
                
                # Count skills
                skill_count = s.query(DBAgentSkillRel).filter(
                    and_(DBAgentSkillRel.agent_id == agent_id,
                         DBAgentSkillRel.status == 'active')
                ).count()
                
                # Count tasks
                total_tasks = s.query(DBAgentTaskRel).filter(
                    DBAgentTaskRel.agent_id == agent_id
                ).count()
                
                running_tasks = s.query(DBAgentTaskRel).filter(
                    and_(DBAgentTaskRel.agent_id == agent_id,
                         DBAgentTaskRel.status == 'running')
                ).count()
                
                completed_tasks = s.query(DBAgentTaskRel).filter(
                    and_(DBAgentTaskRel.agent_id == agent_id,
                         DBAgentTaskRel.status == 'completed')
                ).count()
                
                stats = {
                    'agent_id': agent_id,
                    'agent_name': agent.name,
                    'status': agent.status,
                    'organizations': org_count,
                    'skills': skill_count,
                    'tasks': {
                        'total': total_tasks,
                        'running': running_tasks,
                        'completed': completed_tasks
                    }
                }
                
                return {"success": True, "data": stats, "error": None}
        except Exception as e:
            return {"success": False, "data": {}, "error": str(e)}

    def get_agents_by_org(self, org_id: str) -> Dict[str, Any]:
        """
        Get all agents in a specific organization
        
        Args:
            org_id (str): Organization ID
            
        Returns:
            dict: Standard response with agents data
        """
        try:
            with self.session_scope() as session:
                # Query agents through the association table
                agents = session.query(DBAgent).join(
                    DBAgentOrgRel, DBAgent.id == DBAgentOrgRel.agent_id
                ).filter(
                    DBAgentOrgRel.org_id == org_id,
                    DBAgentOrgRel.status == 'active'
                ).all()
                
                return {
                    "success": True,
                    "data": [agent.to_dict() for agent in agents],
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    def update_agent(self, agent_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an agent with proper data type conversion
        
        Args:
            agent_id (str): Agent ID
            data (dict): Updated agent data
            
        Returns:
            dict: Standard response with success status and data
        """
        try:
            # Convert list/dict fields to JSON strings for SQLite compatibility
            processed_data = data.copy()
            
            logger.debug(f"[DBAgentService] update_agent called with fields: {list(data.keys())}")
            
            # List of fields that should be stored as JSON strings
            json_fields = ['personalities', 'tasks', 'skills']
            
            for field in json_fields:
                if field in processed_data:
                    value = processed_data[field]
                    logger.debug(f"[DBAgentService] Processing field '{field}': type={type(value).__name__}, value={value}")
                    
                    # If already a string (from frontend), keep it as is
                    if isinstance(value, str):
                        logger.debug(f"[DBAgentService] Field '{field}' is already a JSON string")
                        # Validate it's valid JSON
                        try:
                            json.loads(value)
                        except:
                            logger.warning(f"[DBAgentService] Field '{field}' is not valid JSON, converting to array")
                            processed_data[field] = json.dumps([value])
                    elif isinstance(value, (list, dict)):
                        processed_data[field] = json.dumps(value)
                        # logger.debug(f"[DBAgentService] Converted '{field}' to JSON: {processed_data[field]}")
                    elif value is None:
                        processed_data[field] = '[]'  # Empty array as default
                        # logger.debug(f"[DBAgentService] Set '{field}' to empty array")
            
            # Handle title field (now stored as JSON array, same as other list fields)
            if 'title' in processed_data:
                value = processed_data['title']
                logger.debug(f"[DBAgentService] Processing title field: type={type(value).__name__}, value={value}")
                
                if isinstance(value, list):
                    # Convert list to JSON string
                    processed_data['title'] = json.dumps(value)
                    # logger.debug(f"[DBAgentService] Converted title list to JSON: {processed_data['title']}")
                elif isinstance(value, str):
                    # Check if it's a comma-separated string (from frontend Select)
                    if ',' in value:
                        # Split by comma and convert to array
                        title_array = [t.strip() for t in value.split(',') if t.strip()]
                        processed_data['title'] = json.dumps(title_array)
                        # logger.debug(f"[DBAgentService] Converted comma-separated title to JSON array: {processed_data['title']}")
                    else:
                        # Check if it's already a JSON string
                        try:
                            parsed = json.loads(value)
                            if isinstance(parsed, list):
                                # Already a JSON array string, keep it
                                # logger.debug(f"[DBAgentService] title is already a JSON array string")
                                pass
                            else:
                                # Single string, convert to array
                                processed_data['title'] = json.dumps([value])
                                # logger.debug(f"[DBAgentService] Converted single title string to JSON array")
                        except:
                            # Not JSON, treat as single value and convert to array
                            processed_data['title'] = json.dumps([value])
                            # logger.debug(f"[DBAgentService] Wrapped title string in JSON array")
                elif value is None:
                    processed_data['title'] = '[]'
                    logger.debug(f"[DBAgentService] Set title to empty array")
            
            # Handle extra_data field (should be JSON string or dict)
            if 'extra_data' in processed_data:
                value = processed_data['extra_data']
                if isinstance(value, str):
                    # Already a JSON string, keep it
                    logger.debug(f"[DBAgentService] extra_data is already a JSON string")
                elif isinstance(value, dict):
                    processed_data['extra_data'] = json.dumps(value)
                    # logger.debug(f"[DBAgentService] Converted extra_data to JSON")
                elif value is None:
                    processed_data['extra_data'] = '{}'
            
            with self.session_scope() as session:
                agent = session.get(DBAgent, agent_id)
                if not agent:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"Agent with id {agent_id} not found"
                    }
                
                # Extract relationship fields before updating agent
                # These are not direct DBAgent fields, but relationship table fields
                skills_data = data.get('skills')
                tasks_data = data.get('tasks')
                org_id = data.get('org_id')
                vehicle_id = data.get('vehicle_id')  # Used for task relationships
                
                # Fields that should not be set on DBAgent model (handled separately)
                # These are relationship table fields, not direct DBAgent fields
                relationship_fields = {'skills', 'tasks', 'org_id'}
                
                # Update agent fields with processed data (excluding relationship fields)
                for key, value in processed_data.items():
                    # Skip relationship fields - they're handled separately below
                    if key in relationship_fields:
                        continue
                    
                    if hasattr(agent, key):
                        setattr(agent, key, value)
                    else:
                        logger.warning(f"[DBAgentService] Skipping unknown field: {key}")
                
                # Update agent-skill relationships if skills provided
                if skills_data is not None:
                    # Parse skills if it's a JSON string
                    if isinstance(skills_data, str):
                        try:
                            skills_list = json.loads(skills_data)
                        except:
                            skills_list = [skills_data] if skills_data else []
                    else:
                        skills_list = skills_data if isinstance(skills_data, list) else []
                    
                    logger.debug(f"[DBAgentService] Updating agent-skill relationships: {skills_list}")
                    
                    # Validate all skills exist (in database OR in memory as code-generated skills)
                    valid_skills, invalid_skills = self._validate_items_exist(
                        session, skills_list, DBAgentSkill, 'agent_skills', 'skill'
                    )
                    
                    # Reject update if any invalid skills found
                    if invalid_skills:
                        session.rollback()
                        return {
                            "success": False,
                            "data": None,
                            "error": f"Invalid skills: {', '.join(invalid_skills)}. These skills do not exist in the database.",
                            "invalid_skills": invalid_skills
                        }
                    
                    # Delete existing agent-skill relationships
                    session.query(DBAgentSkillRel).filter(DBAgentSkillRel.agent_id == agent_id).delete()
                    
                    # Add new relationships (only valid skills)
                    for skill_id in valid_skills:
                        rel = DBAgentSkillRel(agent_id=agent_id, skill_id=skill_id)
                        session.add(rel)
                        logger.debug(f"[DBAgentService] Added agent-skill relationship: {agent_id} -> {skill_id}")
                
                # Update agent-task relationships if tasks provided
                if tasks_data is not None:
                    # Parse tasks if it's a JSON string
                    if isinstance(tasks_data, str):
                        try:
                            tasks_list = json.loads(tasks_data)
                        except:
                            tasks_list = [tasks_data] if tasks_data else []
                    else:
                        tasks_list = tasks_data if isinstance(tasks_data, list) else []
                    
                    logger.debug(f"[DBAgentService] Updating agent-task relationships: {tasks_list}")
                    
                    # Validate all tasks exist (in database OR in memory as code-generated tasks)
                    valid_tasks, invalid_tasks = self._validate_items_exist(
                        session, tasks_list, DBAgentTask, 'agent_tasks', 'task'
                    )
                    
                    # Reject update if any invalid tasks found
                    if invalid_tasks:
                        session.rollback()
                        return {
                            "success": False,
                            "data": None,
                            "error": f"Invalid tasks: {', '.join(invalid_tasks)}. These tasks do not exist in the database.",
                            "invalid_tasks": invalid_tasks
                        }
                    
                    # Delete existing agent-task relationships
                    session.query(DBAgentTaskRel).filter(DBAgentTaskRel.agent_id == agent_id).delete()
                    
                    # Get agent's vehicle_id (optional, can be None)
                    agent_vehicle_id = vehicle_id
                    
                    # Add new relationships (only valid tasks)
                    for task_id in valid_tasks:
                        rel = DBAgentTaskRel(
                            agent_id=agent_id, 
                            task_id=task_id,
                            vehicle_id=agent_vehicle_id
                        )
                        session.add(rel)
                        logger.debug(f"[DBAgentService] Added agent-task relationship: {agent_id} -> {task_id} (vehicle: {agent_vehicle_id or 'unassigned'})")
                
                # Update agent-org relationship if org_id provided
                if org_id is not None:
                    logger.debug(f"[DBAgentService] Updating agent-org relationship: {org_id}")
                    
                    # Delete existing agent-org relationships
                    session.query(DBAgentOrgRel).filter(DBAgentOrgRel.agent_id == agent_id).delete()
                    
                    # Add new relationship if org_id is not empty
                    if org_id:
                        rel = DBAgentOrgRel(agent_id=agent_id, org_id=org_id)
                        session.add(rel)
                        logger.debug(f"[DBAgentService] Added agent-org relationship: {agent_id} -> {org_id}")
                
                session.commit()
                session.refresh(agent)
                
                # Convert to dict and add avatar information
                agent_dict = agent.to_dict()
                logger.debug(f"[DBAgentService] Agent after update - avatar_resource_id: {agent.avatar_resource_id}")
                
                # Add avatar information with HTTP URLs
                avatar_service = self._get_avatar_service()
                if avatar_service:
                    avatar_info = avatar_service.get_agent_avatar_info(agent, owner=None)
                    if avatar_info:
                        agent_dict['avatar'] = avatar_info
                        logger.debug(f"[DBAgentService] Avatar info added: {avatar_info.get('id')}")
                    else:
                        logger.warning(f"[DBAgentService] No avatar info returned for agent {agent_id}")
                else:
                    logger.warning(f"[DBAgentService] Avatar service not available")
                
                return {
                    "success": True,
                    "data": agent_dict,
                    "error": None
                }
        except SQLAlchemyError as e:
            logger.error(f"[DBAgentService] Failed to update agent {agent_id}: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    def get_agents_by_orgs(self, org_ids: List[str]) -> Dict[str, Any]:
        """
        Get all agents in multiple organizations
        
        Args:
            org_ids (List[str]): List of organization IDs
            
        Returns:
            dict: Standard response with agents data
        """
        try:
            if not org_ids:
                return {
                    "success": False,
                    "data": None,
                    "error": "No organization IDs provided"
                }
            
            with self.session_scope() as session:
                # Query agents through the association table for multiple orgs
                agents = session.query(DBAgent).join(
                    DBAgentOrgRel, DBAgent.id == DBAgentOrgRel.agent_id
                ).filter(
                    DBAgentOrgRel.org_id.in_(org_ids),
                    DBAgentOrgRel.status == 'active'
                ).distinct().all()  # Use distinct to avoid duplicates if agent is in multiple orgs
                
                return {
                    "success": True,
                    "data": [agent.to_dict() for agent in agents],
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    def deactivate_agent_org_relations(self, agent_id: str) -> Dict[str, Any]:
        """
        Deactivate all agent-organization relationships for an agent

        Args:
            agent_id (str): Agent ID

        Returns:
            dict: Standard response with success status
        """
        try:
            with self.session_scope() as session:
                # Update all active relationships to inactive
                updated_count = session.query(DBAgentOrgRel).filter(
                    DBAgentOrgRel.agent_id == agent_id,
                    DBAgentOrgRel.status == 'active'
                ).update({
                    'status': 'inactive',
                    'leave_date': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc)
                })

                session.flush()

                logger.info(f"[DBAgentService] Deactivated {updated_count} agent-org relationships for agent {agent_id}")

                return {
                    "success": True,
                    "data": {"updated_count": updated_count},
                    "error": None
                }
        except SQLAlchemyError as e:
            logger.error(f"[DBAgentService] Failed to deactivate agent-org relations: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }
