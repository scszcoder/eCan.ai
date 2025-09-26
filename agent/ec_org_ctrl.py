"""
EC Organization Controller for eCan.ai

This module provides unified organization management operations,
including initialization, CRUD operations, and agent binding.
"""

import json
import os
from typing import Dict, List, Optional, Any
from utils.logger_helper import logger_helper as logger
from agent.db import DBOrgService, DBAgentService, create_db_manager
from utils.path_manager import get_user_data_path


class EC_OrgCtrl:
    """
    EC Organization Controller for handling all organization-related operations
    """
    
    def __init__(self, user: str = None):
        """
        Initialize organization controller
        
        Args:
            user (str, optional): User identifier for database path (optional, uses ECDBMgr)
        """
        # Get database manager instance
        if user:
            user_data_dir = get_user_data_path(user)
            os.makedirs(user_data_dir, exist_ok=True)
            self.db_manager = create_db_manager(user_data_dir, auto_migrate=True)
        else:
            self.db_manager = create_db_manager(auto_migrate=True)
        
        # Get services from database manager - direct attribute access
        self.org_service = self.db_manager.org_service
        self.agent_service = self.db_manager.agent_service
    
    def initialize_default_organizations(self) -> bool:
        """
        Initialize default organization structure
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logger.info("[EC_OrgCtrl] Initializing default organization structure...")
            
            # Check if organizations already exist
            existing_orgs = self.org_service.get_all_orgs()
            if existing_orgs.get("success") and existing_orgs.get("data"):
                logger.info("[EC_OrgCtrl] Organizations already exist, skipping initialization")
                return True
            
            # Create root organization
            root_org_data = {
                "id": "root",
                "name": "eCan.ai",
                "description": "Root organization for eCan.ai system",
                "org_type": "company",
                "parent_id": None,
                "level": 0,
                "sort_order": 0,
                "status": "active",
                "settings": {
                    "is_root": True,
                    "auto_created": True
                }
            }
            
            result = self.org_service.create_org(root_org_data)
            if not result.get("success"):
                logger.error(f"[EC_OrgCtrl] Failed to create root organization: {result.get('error')}")
                return False
            
            logger.info("[EC_OrgCtrl] Root organization created successfully")
            
            # Create default departments
            default_departments = [
                {
                    "id": "tech",
                    "name": "Technology Department",
                    "description": "Technology and development team",
                    "org_type": "department",
                    "parent_id": "root",
                    "level": 1,
                    "sort_order": 1,
                    "status": "active",
                    "settings": {"auto_created": True}
                },
                {
                    "id": "ops",
                    "name": "Operations Department", 
                    "description": "Operations and support team",
                    "org_type": "department",
                    "parent_id": "root",
                    "level": 1,
                    "sort_order": 2,
                    "status": "active",
                    "settings": {"auto_created": True}
                }
            ]
            
            for dept_data in default_departments:
                result = self.org_service.create_org(dept_data)
                if not result.get("success"):
                    logger.warning(f"[EC_OrgCtrl] Failed to create department {dept_data['name']}: {result.get('error')}")
                else:
                    logger.info(f"[EC_OrgCtrl] Department '{dept_data['name']}' created successfully")
            
            logger.info("[EC_OrgCtrl] Default organization structure initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to initialize default organizations: {e}")
            return False
    
    def get_organization_tree(self) -> Dict[str, Any]:
        """
        Get complete organization tree structure
        
        Returns:
            dict: Organization tree with success status and data
        """
        try:
            logger.debug("[EC_OrgCtrl] Getting organization tree...")
            
            # Get all organizations
            result = self.org_service.get_all_orgs()
            if not result.get("success"):
                return result
            
            orgs = result.get("data", [])
            
            # Build tree structure
            org_dict = {org["id"]: org for org in orgs}
            tree = []
            
            # Add children to each organization
            for org in orgs:
                org["children"] = []
            
            # Build parent-child relationships
            for org in orgs:
                if org.get("parent_id") and org["parent_id"] in org_dict:
                    parent = org_dict[org["parent_id"]]
                    parent["children"].append(org)
                else:
                    # Root level organization
                    tree.append(org)
            
            # Sort children by sort_order
            def sort_children(node):
                if "children" in node:
                    node["children"].sort(key=lambda x: x.get("sort_order", 0))
                    for child in node["children"]:
                        sort_children(child)
            
            for root in tree:
                sort_children(root)
            
            return {
                "success": True,
                "data": tree,
                "total": len(orgs),
                "error": None
            }
            
        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to get organization tree: {e}")
            return {
                "success": False,
                "data": [],
                "total": 0,
                "error": str(e)
            }
    
    def create_organization(self, org_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new organization
        
        Args:
            org_data (dict): Organization data
            
        Returns:
            dict: Creation result with success status
        """
        try:
            logger.info(f"[EC_OrgCtrl] Creating organization: {org_data.get('name')}")
            
            # Validate required fields
            required_fields = ["name", "org_type"]
            for field in required_fields:
                if not org_data.get(field):
                    return {
                        "success": False,
                        "error": f"Missing required field: {field}"
                    }
            
            # Set default values
            if not org_data.get("status"):
                org_data["status"] = "active"
            
            # Calculate level and sort_order if parent_id is provided
            if org_data.get("parent_id"):
                parent_result = self.org_service.get_org_by_id(org_data["parent_id"])
                if parent_result.get("success") and parent_result.get("data"):
                    parent = parent_result["data"]
                    org_data["level"] = parent.get("level", 0) + 1
                    
                    # Get siblings to determine sort_order
                    siblings_result = self.org_service.get_orgs_by_parent(org_data["parent_id"])
                    if siblings_result.get("success"):
                        siblings = siblings_result.get("data", [])
                        org_data["sort_order"] = len(siblings) + 1
                else:
                    return {
                        "success": False,
                        "error": f"Parent organization not found: {org_data['parent_id']}"
                    }
            else:
                org_data["level"] = 0
                org_data["sort_order"] = 1
            
            # Create organization
            result = self.org_service.create_org(org_data)
            
            if result.get("success"):
                logger.info(f"[EC_OrgCtrl] Organization '{org_data['name']}' created successfully")
            else:
                logger.error(f"[EC_OrgCtrl] Failed to create organization: {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to create organization: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def update_organization(self, org_id: str, org_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing organization
        
        Args:
            org_id (str): Organization ID
            org_data (dict): Updated organization data
            
        Returns:
            dict: Update result with success status
        """
        try:
            logger.info(f"[EC_OrgCtrl] Updating organization: {org_id}")
            
            # Get existing organization
            existing_result = self.org_service.get_org_by_id(org_id)
            if not existing_result.get("success"):
                return {
                    "success": False,
                    "error": f"Organization not found: {org_id}"
                }
            
            existing_org = existing_result["data"]
            
            # Merge with existing data
            updated_data = existing_org.copy()
            updated_data.update(org_data)
            
            # Update organization
            result = self.org_service.update_org(org_id, updated_data)
            
            if result.get("success"):
                logger.info(f"[EC_OrgCtrl] Organization '{org_id}' updated successfully")
            else:
                logger.error(f"[EC_OrgCtrl] Failed to update organization: {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to update organization: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def delete_organization(self, org_id: str, force: bool = False) -> Dict[str, Any]:
        """
        Delete an organization

        Args:
            org_id (str): Organization ID
            force (bool): Force delete even if has children or agents

        Returns:
            dict: Deletion result with success status
        """
        try:
            logger.info(f"[EC_OrgCtrl] Deleting organization: {org_id}")

            # Check if organization exists
            existing_result = self.org_service.get_org_by_id(org_id)
            if not existing_result.get("success"):
                return {
                    "success": False,
                    "error": f"Organization not found: {org_id}"
                }

            # Check for children if not force delete
            if not force:
                children_result = self.org_service.get_orgs_by_parent(org_id)
                if children_result.get("success") and children_result.get("data"):
                    return {
                        "success": False,
                        "error": "Cannot delete organization with children. Use force=True to override."
                    }

                # Check for agents in this organization
                agents_result = self.agent_service.get_agents_by_org(org_id)
                if agents_result.get("success") and agents_result.get("data"):
                    return {
                        "success": False,
                        "error": "Cannot delete organization with agents. Move agents first or use force=True."
                    }

            # Delete organization
            result = self.org_service.delete_org(org_id)

            if result.get("success"):
                logger.info(f"[EC_OrgCtrl] Organization '{org_id}' deleted successfully")
            else:
                logger.error(f"[EC_OrgCtrl] Failed to delete organization: {result.get('error')}")

            return result

        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to delete organization: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_organization_agents(self, org_id: str) -> Dict[str, Any]:
        """
        Get all agents in an organization

        Args:
            org_id (str): Organization ID

        Returns:
            dict: Result with agents data
        """
        try:
            logger.debug(f"[EC_OrgCtrl] Getting agents for organization: {org_id}")
            return self.agent_service.get_agents_by_org(org_id)

        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to get organization agents: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    def bind_agent_to_organization(self, agent_id: str, org_id: str) -> Dict[str, Any]:
        """
        Bind an agent to an organization

        Args:
            agent_id (str): Agent ID
            org_id (str): Organization ID

        Returns:
            dict: Binding result with success status
        """
        try:
            logger.info(f"[EC_OrgCtrl] Binding agent {agent_id} to organization {org_id}")

            # Verify organization exists
            org_result = self.org_service.get_org_by_id(org_id)
            if not org_result.get("success"):
                return {
                    "success": False,
                    "error": f"Organization not found: {org_id}"
                }

            # Update agent's organization
            update_data = {"org_id": org_id}
            result = self.agent_service.update_agent(agent_id, update_data)

            if result.get("success"):
                logger.info(f"[EC_OrgCtrl] Agent {agent_id} bound to organization {org_id} successfully")
            else:
                logger.error(f"[EC_OrgCtrl] Failed to bind agent to organization: {result.get('error')}")

            return result

        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to bind agent to organization: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def unbind_agent_from_organization(self, agent_id: str) -> Dict[str, Any]:
        """
        Unbind an agent from its organization

        Args:
            agent_id (str): Agent ID

        Returns:
            dict: Unbinding result with success status
        """
        try:
            logger.info(f"[EC_OrgCtrl] Unbinding agent {agent_id} from organization")

            # Update agent to remove organization
            update_data = {"org_id": None}
            result = self.agent_service.update_agent(agent_id, update_data)

            if result.get("success"):
                logger.info(f"[EC_OrgCtrl] Agent {agent_id} unbound from organization successfully")
            else:
                logger.error(f"[EC_OrgCtrl] Failed to unbind agent from organization: {result.get('error')}")

            return result

        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to unbind agent from organization: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_available_agents(self, organization_id: str = None) -> Dict[str, Any]:
        """
        Get agents available for binding to organizations

        Args:
            organization_id (str, optional): Current organization ID to exclude its agents

        Returns:
            dict: Result with available agents data
        """
        try:
            # Get all agents
            all_agents_result = self.agent_service.query_agents()
            if not all_agents_result.get("success"):
                return all_agents_result

            all_agents = all_agents_result.get("data", [])

            if organization_id:
                # Filter out agents already in this organization
                available_agents = [
                    agent for agent in all_agents
                    if agent.get("org_id") != organization_id
                ]
            else:
                # Return agents not bound to any organization
                available_agents = [
                    agent for agent in all_agents
                    if not agent.get("org_id")
                ]

            return {
                "success": True,
                "data": available_agents,
                "error": None
            }

        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to get available agents: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    def search_organizations(self, name: str = None, organization_type: str = None,
                           status: str = None) -> Dict[str, Any]:
        """
        Search organizations by criteria

        Args:
            name (str, optional): Organization name to search
            organization_type (str, optional): Organization type filter
            status (str, optional): Status filter

        Returns:
            dict: Search results
        """
        return self.org_service.search_organizations(name, organization_type, status)

    def get_organization_by_id(self, organization_id: str) -> Dict[str, Any]:
        """
        Get organization by ID

        Args:
            organization_id (str): Organization ID

        Returns:
            dict: Organization data
        """
        try:
            result = self.org_service.search_organizations()
            if not result.get("success"):
                return result

            organizations = result.get("data", [])
            organization = next((org for org in organizations if org.get("id") == organization_id), None)

            if organization:
                return {
                    "success": True,
                    "data": organization,
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "data": None,
                    "error": f"Organization with id {organization_id} not found"
                }

        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Error getting organization by ID: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }


# Global instance for easy access
ec_org_ctrl = None

def get_organization_manager(user: str = None) -> EC_OrgCtrl:
    """
    Get global organization controller instance

    Args:
        user (str, optional): User identifier for database path (for backward compatibility)

    Returns:
        EC_OrgCtrl: Organization controller instance
    """
    global ec_org_ctrl
    if ec_org_ctrl is None:
        ec_org_ctrl = EC_OrgCtrl(user)
    return ec_org_ctrl
