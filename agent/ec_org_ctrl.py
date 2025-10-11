"""
EC Organization Controller for eCan.ai

This module provides unified organization management operations,
including initialization, CRUD operations, and agent binding.
"""

import json
import os
from typing import Dict, List, Optional, Any
from utils.logger_helper import logger_helper as logger
from agent.db import DBOrgService, DBAgentService, ECDBMgr

class EC_OrgCtrl:
    """
    EC Organization Controller for handling all organization-related operations
    """
    
    def __init__(self, ec_db_mgr: ECDBMgr = None):
        """
        Initialize organization controller
        
        Args:
            ec_db_mgr (ECDBMgr, optional): Existing database manager instance
        """
        # Use existing database manager if provided, otherwise create new one
        if ec_db_mgr:
            self.ec_db_mgr: ECDBMgr = ec_db_mgr
        else:
            logger.error("[EC_OrgCtrl] No database manager provided")
        
        # Get services from database manager - direct attribute access
        self.org_service: DBOrgService = self.ec_db_mgr.get_org_service()
        self.agent_service: DBAgentService = self.ec_db_mgr.get_agent_service()
    
    
    def get_org_tree(self) -> Dict[str, Any]:
        """
        Get complete org tree structure
        
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
            
            # Get all agents and their organization relationships
            agents_result = self.agent_service.query_agents_with_org()
            agent_org_map = {}  # org_id -> agent count
            
            if agents_result.get("success"):
                agents = agents_result.get("data", [])
                for agent in agents:
                    org_id = agent.get("org_id")
                    if org_id:
                        agent_org_map[org_id] = agent_org_map.get(org_id, 0) + 1
            
            # Calculate total agent count for each organization (including descendants)
            def calculate_agent_count(node):
                # Direct agents in this org
                direct_count = agent_org_map.get(node["id"], 0)
                
                # Agents in child orgs
                child_count = 0
                if "children" in node and node["children"]:
                    for child in node["children"]:
                        child_count += calculate_agent_count(child)
                
                # Total agents (direct + descendants)
                total_count = direct_count + child_count
                node["agent_count"] = total_count
                node["direct_agent_count"] = direct_count
                
                return total_count
            
            # Sort children by sort_order and calculate agent counts
            def sort_children(node):
                if "children" in node:
                    node["children"].sort(key=lambda x: x.get("sort_order", 0))
                    for child in node["children"]:
                        sort_children(child)
            
            for root in tree:
                sort_children(root)
                calculate_agent_count(root)
            
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
    
    def create_org(self, org_data: Dict[str, Any] = None, org_model: 'DBAgentOrg' = None, skip_parent_validation: bool = False) -> Dict[str, Any]:
        """
        Create a new org using model-based approach
        
        Args:
            org_data (dict, optional): Organization data (legacy support)
            org_model (DBAgentOrg, optional): Organization model instance (preferred)
            skip_parent_validation (bool): Skip parent organization validation (for template loading)
            
        Returns:
            dict: Creation result with success status
        """
        try:
            # Import model here to avoid circular imports
            from agent.db.models.org_model import DBAgentOrg
            
            # Handle both legacy dict and new model-based approaches
            if org_model is not None:
                # Use the provided model instance
                logger.info(f"[EC_OrgCtrl] Creating organization from model: {org_model.name}")
                organization = org_model
            elif org_data is not None:
                # Create model from dict data (legacy support)
                logger.info(f"[EC_OrgCtrl] Creating org from data: {org_data.get('name')}")
                organization = self._create_org_model(org_data)
                if organization is None:
                    return {
                        "success": False,
                        "error": "Failed to create organization model from data"
                    }
            else:
                return {
                    "success": False,
                    "error": "Either org_data or org_model must be provided"
                }
            
            # Validate and auto-calculate fields
            validation_result = self._validate_and_prepare_org(organization, skip_parent_validation)
            if not validation_result.get("success"):
                return validation_result
            
            # Create org using service
            result = self.org_service.add_org(organization.to_dict())
            
            if result.get("success"):
                logger.info(f"[EC_OrgCtrl] Organization '{organization.name}' created successfully")
            else:
                logger.error(f"[EC_OrgCtrl] Failed to create organization: {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to create organization: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _create_org_model(self, org_data: Dict[str, Any]) -> Optional['DBAgentOrg']:
        """
        Create org model instance from dictionary data
        
        Args:
            org_data (dict): Org data
            
        Returns:
            DBAgentOrg: Org model instance or None if failed
        """
        try:
            from agent.db.models.org_model import DBAgentOrg
            
            # Create model instance with field validation
            # Generate ID if not provided
            org_id = org_data.get("id")
            if not org_id:
                import uuid
                org_id = f"org_{uuid.uuid4().hex[:12]}"
            
            # Only pass valid fields to DBAgentOrg constructor
            valid_fields = {
                'id': org_id,
                'name': org_data.get("name"),
                'description': org_data.get("description", ""),
                'parent_id': org_data.get("parent_id"),
                'org_type': org_data.get("org_type", "department"),
                'level': org_data.get("level", 0),
                'sort_order': org_data.get("sort_order", 0),
                'status': org_data.get("status", "active"),
                'settings': org_data.get("settings", {})
            }
            
            organization = DBAgentOrg(**valid_fields)
            
            return organization
            
        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to create organization model: {e}")
            return None

    def _validate_and_prepare_org(self, org: 'DBAgentOrg', skip_parent_validation: bool = False) -> Dict[str, Any]:
        """
        Validate and prepare org model before creation
        
        Args:
            org (DBAgentOrg): Org model instance
            skip_parent_validation (bool): Skip parent org validation (for template loading)
            
        Returns:
            dict: Validation result with success status
        """
        try:
            # Validate required fields
            if not org.name:
                return {
                    "success": False,
                    "error": "Org name is required"
                }
            
            if not org.org_type:
                org.org_type = "department"
            
            if not org.status:
                org.status = "active"
            
            # Calculate level and sort_order if parent_id is provided
            if org.parent_id:
                if not skip_parent_validation:
                    parent_result = self.org_service.get_org_by_id(org.parent_id)
                    if parent_result.get("success") and parent_result.get("data"):
                        parent = parent_result["data"]
                        org.level = parent.get("level", 0) + 1
                        
                        # Get siblings to determine sort_order
                        siblings_result = self.org_service.get_orgs_by_parent(org.parent_id)
                        if siblings_result.get("success"):
                            siblings = siblings_result.get("data", [])
                            org.sort_order = len(siblings) + 1
                    else:
                        return {
                            "success": False,
                            "error": f"Parent org not found: {org.parent_id}"
                        }
                # For template loading, use the level and sort_order from template data
            else:
                org.level = 0
                if org.sort_order == 0:
                    org.sort_order = 1
            
            return {
                "success": True,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to validate organization: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    
    def update_org(self, org_id: str, org_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing org
        
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
            
            # If parent_id is being updated, validate it and recompute level/sort_order
            if "parent_id" in org_data:
                new_parent_id = org_data.get("parent_id")
                if new_parent_id:
                    # Prevent cycles: new parent cannot be the org itself or its descendant
                    check_id = new_parent_id
                    max_hops = 1000  # safety guard
                    hops = 0
                    while check_id:
                        if check_id == org_id:
                            return {
                                "success": False,
                                "error": "Invalid move: cannot set an organization as a child of itself or its descendant"
                            }
                        parent_check = self.org_service.get_org_by_id(check_id)
                        if not (parent_check.get("success") and parent_check.get("data")):
                            break
                        check_id = parent_check["data"].get("parent_id")
                        hops += 1
                        if hops > max_hops:
                            break

                    parent_result = self.org_service.get_org_by_id(new_parent_id)
                    if not (parent_result.get("success") and parent_result.get("data")):
                        return {
                            "success": False,
                            "error": f"Parent organization not found: {new_parent_id}"
                        }
                    parent = parent_result["data"]
                    # level = parent.level + 1
                    org_data["level"] = parent.get("level", 0) + 1
                    # sort_order = number of siblings + 1
                    siblings_result = self.org_service.get_orgs_by_parent(new_parent_id)
                    if siblings_result.get("success"):
                        siblings = siblings_result.get("data", [])
                        # If moving within the same parent, exclude itself when counting
                        sibling_count = len([s for s in siblings if s.get("id") != org_id])
                        org_data["sort_order"] = sibling_count + 1
                else:
                    # Moving to root
                    org_data["level"] = 0
                    # Determine sort order among root nodes
                    roots_result = self.org_service.search_organizations(status=None)
                    if roots_result.get("success"):
                        roots = [o for o in roots_result.get("data", []) if not o.get("parent_id") and o.get("id") != org_id]
                        org_data["sort_order"] = len(roots) + 1

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

    def delete_org(self, org_id: str, force: bool = False) -> Dict[str, Any]:
        """
        Delete an org

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

    def get_org_agents(self, org_id: str, include_descendants: bool = False) -> Dict[str, Any]:
        """
        Get all agents in an org

        Args:
            org_id (str): Organization ID
            include_descendants (bool): Whether to include agents from child organizations

        Returns:
            dict: Result with agents data
        """
        try:
            logger.debug(f"[EC_OrgCtrl] Getting agents for organization: {org_id}, include_descendants: {include_descendants}")

            if include_descendants:
                # Get all descendant org IDs
                descendant_org_ids = self._get_descendant_org_ids(org_id)
                descendant_org_ids.append(org_id)  # Include current org
                
                # Get agents from all orgs (current + descendants)
                return self.agent_service.get_agents_by_orgs(descendant_org_ids)
            else:
                # Get agents from single org
                return self.agent_service.get_agents_by_org(org_id)

        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to get organization agents: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    def _get_descendant_org_ids(self, org_id: str) -> List[str]:
        """
        Get all descendant organization IDs recursively

        Args:
            org_id (str): Parent organization ID

        Returns:
            List[str]: List of descendant organization IDs
        """
        try:
            descendant_ids = []

            # Get direct children
            children_result = self.org_service.get_orgs_by_parent(org_id)
            if children_result.get("success"):
                children = children_result.get("data", [])
                for child in children:
                    child_id = child.get("id")
                    if child_id:
                        descendant_ids.append(child_id)
                        # Recursively get descendants of this child
                        descendant_ids.extend(self._get_descendant_org_ids(child_id))

            return descendant_ids

        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to get descendant org IDs: {e}")
            return []

    def bind_agent_to_org(self, agent_id: str, org_id: str) -> Dict[str, Any]:
        """
        Bind an agent to an org using association table

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

            # Verify agent exists
            agent_result = self.agent_service.query_agents(id=agent_id)
            if not agent_result.get("success") or not agent_result.get("data"):
                return {
                    "success": False,
                    "error": f"Agent not found: {agent_id}"
                }

            # Use association table to bind agent to organization
            result = self.agent_service.assign_agent_to_org(agent_id, org_id, role='member')

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

    def unbind_agent_from_org(self, agent_id: str) -> Dict[str, Any]:
        """
        Unbind an agent from its org

        Args:
            agent_id (str): Agent ID

        Returns:
            dict: Unbinding result with success status
        """
        try:
            logger.info(f"[EC_OrgCtrl] Unbinding agent {agent_id} from organization")

            # 1. Update agent to remove organization
            update_data = {"org_id": None}
            result = self.agent_service.update_agent(agent_id, update_data)

            if not result.get("success"):
                logger.error(f"[EC_OrgCtrl] Failed to update agent org_id: {result.get('error')}")
                return result

            # 2. Update agent-org relationship status to inactive
            rel_result = self.agent_service.deactivate_agent_org_relations(agent_id)

            if not rel_result.get("success"):
                logger.error(f"[EC_OrgCtrl] Failed to deactivate agent-org relations: {rel_result.get('error')}")
                return rel_result

            logger.info(f"[EC_OrgCtrl] Agent {agent_id} unbound from organization successfully")
            return {
                "success": True,
                "data": None,
                "error": None
            }

        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to unbind agent from organization: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_available_agents(self, org_id: str = None) -> Dict[str, Any]:
        """
        Get agents available for binding to organizations

        Args:
            org_id (str, optional): Current org ID to exclude its agents

        Returns:
            dict: Result with available agents data
        """
        try:
            # Get all agents
            all_agents_result = self.agent_service.query_agents()
            if not all_agents_result.get("success"):
                return all_agents_result

            all_agents = all_agents_result.get("data", [])

            if org_id:
                # Filter out agents already in this org
                available_agents = [
                    agent for agent in all_agents
                    if agent.get("org_id") != org_id
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

    def search_orgs(self, name: str = None, org_type: str = None,
                           status: str = None) -> Dict[str, Any]:
        """
        Search orgs by criteria

        Args:
            name (str, optional): Org name to search
            org_type (str, optional): Org type filter
            status (str, optional): Status filter

        Returns:
            dict: Search results
        """
        return self.org_service.search_orgs(name, org_type, status)

    def get_org_by_id(self, org_id: str) -> Dict[str, Any]:
        """
        Get org by ID

        Args:
            org_id (str): Org ID

        Returns:
            dict: Org data
        """
        try:
            # Use the service's direct method instead of searching all
            return self.org_service.get_org_by_id(org_id)
            
        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Error getting organization by ID: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    def load_org_template(self, template_file_path: str = None) -> Dict[str, Any]:
        """
        Load default org structure from template file
        
        Args:
            template_file_path (str, optional): Path to template file. If None, uses default path.
            
        Returns:
            dict: Loading result with success status and created organizations count
        """
        try:
            logger.info("[EC_OrgCtrl] Loading organization template...")
            
            # Check if organizations already exist in database (skip if not empty)
            existing_orgs = self.org_service.get_all_orgs()
            if existing_orgs.get("success") and existing_orgs.get("data"):
                logger.info("[EC_OrgCtrl] Organizations already exist in database, skipping template loading")
                return {
                    "success": True,
                    "message": "Organizations already exist, skipped template loading",
                    "created_count": 0
                }
            
            # Determine template file path
            if not template_file_path:
                # Use default template file path
                current_dir = os.path.dirname(os.path.abspath(__file__))
                template_file_path = os.path.join(current_dir, "..", "resource", "data", "organization_template.json")
                template_file_path = os.path.normpath(template_file_path)
            
            # Check if template file exists
            if not os.path.exists(template_file_path):
                logger.warning(f"[EC_OrgCtrl] Organization template file not found: {template_file_path}")
                return {
                    "success": False,
                    "error": f"Template file not found: {template_file_path}",
                    "created_count": 0
                }
            
            # Load template data
            with open(template_file_path, 'r', encoding='utf-8') as f:
                template_data = json.load(f)
            
            organizations = template_data.get("organizations", [])
            logger.info(f"[EC_OrgCtrl] Loading {len(organizations)} organizations from template")
            
            # Create organizations in order (parents first)
            created_count = 0
            failed_count = 0
            
            for org_data in organizations:
                try:
                    # Create org using model-based approach
                    result = self._create_org_from_template(org_data)
                    if result.get("success"):
                        created_count += 1
                        logger.debug(f"[EC_OrgCtrl] Created org: {org_data['name']}")
                    else:
                        failed_count += 1
                        logger.warning(f"[EC_OrgCtrl] Failed to create org '{org_data['name']}': {result.get('error')}")
                        
                except Exception as org_error:
                    failed_count += 1
                    logger.error(f"[EC_OrgCtrl] Error creating org '{org_data.get('name', 'Unknown')}': {org_error}")
            
            # Log summary
            total_orgs = len(organizations)
            if created_count == total_orgs:
                logger.info(f"[EC_OrgCtrl] ✅ Successfully created all {created_count} organizations from template")
                return {
                    "success": True,
                    "message": f"Successfully created all {created_count} organizations",
                    "created_count": created_count,
                    "failed_count": failed_count
                }
            elif created_count > 0:
                logger.warning(f"[EC_OrgCtrl] ⚠️ Partially successful: created {created_count}/{total_orgs} organizations")
                return {
                    "success": True,
                    "message": f"Partially successful: created {created_count}/{total_orgs} organizations",
                    "created_count": created_count,
                    "failed_count": failed_count
                }
            else:
                logger.error(f"[EC_OrgCtrl] ❌ Failed to create any organizations from template")
                return {
                    "success": False,
                    "error": "Failed to create any organizations from template",
                    "created_count": 0,
                    "failed_count": failed_count
                }
                
        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to load organization template: {e}")
            return {
                "success": False,
                "error": str(e),
                "created_count": 0
            }

    def _create_org_from_template(self, template_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create org from template data using model-based approach
        
        Args:
            template_data (dict): Org template data
            
        Returns:
            dict: Creation result with success status
        """
        try:
            from agent.db.models.org_model import DBAgentOrg
            
            # Create organization model instance with proper field mapping
            # Generate ID if not provided
            org_id = template_data.get("id")
            if not org_id:
                import uuid
                org_id = f"org_{uuid.uuid4().hex[:12]}"
            
            # Only pass valid fields to DBAgentOrg constructor
            valid_fields = {
                'id': org_id,
                'name': template_data["name"],
                'description': template_data.get("description", ""),
                'parent_id': template_data.get("parent_id"),
                'org_type': template_data.get("org_type", "department"),
                'level': template_data.get("level", 0),
                'sort_order': template_data.get("sort_order", 0),
                'status': template_data.get("status", "active"),
                'settings': template_data.get("settings", {})
            }
            
            org_model = DBAgentOrg(**valid_fields)
            
            # Use the new model-based create_org method with skip_parent_validation for template loading
            return self.create_org(org_model=org_model, skip_parent_validation=True)
            
        except Exception as e:
            logger.error(f"[EC_OrgCtrl] Failed to create organization from template: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# Global instance for easy access
ec_org_ctrl = None

def get_ec_org_ctrl(ec_db_mgr: ECDBMgr = None) -> EC_OrgCtrl:
    """
    Get global org controller instance

    Args:
        ec_db_mgr (ECDBMgr, optional): Existing database manager instance

    Returns:
        EC_OrgCtrl: Org controller instance
    """
    global ec_org_ctrl
    if ec_org_ctrl is None:
        ec_org_ctrl = EC_OrgCtrl(ec_db_mgr)
    return ec_org_ctrl
