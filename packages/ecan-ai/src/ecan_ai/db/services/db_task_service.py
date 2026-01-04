"""
Task database service.

This module provides database service for agent task management operations.
"""

from sqlalchemy.orm import sessionmaker, joinedload
from ..core import get_engine, get_session_factory, Base
from ..models.task_model import DBAgentTask
from ..models.skill_model import DBAgentSkill
from ..models.association_models import (
    DBAgentTaskRel, DBAgentTaskSkillRel, DBAgentSkillRel
)
from .base_service import BaseService

from contextlib import contextmanager
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import and_, or_, func
from typing import List, Optional, Dict, Any
from datetime import datetime
import re


class DBTaskService(BaseService):
    """Task database service class providing all task-related operations"""

    def __init__(self, engine=None, session=None):
        """
        Initialize task service

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

    # ========== Task CRUD operations =================================

    def add_task(self, data):
        """Add a new task"""
        return self._add(DBAgentTask, data)

    def delete_task(self, task_id):
        """Delete a task and its related associations"""
        try:
            with self.session_scope() as s:
                # First, delete all agent-task relationships
                s.query(DBAgentTaskRel).filter(
                    DBAgentTaskRel.task_id == task_id
                ).delete(synchronize_session=False)
                
                # Then, delete all task-skill relationships
                s.query(DBAgentTaskSkillRel).filter(
                    DBAgentTaskSkillRel.task_id == task_id
                ).delete(synchronize_session=False)
                
                # Finally, delete the task itself
                task = s.get(DBAgentTask, task_id)
                if task:
                    s.delete(task)
                    s.flush()
                    return {"success": True, "id": task_id, "data": None, "error": None}
                else:
                    return {"success": False, "id": task_id, "data": None, "error": "Task not found"}
        except SQLAlchemyError as e:
            return {"success": False, "id": task_id, "data": None, "error": str(e)}

    def update_task(self, task_id, fields):
        """Update a task"""
        return self._update(DBAgentTask, task_id, fields)

    def query_tasks(self, id=None, name=None, description=None):
        """Query tasks"""
        return {"success": True,
                "data": self._search(DBAgentTask, id, name, description),
                "error": None}

    def search_tasks(self, id=None, name=None, description=None):
        """Alias for query_tasks for compatibility"""
        result = self.query_tasks(id, name, description)
        return result.get("data", [])

    # ========== Task-Skill Association Management =================================

    def add_skill_to_task(self, task_id: str, skill_id: str,
                         role: str = 'primary', execution_order: int = 0,
                         is_required: bool = True,
                         skill_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Add a skill requirement to a task"""
        try:
            with self.session_scope() as s:
                # Check if association already exists
                existing = s.query(DBAgentTaskSkillRel).filter(
                    and_(DBAgentTaskSkillRel.task_id == task_id,
                         DBAgentTaskSkillRel.skill_id == skill_id)
                ).first()
                
                if existing:
                    # Update existing association
                    existing.role = role
                    existing.execution_order = execution_order
                    existing.is_required = is_required
                    existing.skill_config = skill_config or {}
                    s.flush()
                    return {"success": True, "data": existing.to_dict(), "error": None}
                
                # Create new association
                association = DBAgentTaskSkillRel(
                    task_id=task_id,
                    skill_id=skill_id,
                    role=role,
                    execution_order=execution_order,
                    is_required=is_required,
                    skill_config=skill_config or {}
                )
                s.add(association)
                s.flush()
                return {"success": True, "data": association.to_dict(), "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def remove_skill_from_task(self, task_id: str, skill_id: str) -> Dict[str, Any]:
        """Remove a skill requirement from a task"""
        try:
            with self.session_scope() as s:
                association = s.query(DBAgentTaskSkillRel).filter(
                    and_(DBAgentTaskSkillRel.task_id == task_id,
                         DBAgentTaskSkillRel.skill_id == skill_id)
                ).first()
                
                if association:
                    s.delete(association)
                    s.flush()
                    return {"success": True, "data": None, "error": None}
                else:
                    return {"success": False, "data": None, "error": "Association not found"}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def get_task_skills(self, task_id: str, role: str = None) -> Dict[str, Any]:
        """Get all skills required for a task"""
        try:
            with self.session_scope() as s:
                query = s.query(DBAgentTaskSkillRel).filter(
                    DBAgentTaskSkillRel.task_id == task_id
                )
                if role:
                    query = query.filter(DBAgentTaskSkillRel.role == role)
                associations = query.order_by(DBAgentTaskSkillRel.execution_order).all()
                return {"success": True, "data": [assoc.to_dict() for assoc in associations], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_required_skills(self, task_id: str) -> Dict[str, Any]:
        """Get only required skills for a task"""
        try:
            with self.session_scope() as s:
                associations = s.query(DBAgentTaskSkillRel).filter(
                    and_(DBAgentTaskSkillRel.task_id == task_id,
                         DBAgentTaskSkillRel.is_required == True)
                ).order_by(DBAgentTaskSkillRel.execution_order).all()
                return {"success": True, "data": [assoc.to_dict() for assoc in associations], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    # ========== Task Execution Management =================================

    def get_task_executions(self, task_id: str, status: str = None) -> Dict[str, Any]:
        """Get all executions of a task"""
        try:
            with self.session_scope() as s:
                query = s.query(DBAgentTaskRel).filter(
                    DBAgentTaskRel.task_id == task_id
                )
                if status:
                    query = query.filter(DBAgentTaskRel.status == status)
                executions = query.order_by(DBAgentTaskRel.created_at.desc()).all()
                return {"success": True, "data": [exec.to_dict() for exec in executions], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_running_executions(self, task_id: str) -> Dict[str, Any]:
        """Get currently running executions of a task"""
        return self.get_task_executions(task_id, status='running')

    # ========== Agent Matching =================================

    def find_capable_agents(self, task_id: str, min_proficiency: str = 'beginner') -> Dict[str, Any]:
        """Find agents capable of executing a task based on skill requirements"""
        try:
            with self.session_scope() as s:
                # Get required skills for the task
                required_skills_result = self.get_required_skills(task_id)
                if not required_skills_result["success"]:
                    return {"success": False, "data": [], "error": required_skills_result["error"]}
                
                required_skills = required_skills_result["data"]
                
                if not required_skills:
                    return {"success": True, "data": [], "error": None}
                
                # Define proficiency levels hierarchy
                proficiency_levels = {
                    'beginner': 1,
                    'intermediate': 2,
                    'advanced': 3,
                    'expert': 4
                }
                
                min_level = proficiency_levels.get(min_proficiency, 1)
                
                # Find agents that have all required skills
                capable_agents = []
                
                # Get all agents with any of the required skills
                skill_ids = [ts['skill_id'] for ts in required_skills]
                agent_skills = s.query(DBAgentSkillRel).filter(
                    and_(DBAgentSkillRel.skill_id.in_(skill_ids),
                         DBAgentSkillRel.status == 'active')
                ).all()
                
                # Group by agent
                agent_skill_map = {}
                for agent_skill in agent_skills:
                    if agent_skill.agent_id not in agent_skill_map:
                        agent_skill_map[agent_skill.agent_id] = []
                    agent_skill_map[agent_skill.agent_id].append(agent_skill)
                
                # Check each agent for all required skills
                for agent_id, skills in agent_skill_map.items():
                    agent_skill_ids = {skill.skill_id for skill in skills}
                    required_skill_ids = {ts['skill_id'] for ts in required_skills}
                    
                    # Check if agent has all required skills
                    if required_skill_ids.issubset(agent_skill_ids):
                        # Check proficiency levels
                        meets_proficiency = True
                        skill_details = []
                        
                        for skill in skills:
                            if skill.skill_id in required_skill_ids:
                                skill_level = proficiency_levels.get(skill.proficiency_level, 1)
                                if skill_level < min_level:
                                    meets_proficiency = False
                                    break
                                skill_details.append({
                                    'skill_id': skill.skill_id,
                                    'proficiency_level': skill.proficiency_level,
                                    'experience_points': skill.experience_points,
                                    'success_rate': skill.success_rate
                                })
                        
                        if meets_proficiency:
                            capable_agents.append({
                                'agent_id': agent_id,
                                'skills': skill_details,
                                'total_experience': sum(s['experience_points'] for s in skill_details),
                                'avg_success_rate': sum(s['success_rate'] for s in skill_details) / len(skill_details)
                            })
                
                # Sort by experience and success rate
                capable_agents.sort(key=lambda x: (x['total_experience'], x['avg_success_rate']), reverse=True)
                
                return {"success": True, "data": capable_agents, "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def estimate_task_duration(self, task_id: str) -> Dict[str, Any]:
        """Estimate task duration based on skill requirements and historical data"""
        try:
            with self.session_scope() as s:
                task_skills_result = self.get_task_skills(task_id)
                if not task_skills_result["success"]:
                    return {"success": False, "data": 0.0, "error": task_skills_result["error"]}
                
                task_skills = task_skills_result["data"]
                
                if not task_skills:
                    return {"success": True, "data": 0.0, "error": None}
                
                total_estimated_duration = 0.0
                
                for task_skill in task_skills:
                    # Use configured estimated duration if available
                    if task_skill.get('estimated_duration'):
                        total_estimated_duration += task_skill['estimated_duration']
                    else:
                        # Calculate based on historical data
                        avg_duration = s.query(func.avg(DBAgentTaskRel.execution_time)).join(
                            DBAgentTaskSkillRel
                        ).filter(
                            and_(DBAgentTaskSkillRel.skill_id == task_skill['skill_id'],
                                 DBAgentTaskRel.status == 'completed',
                                 DBAgentTaskRel.execution_time.isnot(None))
                        ).scalar()
                        
                        if avg_duration:
                            total_estimated_duration += avg_duration
                        else:
                            # Default estimation
                            total_estimated_duration += 300.0  # 5 minutes default
                
                return {"success": True, "data": total_estimated_duration, "error": None}
        except Exception as e:
            return {"success": False, "data": 0.0, "error": str(e)}

    # ========== Task Statistics =================================

    def get_task_statistics(self, task_id: str) -> Dict[str, Any]:
        """Get comprehensive statistics for a task"""
        try:
            with self.session_scope() as s:
                task = s.get(DBAgentTask, task_id)
                if not task:
                    return {"success": False, "data": {}, "error": "Task not found"}
                
                # Count executions
                total_executions = s.query(DBAgentTaskRel).filter(
                    DBAgentTaskRel.task_id == task_id
                ).count()
                
                completed_executions = s.query(DBAgentTaskRel).filter(
                    and_(DBAgentTaskRel.task_id == task_id,
                         DBAgentTaskRel.status == 'completed')
                ).count()
                
                failed_executions = s.query(DBAgentTaskRel).filter(
                    and_(DBAgentTaskRel.task_id == task_id,
                         DBAgentTaskRel.status == 'failed')
                ).count()
                
                running_executions = s.query(DBAgentTaskRel).filter(
                    and_(DBAgentTaskRel.task_id == task_id,
                         DBAgentTaskRel.status == 'running')
                ).count()
                
                # Calculate success rate
                success_rate = 0.0
                if completed_executions + failed_executions > 0:
                    success_rate = completed_executions / (completed_executions + failed_executions)
                
                # Get skill count
                skill_count = s.query(DBAgentTaskSkillRel).filter(
                    DBAgentTaskSkillRel.task_id == task_id
                ).count()
                
                required_skill_count = s.query(DBAgentTaskSkillRel).filter(
                    and_(DBAgentTaskSkillRel.task_id == task_id,
                         DBAgentTaskSkillRel.is_required == True)
                ).count()
                
                # Calculate average execution time
                avg_execution_time = s.query(func.avg(DBAgentTaskRel.execution_time)).filter(
                    and_(DBAgentTaskRel.task_id == task_id,
                         DBAgentTaskRel.status == 'completed',
                         DBAgentTaskRel.execution_time.isnot(None))
                ).scalar() or 0.0
                
                # Get estimated duration
                duration_result = self.estimate_task_duration(task_id)
                estimated_duration = duration_result["data"] if duration_result["success"] else 0.0
                
                stats = {
                    'task_id': task_id,
                    'task_name': task.name,
                    'task_type': task.task_type,
                    'priority': task.priority,
                    'status': task.status,
                    'progress': task.progress,
                    'executions': {
                        'total': total_executions,
                        'completed': completed_executions,
                        'failed': failed_executions,
                        'running': running_executions,
                        'success_rate': success_rate
                    },
                    'skills': {
                        'total': skill_count,
                        'required': required_skill_count
                    },
                    'performance': {
                        'avg_execution_time': avg_execution_time,
                        'estimated_duration': estimated_duration
                    }
                }
                
                return {"success": True, "data": stats, "error": None}
        except Exception as e:
            return {"success": False, "data": {}, "error": str(e)}

    def get_tasks_by_skill(self, skill_id: str, role: str = None) -> Dict[str, Any]:
        """Get all tasks that require a specific skill"""
        try:
            with self.session_scope() as s:
                query = s.query(DBAgentTaskSkillRel).filter(
                    DBAgentTaskSkillRel.skill_id == skill_id
                )
                if role:
                    query = query.filter(DBAgentTaskSkillRel.role == role)
                associations = query.all()
                return {"success": True, "data": [assoc.to_dict() for assoc in associations], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def clone_task(self, task_id: str, new_name: str = None) -> Dict[str, Any]:
        """Clone a task with all its skill requirements"""
        try:
            with self.session_scope() as s:
                original_task = s.get(DBAgentTask, task_id)
                if not original_task:
                    return {"success": False, "data": None, "error": "Task not found"}
                
                # Create new task
                task_data = original_task.to_dict()
                task_data.pop('id', None)  # Remove ID to create new one
                task_data.pop('created_at', None)
                task_data.pop('updated_at', None)
                
                if new_name:
                    task_data['name'] = new_name
                else:
                    task_data['name'] = f"{original_task.name} (Copy)"
                
                new_task_result = self.add_task(task_data)
                if not new_task_result["success"]:
                    return new_task_result
                
                new_task_id = new_task_result["id"]
                
                # Copy skill requirements
                original_skills_result = self.get_task_skills(task_id)
                if original_skills_result["success"]:
                    for skill_assoc in original_skills_result["data"]:
                        self.add_skill_to_task(
                            new_task_id,
                            skill_assoc['skill_id'],
                            role=skill_assoc['role'],
                            execution_order=skill_assoc['execution_order'],
                            is_required=skill_assoc['is_required'],
                            skill_config=skill_assoc['skill_config']
                        )
                
                return {"success": True, "data": new_task_result["data"], "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}
