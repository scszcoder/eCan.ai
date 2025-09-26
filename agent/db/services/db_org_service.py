"""
Organization database service.

This module provides database service for organization management operations.
"""

from sqlalchemy.orm import sessionmaker
from ..core import get_engine, get_session_factory, Base
from ..models.org_model import DBAgentOrg
from ..models.agent_model import DBAgent
from .base_service import BaseService

from contextlib import contextmanager
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Dict, Optional, Any
import uuid


class DBOrgService(BaseService):
    """Organization database service class providing all organization-related operations"""

    def __init__(self, engine=None, session=None):
        """
        Initialize organization service

        Args:
            engine: SQLAlchemy engine instance (required)
            session: SQLAlchemy session instance (optional)
        """
        super().__init__(engine, session)

    def _generate_id(self) -> str:
        """Generate a unique ID for organization"""
        return str(uuid.uuid4()).replace('-', '')

    def add_organization(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a new organization
        
        Args:
            data (dict): Organization data
            
        Returns:
            dict: Standard response with success status and data
        """
        try:
            with self.session_scope() as session:
                # Generate ID if not provided
                if 'id' not in data or not data['id']:
                    data['id'] = self._generate_id()
                
                # Validate parent exists if parent_id is provided
                if data.get('parent_id'):
                    parent = session.get(DBAgentOrg, data['parent_id'])
                    if not parent:
                        return {
                            "success": False,
                            "id": None,
                            "data": None,
                            "error": f"Parent organization with id {data['parent_id']} not found"
                        }
                    # Set level based on parent
                    data['level'] = parent.level + 1
                else:
                    data['level'] = 0
                
                organization = DBAgentOrg(**data)
                session.add(organization)
                session.flush()
                
                return {
                    "success": True,
                    "id": organization.id,
                    "data": organization.to_dict(),
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "id": None,
                "data": None,
                "error": str(e)
            }

    def get_organization_tree(self, root_id: str = None) -> Dict[str, Any]:
        """
        Get organization tree structure
        
        Args:
            root_id (str, optional): Root organization ID. If None, gets all root organizations
            
        Returns:
            dict: Standard response with tree data
        """
        try:
            with self.session_scope() as session:
                if root_id:
                    root = session.get(DBAgentOrg, root_id)
                    if not root:
                        return {
                            "success": False,
                            "data": None,
                            "error": f"Organization with id {root_id} not found"
                        }
                    tree = self._build_tree_node(root)
                else:
                    # Get all root organizations (parent_id is None)
                    roots = session.query(DBAgentOrg).filter(DBAgentOrg.parent_id.is_(None)).order_by(DBAgentOrg.sort_order, DBAgentOrg.name).all()
                    tree = [self._build_tree_node(root) for root in roots]
                
                return {
                    "success": True,
                    "data": tree,
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    def delete_organization(self, organization_id: str) -> Dict[str, Any]:
        """
        Delete an organization
        
        Args:
            organization_id (str): Organization ID
            
        Returns:
            dict: Standard response with success status
        """
        try:
            with self.session_scope() as session:
                organization = session.get(DBAgentOrg, organization_id)
                if not organization:
                    return {
                        "success": False,
                        "error": f"Organization with id {organization_id} not found"
                    }
                
                # Check if organization has children
                if organization.children:
                    return {
                        "success": False,
                        "error": "Cannot delete organization with children. Delete children first."
                    }
                
                # Check if organization has agents
                agents = session.query(DBAgent).filter(DBAgent.organization_id == organization_id).all()
                if agents:
                    return {
                        "success": False,
                        "error": f"Cannot delete organization with {len(agents)} agents. Move agents first."
                    }
                
                session.delete(organization)
                return {
                    "success": True,
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "error": str(e)
            }

    def search_organizations(self, name: str = None, organization_type: str = None, status: str = None) -> Dict[str, Any]:
        """
        Search organizations by criteria
        
        Args:
            name (str, optional): Organization name to search
            organization_type (str, optional): Organization type filter
            status (str, optional): Status filter
            
        Returns:
            dict: Standard response with search results
        """
        try:
            with self.session_scope() as session:
                query = session.query(DBAgentOrg)
                
                if name:
                    query = query.filter(DBAgentOrg.name.ilike(f"%{name}%"))
                if organization_type:
                    query = query.filter(DBAgentOrg.org_type == organization_type)
                if status:
                    query = query.filter(DBAgentOrg.status == status)
                
                organizations = query.order_by(DBAgentOrg.level, DBAgentOrg.sort_order, DBAgentOrg.name).all()
                
                return {
                    "success": True,
                    "data": [org.to_dict() for org in organizations],
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }
