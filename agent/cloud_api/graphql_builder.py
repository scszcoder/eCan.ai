"""
GraphQL Builder - Generic GraphQL mutation string builder based on Schema

Core Ideas:
1. No hardcoded fields - all fields come from data
2. Schema-driven transformation - use SchemaRegistry for field mapping
3. Generic builder - one function handles all data types (Agent/Skill/Task/Tool)
4. Flexible and maintainable - adding/removing fields only requires updating Schema mapping

Usage:
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import DataType, Operation
    
    # Add agents
    mutation_str = build_mutation(
        data_type=DataType.AGENT,
        operation=Operation.ADD,
        items=agents_list
    )
    
    # Update skills
    mutation_str = build_mutation(
        data_type=DataType.SKILL,
        operation=Operation.UPDATE,
        items=skills_list
    )
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from agent.cloud_api.constants import DataType, Operation
from agent.cloud_api.schema_registry import get_schema_registry
from utils.logger_helper import logger_helper as logger


class GraphQLBuilder:
    """Generic GraphQL mutation builder"""
    
    # GraphQL mutation name mapping
    # Standard naming convention:
    # - Entity operations: addAgents, addAgentSkills, addAgentTasks, addAgentTools
    # - Relationship operations: addAgentSkillRelations, addAgentTaskRelations, etc.
    MUTATION_NAMES = {
        # ============================================================================
        # Entity Operations
        # ============================================================================
        (DataType.AGENT, Operation.ADD): "addAgents",
        (DataType.AGENT, Operation.UPDATE): "updateAgents",
        (DataType.AGENT, Operation.DELETE): "removeAgents",
        
        (DataType.SKILL, Operation.ADD): "addAgentSkills",
        (DataType.SKILL, Operation.UPDATE): "updateAgentSkills",
        (DataType.SKILL, Operation.DELETE): "removeAgentSkills",
        
        (DataType.TASK, Operation.ADD): "addAgentTasks",
        (DataType.TASK, Operation.UPDATE): "updateAgentTasks",
        (DataType.TASK, Operation.DELETE): "removeAgentTasks",
        
        (DataType.TOOL, Operation.ADD): "addAgentTools",
        (DataType.TOOL, Operation.UPDATE): "updateAgentTools",
        (DataType.TOOL, Operation.DELETE): "removeAgentTools",
        
        (DataType.KNOWLEDGE, Operation.ADD): "addKnowledges",
        (DataType.KNOWLEDGE, Operation.UPDATE): "updateKnowledges",
        (DataType.KNOWLEDGE, Operation.DELETE): "removeKnowledges",
        
        (DataType.AVATAR_RESOURCE, Operation.ADD): "addAvatarResources",
        (DataType.AVATAR_RESOURCE, Operation.UPDATE): "updateAvatarResources",
        (DataType.AVATAR_RESOURCE, Operation.DELETE): "removeAvatarResources",
        
        (DataType.VEHICLE, Operation.ADD): "reportVehicles",
        (DataType.VEHICLE, Operation.UPDATE): "updateVehicles",
        
        # ============================================================================
        # First-Level Relationship Operations
        # ============================================================================
        (DataType.AGENT_SKILL, Operation.ADD): "addAgentSkillRelations",
        (DataType.AGENT_SKILL, Operation.UPDATE): "updateAgentSkillRelations",
        (DataType.AGENT_SKILL, Operation.DELETE): "removeAgentSkillRelations",
        
        (DataType.AGENT_TASK, Operation.ADD): "addAgentTaskRelations",
        (DataType.AGENT_TASK, Operation.UPDATE): "updateAgentTaskRelations",
        (DataType.AGENT_TASK, Operation.DELETE): "removeAgentTaskRelations",
        
        (DataType.AGENT_TOOL, Operation.ADD): "addAgentToolRelations",
        (DataType.AGENT_TOOL, Operation.UPDATE): "updateAgentToolRelations",
        (DataType.AGENT_TOOL, Operation.DELETE): "removeAgentToolRelations",
        
        # ============================================================================
        # Second-Level Relationship Operations
        # ============================================================================
        (DataType.SKILL_TOOL, Operation.ADD): "addSkillToolRelations",
        (DataType.SKILL_TOOL, Operation.UPDATE): "updateSkillToolRelations",
        (DataType.SKILL_TOOL, Operation.DELETE): "removeSkillToolRelations",
        
        (DataType.SKILL_KNOWLEDGE, Operation.ADD): "addSkillKnowledgeRelations",
        (DataType.SKILL_KNOWLEDGE, Operation.UPDATE): "updateSkillKnowledgeRelations",
        (DataType.SKILL_KNOWLEDGE, Operation.DELETE): "removeSkillKnowledgeRelations",
        
        (DataType.TASK_SKILL, Operation.ADD): "addTaskSkillRelations",
        (DataType.TASK_SKILL, Operation.UPDATE): "updateTaskSkillRelations",
        (DataType.TASK_SKILL, Operation.DELETE): "removeTaskSkillRelations",
    }
    
    # Return field selection for mutations that return result types
    # Format: mutation_name -> "{ field1 field2 ... }"
    MUTATION_RETURN_FIELDS = {
        # Agent mutations -> AgentMutationResult
        "addAgents": "{ id success error }",
        "updateAgents": "{ id success error }",
        "removeAgents": "{ id success error }",
        # Skill mutations -> SkillMutationResult
        "addAgentSkills": "{ id success error }",
        "updateAgentSkills": "{ id success error }",
        "removeAgentSkills": "{ id success error }",
        # Task mutations -> TaskMutationResult
        "addAgentTasks": "{ id success error }",
        "updateAgentTasks": "{ id success error }",
        "removeAgentTasks": "{ id success error }",
        # Tool mutations -> ToolMutationResult
        "addAgentTools": "{ id success error }",
        "updateAgentTools": "{ id success error }",
        "removeAgentTools": "{ id success error }",
        # Knowledge mutations -> KnowledgeMutationResult
        "addAgentKnowledges": "{ id success error }",
        "updateAgentKnowledges": "{ id success error }",
        "removeAgentKnowledges": "{ id success error }",
        # Avatar mutations -> AvatarMutationResult
        "addAvatars": "{ id success error }",
        "updateAvatars": "{ id success error }",
        "removeAvatars": "{ id success error }",
        # Vehicle mutations -> VehicleMutationResult
        "addVehicles": "{ id success error }",
        "updateVehicles": "{ id success error }",
        "removeVehicles": "{ id success error }",
        # Org mutations -> OrgMutationResult
        "addOrgs": "{ id success error }",
        "updateOrgs": "{ id success error }",
        "removeOrgs": "{ id success error }",
        # Prompt mutations -> PromptMutationResult
        "addPrompts": "{ id success error }",
        "updatePrompts": "{ id success error }",
        "removePrompts": "{ id success error }",
    }
    
    def __init__(self):
        self.schema_registry = get_schema_registry()
    
    def build_mutation(
        self,
        data_type: DataType,
        operation: Operation,
        items: List[Dict[str, Any]],
        settings: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build GraphQL mutation string
        
        Args:
            data_type: Data type (AGENT/SKILL/TASK/TOOL)
            operation: Operation type (ADD/UPDATE/REMOVE)
            items: Data items list (list of dicts)
            settings: Optional settings (e.g., test_settings)
            
        Returns:
            GraphQL mutation string
            
        Example:
            builder = GraphQLBuilder()
            mutation = builder.build_mutation(
                DataType.AGENT,
                Operation.ADD,
                [{'id': '1', 'name': 'Agent1', ...}]
            )
        """
        # Get mutation name
        mutation_name = self.MUTATION_NAMES.get((data_type, operation))
        if not mutation_name:
            raise ValueError(f"Unsupported operation: {data_type.value} {operation.value}")
        
        # Get schema
        schema = self.schema_registry.get_schema(data_type)
        if not schema:
            raise ValueError(f"Schema not found for {data_type.value}")
        
        # Build mutation
        if operation == Operation.DELETE:
            return self._build_remove_mutation(mutation_name, items)
        else:
            return self._build_add_update_mutation(
                mutation_name, items, schema, settings
            )
    
    def _build_add_update_mutation(
        self,
        mutation_name: str,
        items: List[Dict[str, Any]],
        schema,
        settings: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build ADD/UPDATE mutation"""
        # Start mutation
        mutation_str = f"mutation MyMutation {{ {mutation_name}(input: ["
        
        # Build each item
        item_strings = []
        for item in items:
            # Transform to cloud format using schema
            cloud_item = schema.to_cloud(item)
            
            # Build GraphQL object string
            item_str = self._build_graphql_object(cloud_item)
            item_strings.append(item_str)
        
        # Join items
        mutation_str += ", ".join(item_strings)
        mutation_str += "]"
        
        # Add settings if provided
        if settings:
            settings_str = json.dumps(settings).replace('"', '\\"')
            mutation_str += f', settings: "{settings_str}"'
        
        # Close mutation with return field selection if needed
        return_fields = self.MUTATION_RETURN_FIELDS.get(mutation_name, "")
        mutation_str += f") {return_fields} }}"
        
        logger.debug(f"[GraphQLBuilder] Built mutation: {mutation_str[:200]}...")
        return mutation_str
    
    def _build_remove_mutation(
        self,
        mutation_name: str,
        items: List[Dict[str, Any]]
    ) -> str:
        """Build REMOVE mutation
        
        New schema: remove mutations take [ID!]! - just an array of ID strings
        """
        mutation_str = f"mutation MyMutation {{ {mutation_name}(input: ["
        
        # Build array of IDs
        id_strings = []
        for item in items:
            # Get ID from various possible field names
            oid = (item.get("id") or  # Generic ID
                   item.get("oid") or  # Order ID
                   item.get("agid") or  # Agent ID (legacy)
                   item.get("skid") or  # Skill ID (legacy)
                   item.get("task_id") or  # Task ID (legacy)
                   item.get("tool_id"))  # Tool ID (legacy)
            
            if not oid:
                logger.warning(f"[GraphQLBuilder] Remove item missing ID: {item}")
                continue
            
            id_strings.append(f'"{oid}"')
        
        mutation_str += ", ".join(id_strings)
        mutation_str += "]"
        
        # Close mutation with return field selection if needed
        return_fields = self.MUTATION_RETURN_FIELDS.get(mutation_name, "")
        mutation_str += f") {return_fields} }}"
        
        logger.debug(f"[GraphQLBuilder] Built remove mutation: {mutation_str[:200]}...")
        return mutation_str
    
    def _build_graphql_object(self, data: Dict[str, Any]) -> str:
        """
        Build GraphQL object string from dict
        
        Automatically handles:
        - String escaping
        - Boolean values
        - Number values
        - Null values
        - Nested JSON (already serialized by schema)
        """
        fields = []
        
        for key, value in data.items():
            # Skip None values
            if value is None:
                continue
            
            # Format value based on type
            formatted_value = self._format_graphql_value(value)
            fields.append(f"{key}: {formatted_value}")
        
        return "{ " + ", ".join(fields) + " }"
    
    def _format_graphql_value(self, value: Any) -> str:
        """
        Format value for GraphQL with AWS type support
        
        Handles:
        - AWSDate: YYYY-MM-DD format
        - AWSDateTime: ISO 8601 format
        - AWSJSON: Already serialized by Schema
        - Boolean: true/false (lowercase)
        - Number: as-is
        - String: escaped
        """
        if value is None:
            return '""'  # Empty string for null
        elif isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, (datetime, date)):
            # AWSDate/AWSDateTime: format as ISO string
            return f'"{self._format_aws_datetime(value)}"'
        elif isinstance(value, str):
            # Escape quotes and backslashes
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            return f'"{escaped}"'
        else:
            # For other types, convert to string
            return f'"{str(value)}"'
    
    def _format_aws_datetime(self, dt_value: Any) -> str:
        """
        Format datetime/date to AWS format
        
        - AWSDate: YYYY-MM-DD
        - AWSDateTime: ISO 8601 (YYYY-MM-DDTHH:MM:SS.sssZ)
        """
        if isinstance(dt_value, str):
            # Already a string, check format
            if 'T' in dt_value:
                # ISO 8601 format, extract date if needed
                return dt_value.split('T')[0] if len(dt_value.split('T')[0]) == 10 else dt_value
            return dt_value
        elif isinstance(dt_value, datetime):
            # AWSDateTime: ISO 8601 format
            return dt_value.isoformat() + 'Z' if dt_value.tzinfo is None else dt_value.isoformat()
        elif isinstance(dt_value, date):
            # AWSDate: YYYY-MM-DD
            return dt_value.strftime('%Y-%m-%d')
        else:
            return str(dt_value)


# Global builder instance
_graphql_builder = GraphQLBuilder()


def build_mutation(
    data_type: DataType,
    operation: Operation,
    items: List[Dict[str, Any]],
    settings: Optional[Dict[str, Any]] = None
) -> str:
    """
    Convenience function: Build GraphQL mutation
    
    Args:
        data_type: Data type (AGENT/SKILL/TASK/TOOL)
        operation: Operation type (ADD/UPDATE/REMOVE)
        items: Data items list
        settings: Optional settings
        
    Returns:
        GraphQL mutation string
        
    Example:
        # Add agents
        mutation = build_mutation(
            DataType.AGENT,
            Operation.ADD,
            [{'id': '1', 'name': 'Agent1', 'org_id': '100'}]
        )
        
        # Update skills
        mutation = build_mutation(
            DataType.SKILL,
            Operation.UPDATE,
            [{'id': '1', 'name': 'Updated Skill'}]
        )
        
        # Remove tasks
        mutation = build_mutation(
            DataType.TASK,
            Operation.DELETE,
            [{'id': '1', 'owner': 'user@example.com', 'reason': 'Completed'}]
        )
    """
    return _graphql_builder.build_mutation(data_type, operation, items, settings)


# ============================================================================
# Legacy Helper Functions (Backward Compatibility)
# ============================================================================
# These functions are kept for backward compatibility with existing code.
# New code should use build_mutation() directly.

def gen_add_agents_string(agents: List[Dict[str, Any]]) -> str:
    """Add agents - Legacy wrapper for build_mutation"""
    return build_mutation(DataType.AGENT, Operation.ADD, agents)


def gen_update_agents_string(agents: List[Dict[str, Any]]) -> str:
    """Update agents - Legacy wrapper for build_mutation"""
    return build_mutation(DataType.AGENT, Operation.UPDATE, agents)


def gen_remove_agents_string(remove_orders: List[Dict[str, Any]]) -> str:
    """Remove agents - Legacy wrapper for build_mutation"""
    return build_mutation(DataType.AGENT, Operation.DELETE, remove_orders)


def gen_add_agent_skills_string(skills: List[Dict[str, Any]]) -> str:
    """Add skills (entities) - Legacy wrapper for build_mutation"""
    return build_mutation(DataType.SKILL, Operation.ADD, skills)


def gen_update_agent_skills_string(skills: List[Dict[str, Any]]) -> str:
    """Update skills (entities) - Legacy wrapper for build_mutation"""
    return build_mutation(DataType.SKILL, Operation.UPDATE, skills)


def gen_remove_agent_skills_string(remove_orders: List[Dict[str, Any]]) -> str:
    """Remove skills (entities) - Legacy wrapper for build_mutation"""
    return build_mutation(DataType.SKILL, Operation.DELETE, remove_orders)


def gen_add_agent_tasks_string(tasks: List[Dict[str, Any]], test_settings: Dict[str, Any] = None) -> str:
    """Add tasks (entities) - Legacy wrapper for build_mutation"""
    settings = test_settings if test_settings else {"testmode": False}
    return build_mutation(DataType.TASK, Operation.ADD, tasks, settings)


def gen_update_agent_tasks_string(tasks: List[Dict[str, Any]]) -> str:
    """Update tasks (entities) - Legacy wrapper for build_mutation"""
    return build_mutation(DataType.TASK, Operation.UPDATE, tasks)


def gen_remove_agent_tasks_string(remove_orders: List[Dict[str, Any]]) -> str:
    """Remove tasks (entities) - Legacy wrapper for build_mutation"""
    return build_mutation(DataType.TASK, Operation.DELETE, remove_orders)


def gen_add_agent_tools_string(tools: List[Dict[str, Any]], test_settings: Dict[str, Any] = None) -> str:
    """Add tools (entities) - Legacy wrapper for build_mutation"""
    settings = test_settings if test_settings else {"testmode": False}
    return build_mutation(DataType.TOOL, Operation.ADD, tools, settings)


def gen_update_agent_tools_string(tools: List[Dict[str, Any]]) -> str:
    """Update tools (entities) - Legacy wrapper for build_mutation"""
    return build_mutation(DataType.TOOL, Operation.UPDATE, tools)


def gen_remove_agent_tools_string(remove_orders: List[Dict[str, Any]]) -> str:
    """Remove tools (entities) - Legacy wrapper for build_mutation"""
    return build_mutation(DataType.TOOL, Operation.DELETE, remove_orders)
