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

    def add_org(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a new org
        
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
                
                # Filter out invalid fields that are not part of the model
                valid_fields = {
                    # DBAgentOrg specific fields
                    'id', 'name', 'description', 'parent_id', 'org_type', 
                    'level', 'sort_order', 'status', 'settings',
                    # BaseModel fields
                    'created_at', 'updated_at',
                    # ExtensibleMixin fields
                    'ext'
                }
                filtered_data = {k: v for k, v in data.items() if k in valid_fields}
                organization = DBAgentOrg(**filtered_data)
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

    def get_org_tree(self, root_id: str = None) -> Dict[str, Any]:
        """
        Get org tree structure
        
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

    def delete_org(self, org_id: str) -> Dict[str, Any]:
        """
        Delete an org
        
        Args:
            org_id (str): Org ID
            
        Returns:
            dict: Standard response with success status
        """
        try:
            with self.session_scope() as session:
                org = session.get(DBAgentOrg, org_id)
                if not org:
                    return {
                        "success": False,
                        "error": f"Org with id {org_id} not found"
                    }
                
                # Check if org has children
                if org.children:
                    return {
                        "success": False,
                        "error": "Cannot delete org with children. Delete children first."
                    }
                
                # Check if org has associated agents
                # TODO: Add agent association check when agent model is available
                
                # Delete the org
                session.delete(org)
                return {
                    "success": True,
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "error": str(e)
            }

    def search_orgs(self, name: str = None, org_type: str = None, status: str = None) -> Dict[str, Any]:
        """
        Search orgs by criteria
        
        Args:
            name (str, optional): Org name to search
            org_type (str, optional): Org type filter
            status (str, optional): Status filter
            
        Returns:
            dict: Standard response with search results
        """
        try:
            with self.session_scope() as session:
                query = session.query(DBAgentOrg)
                
                if name:
                    query = query.filter(DBAgentOrg.name.ilike(f"%{name}%"))
                if org_type:
                    query = query.filter(DBAgentOrg.org_type == org_type)
                if status:
                    query = query.filter(DBAgentOrg.status == status)
                
                orgs = query.order_by(DBAgentOrg.level, DBAgentOrg.sort_order, DBAgentOrg.name).all()
                
                return {
                    "success": True,
                    "data": [org.to_dict() for org in orgs],
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    def get_all_orgs(self) -> Dict[str, Any]:
        """
        Get all organizations
        
        Returns:
            dict: Standard response with all organizations data
        """
        try:
            with self.session_scope() as session:
                organizations = session.query(DBAgentOrg).order_by(DBAgentOrg.level, DBAgentOrg.sort_order, DBAgentOrg.name).all()
                
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

    def create_org(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new organization (alias for add_organization)
        
        Args:
            data (dict): Organization data
            
        Returns:
            dict: Standard response with success status and data
        """
        return self.add_organization(data)

    def get_org_by_id(self, org_id: str) -> Dict[str, Any]:
        """
        Get organization by ID
        
        Args:
            org_id (str): Organization ID
            
        Returns:
            dict: Standard response with organization data
        """
        try:
            with self.session_scope() as session:
                organization = session.get(DBAgentOrg, org_id)
                if not organization:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"Organization with id {org_id} not found"
                    }
                
                return {
                    "success": True,
                    "data": organization.to_dict(),
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    def get_orgs_by_parent(self, parent_id: str) -> Dict[str, Any]:
        """
        Get organizations by parent ID
        
        Args:
            parent_id (str): Parent organization ID
            
        Returns:
            dict: Standard response with organizations data
        """
        try:
            with self.session_scope() as session:
                organizations = session.query(DBAgentOrg).filter(
                    DBAgentOrg.parent_id == parent_id
                ).order_by(DBAgentOrg.sort_order, DBAgentOrg.name).all()
                
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

    def update_org(self, org_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an organization
        
        Args:
            org_id (str): Organization ID
            data (dict): Updated organization data
            
        Returns:
            dict: Standard response with success status and data
        """
        try:
            with self.session_scope() as session:
                organization = session.get(DBAgentOrg, org_id)
                if not organization:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"Organization with id {org_id} not found"
                    }
                
                # Convert timestamps in the data before updating
                converted_data = self._convert_timestamps(data)
                
                # Update organization fields
                for key, value in converted_data.items():
                    if hasattr(organization, key):
                        setattr(organization, key, value)
                
                session.flush()
                
                return {
                    "success": True,
                    "data": organization.to_dict(),
                    "error": None
                }
        except SQLAlchemyError as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    def _build_tree_node(self, org: DBAgentOrg) -> Dict[str, Any]:
        """
        Build a tree node from organization model
        
        Args:
            org (DBAgentOrg): Organization model instance
            
        Returns:
            dict: Tree node data
        """
        node = org.to_dict()
        node['children'] = [self._build_tree_node(child) for child in org.children]
        return node
