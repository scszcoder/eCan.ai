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
from datetime import datetime
import re


class DBAgentService(BaseService):
    """Agent database service class providing all agent-related operations"""

    def __init__(self, engine=None, session=None):
        """
        Initialize agent service

        Args:
            engine: SQLAlchemy engine instance (required)
            session: SQLAlchemy session instance (optional)
        """
        # Call parent class initialization
        super().__init__(engine, session)


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

                # Add eager loading for relationships
                if include_org:
                    query = query.options(joinedload(DBAgent.organization))
                if include_skills:
                    query = query.options(joinedload(DBAgent.skills))
                if include_tasks:
                    query = query.options(joinedload(DBAgent.tasks))

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

                    # Add additional computed fields for frontend
                    agent_dict['skills_count'] = len(agent.skills) if hasattr(agent, 'skills') and agent.skills else 0
                    agent_dict['tasks_count'] = len(agent.tasks) if hasattr(agent, 'tasks') and agent.tasks else 0
                    agent_dict['active_tasks_count'] = len([t for t in (agent.tasks or []) if t.status in ['pending', 'running']])

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
                existing = s.query(AgentOrgAssociation).filter(
                    and_(AgentOrgAssociation.agent_id == agent_id,
                         AgentOrgAssociation.org_id == org_id)
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
                association = AgentOrgAssociation(
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
                existing = s.query(AgentSkillAssociation).filter(
                    and_(AgentSkillAssociation.agent_id == agent_id,
                         AgentSkillAssociation.skill_id == skill_id)
                ).first()
                
                if existing:
                    # Update existing association
                    existing.proficiency_level = proficiency_level
                    existing.priority = priority
                    existing.status = 'active'
                    s.flush()
                    return {"success": True, "data": existing.to_dict(), "error": None}
                
                # Create new association
                association = AgentSkillAssociation(
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
                existing_running = s.query(AgentTaskAssociation).filter(
                    and_(AgentTaskAssociation.agent_id == agent_id,
                         AgentTaskAssociation.task_id == task_id,
                         AgentTaskAssociation.status == 'running')
                ).first()
                
                if existing_running:
                    return {"success": False, "data": None, 
                           "error": f"Task {task_id} is already running on agent {agent_id}"}
                
                # Create new task assignment
                association = AgentTaskAssociation(
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
                associations = s.query(AgentOrgAssociation).filter(
                    AgentOrgAssociation.agent_id == agent_id
                ).all()
                return {"success": True, "data": [assoc.to_dict() for assoc in associations], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_agent_skill_associations(self, agent_id: str, status: str = 'active') -> Dict[str, Any]:
        """Get all skills assigned to an agent"""
        try:
            with self.session_scope() as s:
                query = s.query(AgentSkillAssociation).filter(
                    AgentSkillAssociation.agent_id == agent_id
                )
                if status:
                    query = query.filter(AgentSkillAssociation.status == status)
                associations = query.all()
                return {"success": True, "data": [assoc.to_dict() for assoc in associations], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_agent_task_associations(self, agent_id: str, status: str = None) -> Dict[str, Any]:
        """Get all tasks assigned to an agent"""
        try:
            with self.session_scope() as s:
                query = s.query(AgentTaskAssociation).filter(
                    AgentTaskAssociation.agent_id == agent_id
                )
                if status:
                    query = query.filter(AgentTaskAssociation.status == status)
                associations = query.order_by(AgentTaskAssociation.created_at.desc()).all()
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
                association = s.query(AgentTaskAssociation).filter(
                    and_(AgentTaskAssociation.agent_id == agent_id,
                         AgentTaskAssociation.task_id == task_id,
                         AgentTaskAssociation.vehicle_id == vehicle_id)
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
                org_count = s.query(AgentOrgAssociation).filter(
                    and_(AgentOrgAssociation.agent_id == agent_id,
                         AgentOrgAssociation.status == 'active')
                ).count()
                
                # Count skills
                skill_count = s.query(AgentSkillAssociation).filter(
                    and_(AgentSkillAssociation.agent_id == agent_id,
                         AgentSkillAssociation.status == 'active')
                ).count()
                
                # Count tasks
                total_tasks = s.query(AgentTaskAssociation).filter(
                    AgentTaskAssociation.agent_id == agent_id
                ).count()
                
                running_tasks = s.query(AgentTaskAssociation).filter(
                    and_(AgentTaskAssociation.agent_id == agent_id,
                         AgentTaskAssociation.status == 'running')
                ).count()
                
                completed_tasks = s.query(AgentTaskAssociation).filter(
                    and_(AgentTaskAssociation.agent_id == agent_id,
                         AgentTaskAssociation.status == 'completed')
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
        Update an agent
        
        Args:
            agent_id (str): Agent ID
            data (dict): Updated agent data
            
        Returns:
            dict: Standard response with success status and data
        """
        try:
            with self.session_scope() as session:
                agent = session.get(DBAgent, agent_id)
                if not agent:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"Agent with id {agent_id} not found"
                    }
                
                # Update agent fields
                for key, value in data.items():
                    if hasattr(agent, key):
                        setattr(agent, key, value)
                
                session.flush()
                
                return {
                    "success": True,
                    "data": agent.to_dict(),
                    "error": None
                }
        except SQLAlchemyError as e:
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
                    "success": True,
                    "data": [],
                    "error": None
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
