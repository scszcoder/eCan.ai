"""
Skill history database service.

This module provides database service for skill history operations:
- Save complete skill snapshots on each save
- Query history list (limited to last 100 per skill)
- Get specific history version
- Restore from history
- Cleanup old history records
"""

import json
import uuid
from typing import List, Optional, Dict, Any
from sqlalchemy import and_, desc, asc, func
from sqlalchemy.exc import SQLAlchemyError

from .base_service import BaseService
from ..models.skill_history_model import DBSkillHistory, MAX_HISTORY_PER_SKILL


class DBSkillHistoryService(BaseService):
    """Database service for skill version history operations"""

    def __init__(self, engine=None, session=None):
        super().__init__(engine, session)

    def _get_next_version_number(self, session, skill_id: str) -> int:
        """Get the next version number for a skill"""
        result = session.query(func.max(DBSkillHistory.version_number)).filter(
            DBSkillHistory.skill_id == skill_id
        ).scalar()
        return (result or 0) + 1

    def _cleanup_old_records(self, session, skill_id: str):
        """Remove oldest history records if exceeding MAX_HISTORY_PER_SKILL limit"""
        # Count current records
        count = session.query(func.count(DBSkillHistory.id)).filter(
            DBSkillHistory.skill_id == skill_id
        ).scalar()

        if count >= MAX_HISTORY_PER_SKILL:
            # Calculate how many to delete
            delete_count = count - MAX_HISTORY_PER_SKILL + 1

            # Get IDs of oldest records to delete
            oldest_ids = session.query(DBSkillHistory.id).filter(
                DBSkillHistory.skill_id == skill_id
            ).order_by(DBSkillHistory.created_at.asc()).limit(delete_count).all()

            if oldest_ids:
                ids_to_delete = [r[0] for r in oldest_ids]
                session.query(DBSkillHistory).filter(
                    DBSkillHistory.id.in_(ids_to_delete)
                ).delete(synchronize_session=False)

    def _safe_json_parse(self, val, default=None):
        """Parse a value that might be a JSON string or already a dict/list."""
        if val is None:
            return default
        if isinstance(val, (dict, list)):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return default
        return default

    def save_history(self, skill_id: str, skill_data: Dict[str, Any],
                     save_type: str = 'manual') -> Dict[str, Any]:
        """Save a complete snapshot of skill data as a new history record.

        Args:
            skill_id: The skill ID to save history for
            skill_data: Complete skill data including metadata and diagram
            save_type: Source of save ('manual', 'auto_save', 'restore', 'save_as')

        Returns:
            dict with success status, history record data, and error message
        """
        try:
            with self.session_scope() as session:
                # Get skill metadata from skill_data
                skill_name = skill_data.get('name', '') or skill_data.get('skillName', 'Unknown')
                owner = skill_data.get('owner', '')
                version = skill_data.get('version', '1.0.0')
                version_label = skill_data.get('version_label', '')

                # Ensure config and diagram are dicts (they may be JSON strings from DB)
                config = self._safe_json_parse(skill_data.get('config'), {})
                diagram = self._safe_json_parse(skill_data.get('diagram'), {})

                # Get next version number
                version_number = self._get_next_version_number(session, skill_id)

                # Collect skill files snapshot
                skill_files = self._safe_json_parse(skill_data.get('skill_files'), None)

                # Calculate file size (include skill_files in total size)
                file_size = len(json.dumps(skill_data).encode('utf-8'))
                if skill_files:
                    file_size += len(json.dumps(skill_files).encode('utf-8'))

                # Build change summary (use the already-parsed diagram)
                change_summary = self._generate_change_summary(skill_data, diagram)

                # Create history record
                history_record = DBSkillHistory(
                    id=f"hist_{uuid.uuid4().hex[:16]}",
                    skill_id=skill_id,
                    skill_name=skill_name,
                    owner=owner,
                    version=version,
                    version_number=version_number,
                    description=skill_data.get('description', ''),
                    version_label=version_label,
                    path=skill_data.get('path', ''),
                    source=skill_data.get('source', 'ui'),
                    level=skill_data.get('level', 'entry'),
                    config=config,
                    diagram=diagram,
                    tags=skill_data.get('tags', []),
                    skill_data=skill_data,  # Complete snapshot
                    skill_files=skill_files,  # Full directory snapshot
                    file_size=file_size,
                    change_summary=change_summary,
                    save_type=save_type,
                )

                session.add(history_record)

                # Cleanup old records (keep only last 100)
                self._cleanup_old_records(session, skill_id)

                session.flush()

                return {
                    "success": True,
                    "id": history_record.id,
                    "data": history_record.to_dict(),
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "id": None,
                "data": None,
                "error": str(e)
            }

    def _generate_change_summary(self, skill_data: Dict[str, Any], diagram=None) -> str:
        """Generate a brief summary of changes from skill data"""
        parts = []
        if skill_data.get('name'):
            parts.append(f"Name: {skill_data['name']}")
        if skill_data.get('description'):
            desc_preview = skill_data['description'][:50]
            if len(skill_data['description']) > 50:
                desc_preview += '...'
            parts.append(f"Description: {desc_preview}")

        # Count nodes in diagram (use pre-parsed diagram if available)
        if diagram is None:
            diagram = self._safe_json_parse(skill_data.get('diagram'), {})
        nodes = diagram.get('nodes', []) if isinstance(diagram, dict) else []
        edges = diagram.get('edges', []) if isinstance(diagram, dict) else []
        if nodes:
            parts.append(f"Nodes: {len(nodes)}, Edges: {len(edges)}")

        return ' | '.join(parts) if parts else 'No changes'

    def get_history_list(self, skill_id: str, limit: int = 100,
                         offset: int = 0) -> Dict[str, Any]:
        """Get history list for a skill.

        Args:
            skill_id: The skill ID to get history for
            limit: Maximum number of records to return (default 100)
            offset: Number of records to skip (default 0)

        Returns:
            dict with success status, history list, total count, and error message
        """
        try:
            with self.session_scope() as session:
                # Get total count
                total = session.query(func.count(DBSkillHistory.id)).filter(
                    DBSkillHistory.skill_id == skill_id
                ).scalar()

                # Get paginated records (newest first)
                records = session.query(DBSkillHistory).filter(
                    DBSkillHistory.skill_id == skill_id
                ).order_by(
                    desc(DBSkillHistory.created_at)
                ).offset(offset).limit(limit).all()

                return {
                    "success": True,
                    "data": [r.to_dict() for r in records],
                    "total": total,
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "data": [],
                "total": 0,
                "error": str(e)
            }

    def get_history_by_id(self, history_id: str) -> Dict[str, Any]:
        """Get a specific history record by ID.

        Args:
            history_id: The history record ID

        Returns:
            dict with success status, history data, and error message
        """
        try:
            with self.session_scope() as session:
                record = session.get(DBSkillHistory, history_id)
                if not record:
                    return {
                        "success": False,
                        "data": None,
                        "error": "History record not found"
                    }

                return {
                    "success": True,
                    "data": record.to_dict(),
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    def get_latest_history(self, skill_id: str) -> Dict[str, Any]:
        """Get the most recent history record for a skill.

        Args:
            skill_id: The skill ID

        Returns:
            dict with success status, history data, and error message
        """
        try:
            with self.session_scope() as session:
                record = session.query(DBSkillHistory).filter(
                    DBSkillHistory.skill_id == skill_id
                ).order_by(
                    desc(DBSkillHistory.created_at)
                ).first()

                if not record:
                    return {
                        "success": False,
                        "data": None,
                        "error": "No history found for this skill"
                    }

                return {
                    "success": True,
                    "data": record.to_dict(),
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    def restore_from_history(self, history_id: str) -> Dict[str, Any]:
        """Restore skill data from a history record.

        Args:
            history_id: The history record ID to restore from

        Returns:
            dict with success status, restored skill data, and error message
        """
        try:
            with self.session_scope() as session:
                record = session.get(DBSkillHistory, history_id)
                if not record:
                    return {
                        "success": False,
                        "data": None,
                        "error": "History record not found"
                    }

                # Get the complete skill data from the snapshot
                skill_data = record.skill_data
                if not skill_data:
                    return {
                        "success": False,
                        "data": None,
                        "error": "History record has no skill data"
                    }

                return {
                    "success": True,
                    "data": skill_data,
                    "history_info": {
                        "id": record.id,
                        "version": record.version,
                        "version_number": record.version_number,
                        "created_at": record.created_at,
                        "skill_name": record.skill_name
                    },
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    def delete_history(self, history_id: str) -> Dict[str, Any]:
        """Delete a specific history record.

        Args:
            history_id: The history record ID to delete

        Returns:
            dict with success status and error message
        """
        try:
            with self.session_scope() as session:
                record = session.get(DBSkillHistory, history_id)
                if not record:
                    return {
                        "success": False,
                        "error": "History record not found"
                    }

                session.delete(record)
                return {
                    "success": True,
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "error": str(e)
            }

    def delete_all_history(self, skill_id: str) -> Dict[str, Any]:
        """Delete all history records for a skill.

        Args:
            skill_id: The skill ID

        Returns:
            dict with success status, deleted count, and error message
        """
        try:
            with self.session_scope() as session:
                count = session.query(DBSkillHistory).filter(
                    DBSkillHistory.skill_id == skill_id
                ).delete()
                return {
                    "success": True,
                    "deleted_count": count,
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "deleted_count": 0,
                "error": str(e)
            }

    def get_history_count(self, skill_id: str) -> int:
        """Get the number of history records for a skill.

        Args:
            skill_id: The skill ID

        Returns:
            int: Number of history records
        """
        try:
            with self.session_scope() as session:
                return session.query(func.count(DBSkillHistory.id)).filter(
                    DBSkillHistory.skill_id == skill_id
                ).scalar() or 0
        except SQLAlchemyError:
            return 0

    def compare_versions(self, history_id1: str, history_id2: str) -> Dict[str, Any]:
        """Compare two history versions and return differences.

        Args:
            history_id1: First history record ID
            history_id2: Second history record ID

        Returns:
            dict with success status, comparison data, and error message
        """
        try:
            with self.session_scope() as session:
                record1 = session.get(DBSkillHistory, history_id1)
                record2 = session.get(DBSkillHistory, history_id2)

                if not record1 or not record2:
                    return {
                        "success": False,
                        "data": None,
                        "error": "One or both history records not found"
                    }

                # Extract skill data
                data1 = record1.skill_data or {}
                data2 = record2.skill_data or {}

                # Compute diff
                differences = self._compute_diff(data1, data2)

                return {
                    "success": True,
                    "data": {
                        "version1": {
                            "id": record1.id,
                            "version": record1.version,
                            "version_number": record1.version_number,
                            "created_at": record1.created_at,
                            "skill_name": record1.skill_name
                        },
                        "version2": {
                            "id": record2.id,
                            "version": record2.version,
                            "version_number": record2.version_number,
                            "created_at": record2.created_at,
                            "skill_name": record2.skill_name
                        },
                        "differences": differences
                    },
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    def _compute_diff(self, data1: Dict, data2: Dict) -> Dict[str, Any]:
        """Compute differences between two skill data snapshots"""
        diff = {
            "changed_fields": [],
            "added_fields": [],
            "removed_fields": []
        }

        all_keys = set(data1.keys()) | set(data2.keys())

        for key in all_keys:
            if key not in data1:
                diff["added_fields"].append(key)
            elif key not in data2:
                diff["removed_fields"].append(key)
            elif data1[key] != data2[key]:
                diff["changed_fields"].append({
                    "field": key,
                    "old_value": data1[key],
                    "new_value": data2[key]
                })

        return diff
