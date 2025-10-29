"""
Skill database service.

This module provides database service for skill management operations.
"""

from ..models.skill_model import DBAgentSkill
from ..models.tool_model import DBAgentTool
from ..models.knowledge_model import DBAgentKnowledge
from ..models.association_models import (
    DBSkillToolRel, DBAgentSkillKnowledgeRel,
    DBAgentSkillRel, DBAgentTaskSkillRel
)
from .base_service import BaseService

from contextlib import contextmanager
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import and_, or_, func
from typing import List, Optional, Dict, Any
from datetime import datetime
import re


class DBSkillService(BaseService):
    """Skill database service class providing all skill-related operations"""

    def __init__(self, engine=None, session=None):
        """
        Initialize skill service

        Args:
            engine: SQLAlchemy engine instance (required)
            session: SQLAlchemy session instance (optional)
        """
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
    
    def search_skills(self, id=None, name=None, description=None):
        """Alias for query_skills for compatibility"""
        result = self.query_skills(id, name, description)
        return result.get("data", [])

    def get_skill_by_id(self, skill_id):
        """Get a skill by ID"""
        try:
            with self.session_scope() as s:
                skill = s.get(DBAgentSkill, skill_id)
                if skill:
                    return {"success": True, "data": skill.to_dict(), "error": None}
                else:
                    return {"success": False, "data": None, "error": "Skill not found"}
        except SQLAlchemyError as e:
            return {"success": False, "data": None, "error": str(e)}
    
    def get_skill_by_path(self, path):
        """Get a skill by file path"""
        try:
            with self.session_scope() as s:
                skill = s.query(DBAgentSkill).filter(DBAgentSkill.path == path).first()
                if skill:
                    return {"success": True, "data": skill.to_dict(), "error": None}
                else:
                    return {"success": False, "data": None, "error": "Skill not found"}
        except SQLAlchemyError as e:
            return {"success": False, "data": None, "error": str(e)}

    def get_skills_by_owner(self, owner):
        """Get all skills by owner"""
        try:
            with self.session_scope() as s:
                skills = s.query(DBAgentSkill).filter(DBAgentSkill.owner == owner).all()
                return {"success": True, "data": [skill.to_dict() for skill in skills], "error": None}
        except SQLAlchemyError as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_public_skills(self):
        """Get all public skills"""
        try:
            with self.session_scope() as s:
                skills = s.query(DBAgentSkill).filter(DBAgentSkill.public == True).all()
                return {"success": True, "data": [skill.to_dict() for skill in skills], "error": None}
        except SQLAlchemyError as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_rentable_skills(self):
        """Get all rentable skills"""
        try:
            with self.session_scope() as s:
                skills = s.query(DBAgentSkill).filter(DBAgentSkill.rentable == True).all()
                return {"success": True, "data": [skill.to_dict() for skill in skills], "error": None}
        except SQLAlchemyError as e:
            return {"success": False, "data": [], "error": str(e)}

    # ========== Skill-Tool Association Management =================

    def add_tool_to_skill(self, skill_id: str, tool_id: str,
                         dependency_type: str = 'required',
                         usage_frequency: str = 'medium',
                         importance: int = 1,
                         tool_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Add a tool dependency to a skill"""
        try:
            with self.session_scope() as s:
                # Check if association already exists
                existing = s.query(DBSkillToolRel).filter(
                    and_(DBSkillToolRel.skill_id == skill_id,
                         DBSkillToolRel.tool_id == tool_id)
                ).first()
                
                if existing:
                    # Update existing association
                    existing.dependency_type = dependency_type
                    existing.usage_frequency = usage_frequency
                    existing.importance = importance
                    existing.tool_config = tool_config or {}
                    s.flush()
                    return {"success": True, "data": existing.to_dict(), "error": None}
                
                # Create new association
                association = DBSkillToolRel(
                    skill_id=skill_id,
                    tool_id=tool_id,
                    dependency_type=dependency_type,
                    usage_frequency=usage_frequency,
                    importance=importance,
                    tool_config=tool_config or {}
                )
                s.add(association)
                s.flush()
                return {"success": True, "data": association.to_dict(), "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def remove_tool_from_skill(self, skill_id: str, tool_id: str) -> Dict[str, Any]:
        """Remove a tool dependency from a skill"""
        try:
            with self.session_scope() as s:
                association = s.query(DBSkillToolRel).filter(
                    and_(DBSkillToolRel.skill_id == skill_id,
                         DBSkillToolRel.tool_id == tool_id)
                ).first()
                
                if association:
                    s.delete(association)
                    s.flush()
                    return {"success": True, "data": None, "error": None}
                else:
                    return {"success": False, "data": None, "error": "Association not found"}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def get_skill_tools(self, skill_id: str, dependency_type: str = None) -> Dict[str, Any]:
        """Get all tools required by a skill"""
        try:
            with self.session_scope() as s:
                query = s.query(DBSkillToolRel).filter(
                    DBSkillToolRel.skill_id == skill_id
                )
                if dependency_type:
                    query = query.filter(DBSkillToolRel.dependency_type == dependency_type)
                associations = query.order_by(DBSkillToolRel.importance.desc()).all()
                return {"success": True, "data": [assoc.to_dict() for assoc in associations], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_required_tools(self, skill_id: str) -> Dict[str, Any]:
        """Get only required tools for a skill"""
        return self.get_skill_tools(skill_id, dependency_type='required')

    # ========== Skill-Knowledge Association Management =================

    def add_knowledge_to_skill(self, skill_id: str, knowledge_id: str,
                              dependency_type: str = 'required',
                              access_pattern: str = 'read',
                              knowledge_scope: List[str] = None) -> Dict[str, Any]:
        """Add a knowledge dependency to a skill"""
        try:
            with self.session_scope() as s:
                # Check if association already exists
                existing = s.query(DBAgentSkillKnowledgeRel).filter(
                    and_(DBAgentSkillKnowledgeRel.skill_id == skill_id,
                         DBAgentSkillKnowledgeRel.knowledge_id == knowledge_id)
                ).first()
                
                if existing:
                    # Update existing association
                    existing.dependency_type = dependency_type
                    existing.access_pattern = access_pattern
                    existing.knowledge_scope = knowledge_scope or []
                    s.flush()
                    return {"success": True, "data": existing.to_dict(), "error": None}
                
                # Create new association
                association = DBAgentSkillKnowledgeRel(
                    skill_id=skill_id,
                    knowledge_id=knowledge_id,
                    dependency_type=dependency_type,
                    access_pattern=access_pattern,
                    knowledge_scope=knowledge_scope or []
                )
                s.add(association)
                s.flush()
                return {"success": True, "data": association.to_dict(), "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def remove_knowledge_from_skill(self, skill_id: str, knowledge_id: str) -> Dict[str, Any]:
        """Remove a knowledge dependency from a skill"""
        try:
            with self.session_scope() as s:
                association = s.query(DBAgentSkillKnowledgeRel).filter(
                    and_(DBAgentSkillKnowledgeRel.skill_id == skill_id,
                         DBAgentSkillKnowledgeRel.knowledge_id == knowledge_id)
                ).first()
                
                if association:
                    s.delete(association)
                    s.flush()
                    return {"success": True, "data": None, "error": None}
                else:
                    return {"success": False, "data": None, "error": "Association not found"}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def get_skill_knowledges(self, skill_id: str, dependency_type: str = None) -> Dict[str, Any]:
        """Get all knowledge bases required by a skill"""
        try:
            with self.session_scope() as s:
                query = s.query(DBAgentSkillKnowledgeRel).filter(
                    DBAgentSkillKnowledgeRel.skill_id == skill_id
                )
                if dependency_type:
                    query = query.filter(DBAgentSkillKnowledgeRel.dependency_type == dependency_type)
                associations = query.order_by(DBAgentSkillKnowledgeRel.importance.desc()).all()
                return {"success": True, "data": [assoc.to_dict() for assoc in associations], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_required_knowledges(self, skill_id: str) -> Dict[str, Any]:
        """Get only required knowledge bases for a skill"""
        return self.get_skill_knowledges(skill_id, dependency_type='required')

    # ========== Skill Dependencies Validation =================

    def check_skill_dependencies(self, skill_id: str) -> Dict[str, Any]:
        """Check if all skill dependencies are available and valid"""
        try:
            with self.session_scope() as s:
                skill = s.get(DBAgentSkill, skill_id)
                if not skill:
                    return {"success": False, "data": {}, "error": "Skill not found"}
                
                # Check tool dependencies
                tool_deps_result = self.get_skill_tools(skill_id)
                tool_dependencies = tool_deps_result["data"] if tool_deps_result["success"] else []
                
                missing_tools = []
                invalid_tools = []
                
                for tool_dep in tool_dependencies:
                    tool = s.get(DBAgentTool, tool_dep['tool_id'])
                    if not tool:
                        missing_tools.append(tool_dep['tool_id'])
                    elif tool.status != 'active':
                        invalid_tools.append(tool_dep['tool_id'])
                
                # Check knowledge dependencies
                knowledge_deps_result = self.get_skill_knowledges(skill_id)
                knowledge_dependencies = knowledge_deps_result["data"] if knowledge_deps_result["success"] else []
                
                missing_knowledges = []
                invalid_knowledges = []
                
                for knowledge_dep in knowledge_dependencies:
                    knowledge = s.get(DBAgentKnowledge, knowledge_dep['knowledge_id'])
                    if not knowledge:
                        missing_knowledges.append(knowledge_dep['knowledge_id'])
                    elif knowledge.status != 'active':
                        invalid_knowledges.append(knowledge_dep['knowledge_id'])
                
                # Determine overall status
                is_valid = (len(missing_tools) == 0 and len(invalid_tools) == 0 and
                           len(missing_knowledges) == 0 and len(invalid_knowledges) == 0)
                
                dependency_check = {
                    'skill_id': skill_id,
                    'skill_name': skill.name,
                    'is_valid': is_valid,
                    'tools': {
                        'total': len(tool_dependencies),
                        'missing': missing_tools,
                        'invalid': invalid_tools
                    },
                    'knowledges': {
                        'total': len(knowledge_dependencies),
                        'missing': missing_knowledges,
                        'invalid': invalid_knowledges
                    }
                }
                
                return {"success": True, "data": dependency_check, "error": None}
        except Exception as e:
            return {"success": False, "data": {}, "error": str(e)}

    # ========== Skill Statistics =================

    def get_skill_statistics(self, skill_id: str) -> Dict[str, Any]:
        """Get comprehensive statistics for a skill"""
        try:
            with self.session_scope() as s:
                skill = s.get(DBAgentSkill, skill_id)
                if not skill:
                    return {"success": False, "data": {}, "error": "Skill not found"}
                
                # Count dependencies
                tool_count = s.query(DBSkillToolRel).filter(
                    DBSkillToolRel.skill_id == skill_id
                ).count()
                
                knowledge_count = s.query(DBAgentSkillKnowledgeRel).filter(
                    DBAgentSkillKnowledgeRel.skill_id == skill_id
                ).count()
                
                # Count agents using this skill
                agent_count = s.query(DBAgentSkillRel).filter(
                    and_(DBAgentSkillRel.skill_id == skill_id,
                         DBAgentSkillRel.status == 'active')
                ).count()
                
                # Count tasks requiring this skill
                task_count = s.query(DBAgentTaskSkillRel).filter(
                    DBAgentTaskSkillRel.skill_id == skill_id
                ).count()
                
                # Calculate average proficiency of agents
                proficiency_levels = {
                    'beginner': 1, 'intermediate': 2, 'advanced': 3, 'expert': 4
                }
                
                agent_skills = s.query(DBAgentSkillRel).filter(
                    and_(DBAgentSkillRel.skill_id == skill_id,
                         DBAgentSkillRel.status == 'active')
                ).all()
                
                avg_proficiency = 0.0
                if agent_skills:
                    total_proficiency = sum(
                        proficiency_levels.get(assoc.proficiency_level, 1) 
                        for assoc in agent_skills
                    )
                    avg_proficiency = total_proficiency / len(agent_skills)
                
                # Calculate average success rate
                avg_success_rate = 0.0
                if agent_skills:
                    success_rates = [assoc.success_rate for assoc in agent_skills if assoc.success_rate is not None]
                    if success_rates:
                        avg_success_rate = sum(success_rates) / len(success_rates)
                
                stats = {
                    'skill_id': skill_id,
                    'skill_name': skill.name,
                    'skill_level': skill.level,
                    'version': skill.version,
                    'public': skill.public,
                    'rentable': skill.rentable,
                    'dependencies': {
                        'tools': tool_count,
                        'knowledges': knowledge_count
                    },
                    'usage': {
                        'agents': agent_count,
                        'tasks': task_count,
                        'avg_proficiency': avg_proficiency,
                        'avg_success_rate': avg_success_rate
                    }
                }
                
                return {"success": True, "data": stats, "error": None}
        except Exception as e:
            return {"success": False, "data": {}, "error": str(e)}

    def get_skills_by_tool(self, tool_id: str, dependency_type: str = None) -> Dict[str, Any]:
        """Get all skills that depend on a specific tool"""
        try:
            with self.session_scope() as s:
                query = s.query(DBSkillToolRel).filter(
                    DBSkillToolRel.tool_id == tool_id
                )
                if dependency_type:
                    query = query.filter(DBSkillToolRel.dependency_type == dependency_type)
                associations = query.all()
                return {"success": True, "data": [assoc.to_dict() for assoc in associations], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_skills_by_knowledge(self, knowledge_id: str, dependency_type: str = None) -> Dict[str, Any]:
        """Get all skills that depend on a specific knowledge base"""
        try:
            with self.session_scope() as s:
                query = s.query(DBAgentSkillKnowledgeRel).filter(
                    DBAgentSkillKnowledgeRel.knowledge_id == knowledge_id
                )
                if dependency_type:
                    query = query.filter(DBAgentSkillKnowledgeRel.dependency_type == dependency_type)
                associations = query.all()
                return {"success": True, "data": [assoc.to_dict() for assoc in associations], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

