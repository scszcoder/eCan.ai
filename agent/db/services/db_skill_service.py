"""
Skill database service.

This module provides database service for skill management operations.
"""

from ..models.skill_model import DBAgentSkill, DBAgentSkillReview
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
        """Add a new skill, or update if ID already exists (upsert by ID)
        
        This prevents duplicate skills when the same skill is saved multiple times
        with the same ID (e.g., from cloud sync or multiple save operations).
        """
        try:
            skill_id = data.get('id')

            with self.session_scope() as s:
                # Check if a skill with the same ID already exists
                if skill_id:
                    existing = s.query(DBAgentSkill).filter(
                        DBAgentSkill.id == skill_id
                    ).first()
                    
                    if existing:
                        # Update existing record instead of creating duplicate
                        for key, value in data.items():
                            if hasattr(existing, key):
                                setattr(existing, key, value)
                        s.flush()
                        return {"success": True, "id": existing.id, "data": existing.to_dict(), "error": None, "updated": True}

                # No duplicate found, create new record
                # Filter to only DB-model columns to avoid TypeError from extra fields
                # added by _prepare_skill_data (e.g. skill_owner, status, run_mode,
                # mapping_rules, ui_info). These are stored inside config/owner, not as
                # separate columns.
                db_columns = {c.name for c in DBAgentSkill.__table__.columns}
                db_data = {k: v for k, v in data.items() if k in db_columns}
                obj = DBAgentSkill(**db_data)
                s.add(obj)
                s.flush()
                return {"success": True, "id": obj.id, "data": obj.to_dict(), "error": None, "updated": False}

        except SQLAlchemyError as e:
            return {"success": False, "id": data.get("id"), "data": None, "error": str(e)}

    def delete_skill(self, skill_id):
        """Delete a skill and all its relationships"""
        try:
            with self.session_scope() as s:
                # First, try to find the skill by id
                skill = s.get(DBAgentSkill, skill_id)
                
                # If not found by id, try by cloud_id (for cloud-synced skills)
                if not skill:
                    skill = s.query(DBAgentSkill).filter(
                        DBAgentSkill.cloud_id == skill_id
                    ).first()
                
                if not skill:
                    # Try to find by askid as fallback (for legacy numeric askid)
                    try:
                        askid_num = int(skill_id) if skill_id.isdigit() else None
                        if askid_num:
                            skill = s.query(DBAgentSkill).filter(
                                DBAgentSkill.askid == askid_num
                            ).first()
                    except (ValueError, TypeError):
                        pass
                
                if not skill:
                    return {"success": False, "id": skill_id, "data": None, "error": "Skill not found"}
                
                actual_skill_id = skill.id
                
                # Delete all related records to avoid foreign key constraint issues
                # Delete agent-skill relationships
                s.query(DBAgentSkillRel).filter(DBAgentSkillRel.skill_id == actual_skill_id).delete()
                
                # Delete skill-tool relationships
                s.query(DBSkillToolRel).filter(DBSkillToolRel.skill_id == actual_skill_id).delete()
                
                # Delete skill-knowledge relationships
                s.query(DBAgentSkillKnowledgeRel).filter(DBAgentSkillKnowledgeRel.skill_id == actual_skill_id).delete()
                
                # Delete task-skill relationships
                s.query(DBAgentTaskSkillRel).filter(DBAgentTaskSkillRel.skill_id == actual_skill_id).delete()
                
                # Finally, delete the skill itself
                s.delete(skill)
                s.flush()
                return {"success": True, "id": actual_skill_id, "data": None, "error": None}
        except SQLAlchemyError as e:
            return {"success": False, "id": skill_id, "data": None, "error": str(e)}

    def update_skill(self, skill_id, fields):
        """Update a skill"""
        return self._update(DBAgentSkill, skill_id, fields)

    def update_skill_askid(self, skill_id, askid):
        """Update the cloud askid for a skill.

        Called after a successful cloud ADD to link the local record to its cloud id,
        preventing duplicate entries on app restart.
        """
        return self.update_skill(skill_id, {"askid": askid})

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
        """Get a skill by primary id, or by cloud_id / askid (same resolution as delete_skill)."""
        if not skill_id:
            return {"success": False, "data": None, "error": "Skill not found"}
        try:
            with self.session_scope() as s:
                skill = s.get(DBAgentSkill, skill_id)
                if skill:
                    return {"success": True, "data": skill.to_dict(), "error": None}
                skill = s.query(DBAgentSkill).filter(
                    DBAgentSkill.cloud_id == str(skill_id)
                ).first()
                if skill:
                    return {"success": True, "data": skill.to_dict(), "error": None}
                try:
                    askid_num = int(skill_id) if str(skill_id).isdigit() else None
                    if askid_num:
                        skill = s.query(DBAgentSkill).filter(
                            DBAgentSkill.askid == askid_num
                        ).first()
                        if skill:
                            return {"success": True, "data": skill.to_dict(), "error": None}
                except (ValueError, TypeError):
                    pass
                return {"success": False, "data": None, "error": "Skill not found"}
        except SQLAlchemyError as e:
            return {"success": False, "data": None, "error": str(e)}
    
    def get_skill_by_path(self, path):
        """Get a skill by file path
        
        Handles Chinese characters in file paths by normalizing paths before comparison.
        This ensures that skills with Chinese filenames can be correctly queried.
        """
        try:
            import os
            # Normalize the input path to handle Chinese characters correctly
            # Convert to absolute path and normalize separators
            normalized_path = os.path.abspath(os.path.normpath(path))
            
            with self.session_scope() as s:
                # Try exact match first
                skill = s.query(DBAgentSkill).filter(DBAgentSkill.path == normalized_path).first()
                
                # If not found, try to match by normalizing all stored paths
                # This handles cases where paths were stored with different encodings
                if not skill:
                    all_skills = s.query(DBAgentSkill).all()
                    for sk in all_skills:
                        if sk.path:
                            try:
                                stored_normalized = os.path.abspath(os.path.normpath(sk.path))
                                if stored_normalized == normalized_path:
                                    skill = sk
                                    break
                            except Exception:
                                continue
                
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

    # ========== Reviews / Ratings (DBAgentSkillReview) ==========

    def upsert_skill_review(self, skill_id: str, reviewer_id: str,
                            rating: int, review_text: str = "") -> Dict[str, Any]:
        """Create or update a review for a skill. One review per (skill, reviewer)."""
        try:
            rating = max(1, min(5, int(rating)))
            with self.session_scope() as s:
                existing = s.query(DBAgentSkillReview).filter(
                    and_(DBAgentSkillReview.skill_id == skill_id,
                         DBAgentSkillReview.reviewer_id == reviewer_id)
                ).first()
                if existing:
                    existing.rating = rating
                    existing.review_text = review_text or ""
                    s.flush()
                    return {"success": True, "id": existing.id, "action": "updated",
                            "data": existing.to_dict(), "error": None}
                review = DBAgentSkillReview(
                    skill_id=skill_id,
                    reviewer_id=reviewer_id,
                    rating=rating,
                    review_text=review_text or "",
                    helpful=0,
                )
                s.add(review)
                s.flush()
                return {"success": True, "id": review.id, "action": "created",
                        "data": review.to_dict(), "error": None}
        except SQLAlchemyError as e:
            return {"success": False, "data": None, "error": str(e)}

    def get_skill_reviews(self, skill_id: str) -> Dict[str, Any]:
        """Return all reviews for a skill, newest first."""
        try:
            with self.session_scope() as s:
                rows = s.query(DBAgentSkillReview).filter(
                    DBAgentSkillReview.skill_id == skill_id
                ).order_by(DBAgentSkillReview.created_at.desc()).all()
                return {"success": True,
                        "data": [r.to_dict() for r in rows],
                        "error": None}
        except SQLAlchemyError as e:
            return {"success": False, "data": [], "error": str(e)}

    def delete_skill_review(self, review_id: str, reviewer_id: str) -> Dict[str, Any]:
        """Delete a review owned by reviewer_id."""
        try:
            with self.session_scope() as s:
                review = s.query(DBAgentSkillReview).filter(
                    and_(DBAgentSkillReview.id == review_id,
                         DBAgentSkillReview.reviewer_id == reviewer_id)
                ).first()
                if not review:
                    return {"success": False, "error": "Review not found or not owned by user"}
                s.delete(review)
                s.flush()
                return {"success": True, "id": review_id}
        except SQLAlchemyError as e:
            return {"success": False, "error": str(e)}

    def get_skill_rating_stats(self, skill_id: str) -> Dict[str, Any]:
        """Aggregate rating stats for a skill: total, avg, helpful, distribution."""
        try:
            with self.session_scope() as s:
                rows = s.query(DBAgentSkillReview).filter(
                    DBAgentSkillReview.skill_id == skill_id
                ).all()
                total = len(rows)
                if total == 0:
                    return {"total": 0, "avgRating": 5.0, "totalHelpful": 0,
                            "distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}}
                dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
                rating_sum = 0
                helpful_sum = 0
                for r in rows:
                    rating_sum += int(r.rating or 0)
                    helpful_sum += int(r.helpful or 0)
                    bucket = max(1, min(5, int(r.rating or 0)))
                    dist[bucket] += 1
                return {
                    "total": total,
                    "avgRating": round(rating_sum / total, 2),
                    "totalHelpful": helpful_sum,
                    "distribution": dist,
                }
        except SQLAlchemyError as e:
            return {"total": 0, "avgRating": 5.0, "totalHelpful": 0,
                    "distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}, "error": str(e)}

    def increment_review_helpful(self, review_id: str) -> Dict[str, Any]:
        """Increment the helpful counter on a review (one-way, no decrement)."""
        try:
            with self.session_scope() as s:
                review = s.get(DBAgentSkillReview, review_id)
                if not review:
                    return {"success": False, "error": "Review not found"}
                review.helpful = (review.helpful or 0) + 1
                s.flush()
                return {"success": True, "helpful": review.helpful}
        except SQLAlchemyError as e:
            return {"success": False, "error": str(e)}

    # ========== Marketplace statistics (downloads / favorites / proficiency) ==========

    def _ensure_ext(self, skill, key: str, default):
        """Read a value from skill.ext (auto-init dict), with safe default."""
        if skill.ext is None or not isinstance(skill.ext, dict):
            return default
        return skill.ext.get(key, default)

    def _set_ext(self, skill, key: str, value):
        if skill.ext is None or not isinstance(skill.ext, dict):
            skill.ext = {}
        skill.ext[key] = value

    def increment_skill_download(self, skill_id: str, delta: int = 1) -> Dict[str, Any]:
        """Increment the download counter (stored in skill.ext.downloadCount)."""
        try:
            with self.session_scope() as s:
                skill = s.get(DBAgentSkill, skill_id)
                if not skill:
                    return {"success": False, "error": "Skill not found"}
                current = int(self._ensure_ext(skill, "downloadCount", 0)) + int(delta)
                self._set_ext(skill, "downloadCount", max(0, current))
                s.flush()
                return {"success": True, "downloadCount": max(0, current)}
        except SQLAlchemyError as e:
            return {"success": False, "error": str(e)}

    def get_skill_marketplace_stats(self, skill_id: str) -> Dict[str, Any]:
        """Return marketplace-level stats for a skill: downloads, favorites, subscribers, rating, reviewCount."""
        try:
            with self.session_scope() as s:
                skill = s.get(DBAgentSkill, skill_id)
                if not skill:
                    return {"success": False, "error": "Skill not found"}
                ext = skill.ext if isinstance(skill.ext, dict) else {}

                # Rating stats from agent_skill_reviews
                review_rows = s.query(DBAgentSkillReview).filter(
                    DBAgentSkillReview.skill_id == skill_id
                ).all()
                review_count = len(review_rows)
                rating_sum = sum(int(r.rating or 0) for r in review_rows)
                avg_rating = round(rating_sum / review_count, 2) if review_count > 0 else 5.0

                return {
                    "success": True,
                    "data": {
                        "skill_id": skill.id,
                        "downloadCount": int(ext.get("downloadCount", 0) or 0),
                        "favoriteCount": int(ext.get("favoriteCount", 0) or 0),
                        "subscriberCount": int(ext.get("subscriberCount", 0) or 0),
                        "lastUsed": ext.get("lastUsed"),
                        "trendingScore": float(ext.get("trendingScore", 0.0) or 0.0),
                        "rating": avg_rating,
                        "reviewCount": review_count,
                    },
                    "error": None,
                }
        except SQLAlchemyError as e:
            return {"success": False, "error": str(e)}

    def get_skill_changelog(self, skill_id: str) -> Dict[str, Any]:
        """Return the changelog (list of {version, date, notes}) from skill.ext.changelog."""
        try:
            with self.session_scope() as s:
                skill = s.get(DBAgentSkill, skill_id)
                if not skill:
                    return {"success": False, "data": [], "error": "Skill not found"}
                ext = skill.ext if isinstance(skill.ext, dict) else {}
                changelog = ext.get("changelog") or []
                if not isinstance(changelog, list):
                    changelog = []
                return {"success": True, "data": changelog, "error": None}
        except SQLAlchemyError as e:
            return {"success": False, "data": [], "error": str(e)}

    def append_skill_changelog(self, skill_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Append a changelog entry {version, date, notes} to skill.ext.changelog."""
        try:
            with self.session_scope() as s:
                skill = s.get(DBAgentSkill, skill_id)
                if not skill:
                    return {"success": False, "error": "Skill not found"}
                ext = skill.ext if isinstance(skill.ext, dict) else {}
                changelog = ext.get("changelog") or []
                if not isinstance(changelog, list):
                    changelog = []
                changelog.insert(0, entry)
                ext["changelog"] = changelog[:50]
                skill.ext = ext
                s.flush()
                return {"success": True, "data": ext["changelog"]}
        except SQLAlchemyError as e:
            return {"success": False, "error": str(e)}

    def record_skill_usage(self, skill_id: str, user_id: str = "") -> Dict[str, Any]:
        """Increment usageCount and update lastUsed timestamp for a skill."""
        try:
            with self.session_scope() as s:
                skill = s.get(DBAgentSkill, skill_id)
                if not skill:
                    return {"success": False, "error": "Skill not found"}
                ext = skill.ext if isinstance(skill.ext, dict) else {}
                ext["usageCount"] = int(ext.get("usageCount", 0) or 0) + 1
                ext["lastUsed"] = datetime.utcnow().isoformat() + "Z"
                skill.ext = ext
                s.flush()
                return {"success": True, "usageCount": ext["usageCount"], "lastUsed": ext["lastUsed"]}
        except SQLAlchemyError as e:
            return {"success": False, "error": str(e)}

    def get_user_skill_proficiency(self, user_id: str, skill_id: str) -> Dict[str, Any]:
        """Return the user's proficiency with a subscribed skill (level + score).

        Stored at skill.ext.user_proficiency.{user_id} = {score, level, updatedAt}.
        Falls back to {score: 0, level: 'entry'} when missing.
        """
        try:
            with self.session_scope() as s:
                skill = s.get(DBAgentSkill, skill_id)
                if not skill:
                    return {"success": False, "error": "Skill not found"}
                ext = skill.ext if isinstance(skill.ext, dict) else {}
                prof = (ext.get("user_proficiency") or {}).get(user_id) or {}
                return {
                    "success": True,
                    "data": {
                        "skill_id": skill_id,
                        "user_id": user_id,
                        "score": int(prof.get("score", 0) or 0),
                        "level": prof.get("level", "entry"),
                        "updatedAt": prof.get("updatedAt"),
                    },
                }
        except SQLAlchemyError as e:
            return {"success": False, "error": str(e)}

    def update_user_skill_proficiency(self, user_id: str, skill_id: str,
                                      score: int, level: str) -> Dict[str, Any]:
        """Update user→skill proficiency record. score is clamped to 0..100."""
        try:
            score = max(0, min(100, int(score)))
            level = (level or "entry").lower()
            if level not in {"entry", "intermediate", "advanced", "expert"}:
                level = "entry"
            with self.session_scope() as s:
                skill = s.get(DBAgentSkill, skill_id)
                if not skill:
                    return {"success": False, "error": "Skill not found"}
                ext = skill.ext if isinstance(skill.ext, dict) else {}
                prof = ext.get("user_proficiency") or {}
                prof[user_id] = {
                    "score": score,
                    "level": level,
                    "updatedAt": datetime.utcnow().isoformat() + "Z",
                }
                ext["user_proficiency"] = prof
                skill.ext = ext
                s.flush()
                return {"success": True, "data": prof[user_id]}
        except SQLAlchemyError as e:
            return {"success": False, "error": str(e)}

    def list_favorite_skills(self, user_id: str) -> Dict[str, Any]:
        """Return all favorite skill IDs for a user (stored on each skill.ext.favorited_by)."""
        try:
            with self.session_scope() as s:
                rows = s.query(DBAgentSkill).all()
                ids = []
                for r in rows:
                    ext = r.ext if isinstance(r.ext, dict) else {}
                    by = ext.get("favorited_by") or []
                    if user_id in by:
                        ids.append(r.id)
                return {"success": True, "data": ids, "error": None}
        except SQLAlchemyError as e:
            return {"success": False, "data": [], "error": str(e)}

    def toggle_skill_favorite(self, user_id: str, skill_id: str) -> Dict[str, Any]:
        """Toggle favorite flag for (user, skill). Returns new favorited state + count."""
        try:
            with self.session_scope() as s:
                skill = s.get(DBAgentSkill, skill_id)
                if not skill:
                    return {"success": False, "error": "Skill not found"}
                ext = skill.ext if isinstance(skill.ext, dict) else {}
                by = ext.get("favorited_by") or []
                if not isinstance(by, list):
                    by = []
                if user_id in by:
                    by.remove(user_id)
                    favorited = False
                else:
                    by.append(user_id)
                    favorited = True
                ext["favorited_by"] = by
                ext["favoriteCount"] = len(by)
                skill.ext = ext
                s.flush()
                return {"success": True, "favorited": favorited,
                        "favoriteCount": len(by), "skill_id": skill_id}
        except SQLAlchemyError as e:
            return {"success": False, "error": str(e)}

    def report_skill(self, skill_id: str, reporter_id: str,
                     reason: str, note: str = "") -> Dict[str, Any]:
        """Record a user-submitted report against a skill.

        Reports are aggregated on skill.ext.reports = [ {reporter_id, reason, note, ts} ].
        """
        try:
            with self.session_scope() as s:
                skill = s.get(DBAgentSkill, skill_id)
                if not skill:
                    return {"success": False, "error": "Skill not found"}
                ext = skill.ext if isinstance(skill.ext, dict) else {}
                reports = ext.get("reports") or []
                if not isinstance(reports, list):
                    reports = []
                reports.append({
                    "reporter_id": reporter_id,
                    "reason": reason,
                    "note": note,
                    "ts": datetime.utcnow().isoformat() + "Z",
                })
                ext["reports"] = reports[-100:]
                skill.ext = ext
                s.flush()
                return {"success": True, "reportCount": len(reports)}
        except SQLAlchemyError as e:
            return {"success": False, "error": str(e)}

    def list_similar_skills(self, skill_id: str, limit: int = 6) -> Dict[str, Any]:
        """Return a list of public skills similar to the given one.

        Similarity heuristic: same category, then overlapping tags, then any public skill.
        Excludes the source skill and the requesting user's own skills.
        """
        try:
            with self.session_scope() as s:
                src = s.get(DBAgentSkill, skill_id)
                if not src:
                    return {"success": False, "data": [], "error": "Skill not found"}
                src_category = (src.tags or [None])[0] if False else None
                # Try by category first
                candidates = s.query(DBAgentSkill).filter(
                    DBAgentSkill.id != skill_id,
                    DBAgentSkill.public == True,
                ).limit(50).all()
                src_tags = set(src.tags or [])
                scored = []
                for c in candidates:
                    score = 0
                    if c.category and src.category and c.category == src.category:
                        score += 5
                    overlap = len(src_tags.intersection(set(c.tags or [])))
                    score += overlap * 2
                    if c.owner == src.owner:
                        score += 1
                    if score > 0:
                        scored.append((score, c))
                scored.sort(key=lambda x: x[0], reverse=True)
                picked = [c.to_dict() for _, c in scored[:limit]]
                if len(picked) < limit:
                    for c in candidates:
                        if c.id == skill_id:
                            continue
                        if any(p["id"] == c.id for p in picked):
                            continue
                        picked.append(c.to_dict())
                        if len(picked) >= limit:
                            break
                return {"success": True, "data": picked, "error": None}
        except SQLAlchemyError as e:
            return {"success": False, "data": [], "error": str(e)}

    def list_skills_by_owner(self, owner: str, exclude_id: str = "",
                             limit: int = 8) -> Dict[str, Any]:
        """Public skills by the same author, optionally excluding one id."""
        try:
            with self.session_scope() as s:
                q = s.query(DBAgentSkill).filter(
                    DBAgentSkill.owner == owner,
                    DBAgentSkill.public == True,
                )
                if exclude_id:
                    q = q.filter(DBAgentSkill.id != exclude_id)
                rows = q.order_by(DBAgentSkill.updated_at.desc()).limit(limit).all()
                return {"success": True, "data": [r.to_dict() for r in rows], "error": None}
        except SQLAlchemyError as e:
            return {"success": False, "data": [], "error": str(e)}

