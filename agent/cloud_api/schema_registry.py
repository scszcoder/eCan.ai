"""
Schema Registry - Data Schema Registration and Version Management

Solves field addition/deletion/modification issues:
1. Versioned Schema definitions
2. Field Transformers
3. Backward compatibility handling
4. Default values and validation
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from agent.cloud_api.constants import DataType
from utils.logger_helper import logger_helper as logger


class FieldAction(str, Enum):
    """Field operation types"""
    RENAME = 'rename'           # Rename field
    ADD = 'add'                 # Add field
    REMOVE = 'remove'           # Remove field
    TRANSFORM = 'transform'     # Transform field value
    MERGE = 'merge'             # Merge multiple fields
    SPLIT = 'split'             # Split field


@dataclass
class FieldTransformer:
    """Field transformer"""
    action: FieldAction
    source_field: Optional[str] = None      # Source field name
    target_field: Optional[str] = None      # Target field name
    default_value: Any = None               # Default value
    transform_func: Optional[Callable] = None  # Transform function (to_cloud)
    reverse_transform_func: Optional[Callable] = None  # Reverse transform function (from_cloud)
    source_fields: List[str] = field(default_factory=list)  # Multiple source fields (for merge)
    
    def apply(self, data: Dict[str, Any], direction: str = 'to_cloud') -> Dict[str, Any]:
        """
        Apply transformation
        
        Args:
            data: Data dictionary
            direction: Transformation direction ('to_cloud' or 'from_cloud')
        """
        result = data.copy()
        
        if self.action == FieldAction.RENAME:
            # Rename field
            if direction == 'to_cloud':
                if self.source_field in result:
                    result[self.target_field] = result.pop(self.source_field)
            else:  # from_cloud
                if self.target_field in result:
                    result[self.source_field] = result.pop(self.target_field)
        
        elif self.action == FieldAction.ADD:
            # Add field (with default value)
            if direction == 'to_cloud':
                if self.target_field not in result:
                    if self.transform_func:
                        result[self.target_field] = self.transform_func(result)
                    else:
                        result[self.target_field] = self.default_value
        
        elif self.action == FieldAction.REMOVE:
            # Remove field
            if direction == 'to_cloud':
                result.pop(self.source_field, None)
        
        elif self.action == FieldAction.TRANSFORM:
            # Transform field value
            if direction == 'to_cloud':
                if self.source_field in result and self.transform_func:
                    result[self.source_field] = self.transform_func(result[self.source_field])
            else:  # from_cloud
                if self.source_field in result:
                    if self.reverse_transform_func:
                        result[self.source_field] = self.reverse_transform_func(result[self.source_field])
                    # If no reverse transform function, keep original value
        
        elif self.action == FieldAction.MERGE:
            # Merge multiple fields
            if direction == 'to_cloud' and self.transform_func:
                values = {f: result.get(f) for f in self.source_fields}
                result[self.target_field] = self.transform_func(values)
                # Optional: delete source fields
                for f in self.source_fields:
                    result.pop(f, None)
        
        elif self.action == FieldAction.SPLIT:
            # Split field
            if direction == 'from_cloud' and self.transform_func:
                if self.source_field in result:
                    split_values = self.transform_func(result[self.source_field])
                    result.update(split_values)
                    result.pop(self.source_field, None)
        
        return result


@dataclass
class SchemaVersion:
    """Schema version definition"""
    version: str                                    # Version number (e.g., "1.0", "2.0")
    fields: Dict[str, str]                         # Field mapping {local: cloud}
    required_fields: Dict[str, Any]                # Required cloud fields and default values
    transformers: List[FieldTransformer] = field(default_factory=list)  # Field transformers
    deprecated_fields: List[str] = field(default_factory=list)  # Deprecated fields
    
    def to_cloud(self, local_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert local data to cloud format"""
        from utils.logger_helper import logger_helper as logger
        
        cloud_data = {}
        
        # 1. Auto-mapping: directly copy fields with same name
        for local_field, value in local_data.items():
            if local_field not in self.fields:
                # Same field name, direct mapping
                cloud_data[local_field] = value
        
        # 2. Explicit mapping: map fields with different names according to config
        for local_field, cloud_field in self.fields.items():
            if cloud_field and local_field in local_data:
                cloud_data[cloud_field] = local_data[local_field]
        
        # 3. Add required fields
        for field_name, default_value in self.required_fields.items():
            if field_name not in cloud_data:
                cloud_data[field_name] = default_value
        
        # Extract ID for logging (try different ID fields)
        record_id = cloud_data.get('agid') or cloud_data.get('askid') or cloud_data.get('ataskid') or cloud_data.get('toolid') or cloud_data.get('id', 'UNKNOWN')
        logger.debug(f"[Schema] Before transformers (ID: {record_id}): {list(cloud_data.keys())}")

        # 4. Apply transformers
        for transformer in self.transformers:
            cloud_data = transformer.apply(cloud_data, direction='to_cloud')

        logger.debug(f"[Schema] After transformers (ID: {record_id}): {list(cloud_data.keys())}")
        
        return cloud_data
    
    def from_cloud(self, cloud_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert cloud data to local format"""
        # 1. Apply transformers first (on cloud field names)
        transformed_cloud_data = cloud_data.copy()
        for transformer in reversed(self.transformers):
            transformed_cloud_data = transformer.apply(transformed_cloud_data, direction='from_cloud')
        
        # 2. Build reverse mapping (cloud → local)
        local_data = {}
        reverse_mapping = {v: k for k, v in self.fields.items() if v}
        
        # 3. Explicit mapping: map fields with different names according to config
        for cloud_field, local_field in reverse_mapping.items():
            if cloud_field in transformed_cloud_data:
                local_data[local_field] = transformed_cloud_data[cloud_field]
        
        # 4. Auto-mapping: directly copy fields with same name
        mapped_cloud_fields = set(reverse_mapping.keys())
        for cloud_field, value in transformed_cloud_data.items():
            if cloud_field not in mapped_cloud_fields and cloud_field not in self.required_fields:
                # Same field name, direct mapping
                local_data[cloud_field] = value
        
        return local_data


class SchemaRegistry:
    """Schema registry"""
    
    def __init__(self):
        self._schemas: Dict[DataType, Dict[str, SchemaVersion]] = {}
        self._current_versions: Dict[DataType, str] = {}
        self._default_schemas_registered = False
    
    def register_schema(self, data_type: DataType, version: str, schema: SchemaVersion):
        """Register Schema version"""
        if data_type not in self._schemas:
            self._schemas[data_type] = {}
        
        self._schemas[data_type][version] = schema
        
        # Set as current version
        if data_type not in self._current_versions:
            self._current_versions[data_type] = version
    
    def get_schema(self, data_type: DataType, version: Optional[str] = None) -> Optional[SchemaVersion]:
        """Get Schema"""
        # Lazy register default Schemas
        if not self._default_schemas_registered:
            self._register_default_schemas()
            self._default_schemas_registered = True
        
        if data_type not in self._schemas:
            return None
        
        # Use specified version or current version
        version = version or self._current_versions.get(data_type)
        return self._schemas[data_type].get(version)
    
    def set_current_version(self, data_type: DataType, version: str):
        """Set current version"""
        if data_type in self._schemas and version in self._schemas[data_type]:
            self._current_versions[data_type] = version
    
    def _register_default_schemas(self):
        """Register default Schemas (auto-build using SchemaBuilder)"""
        try:
            # Lazy import to avoid circular dependency
            import agent.cloud_api.schema_builder as builder
            
            logger.info("[SchemaRegistry] 🔧 Building schemas from mapping files...")
            
            # Agent Schema v1.0 - Auto-build from mapping file
            agent_schema_v1 = builder.build_schema(DataType.AGENT, version="1.0")
            self.register_schema(DataType.AGENT, "1.0", agent_schema_v1)
            logger.info(f"[SchemaRegistry] ✅ Registered Agent schema with {len(agent_schema_v1.transformers)} transformers")
            
            # Skill Entity Schema v1.0 - Skill entity
            skill_schema_v1 = builder.build_schema(DataType.SKILL, version="1.0")
            self.register_schema(DataType.SKILL, "1.0", skill_schema_v1)
            logger.info(f"[SchemaRegistry] ✅ Registered Skill entity schema with {len(skill_schema_v1.transformers)} transformers")
            
            # Agent-Skill Relationship Schema v1.0
            agent_skill_schema_v1 = builder.build_schema(DataType.AGENT_SKILL, version="1.0")
            self.register_schema(DataType.AGENT_SKILL, "1.0", agent_skill_schema_v1)
            logger.info(f"[SchemaRegistry] ✅ Registered Agent-Skill relationship schema with {len(agent_skill_schema_v1.transformers)} transformers")
            
            # Task Entity Schema v1.0 - Task entity
            task_schema_v1 = builder.build_schema(DataType.TASK, version="1.0")
            self.register_schema(DataType.TASK, "1.0", task_schema_v1)
            logger.info(f"[SchemaRegistry] ✅ Registered Task entity schema with {len(task_schema_v1.transformers)} transformers")
            
            # Agent-Task Relationship Schema v1.0
            agent_task_schema_v1 = builder.build_schema(DataType.AGENT_TASK, version="1.0")
            self.register_schema(DataType.AGENT_TASK, "1.0", agent_task_schema_v1)
            logger.info(f"[SchemaRegistry] ✅ Registered Agent-Task relationship schema with {len(agent_task_schema_v1.transformers)} transformers")
            
            # Tool Entity Schema v1.0 - Tool entity
            tool_schema_v1 = builder.build_schema(DataType.TOOL, version="1.0")
            self.register_schema(DataType.TOOL, "1.0", tool_schema_v1)
            logger.info(f"[SchemaRegistry] ✅ Registered Tool entity schema with {len(tool_schema_v1.transformers)} transformers")
            
            # Agent-Tool Relationship Schema v1.0
            agent_tool_schema_v1 = builder.build_schema(DataType.AGENT_TOOL, version="1.0")
            self.register_schema(DataType.AGENT_TOOL, "1.0", agent_tool_schema_v1)
            logger.info(f"[SchemaRegistry] ✅ Registered Agent-Tool relationship schema with {len(agent_tool_schema_v1.transformers)} transformers")
            
            # Avatar Resource Entity Schema v1.0 - Avatar resource entity
            avatar_resource_schema_v1 = builder.build_schema(DataType.AVATAR_RESOURCE, version="1.0")
            self.register_schema(DataType.AVATAR_RESOURCE, "1.0", avatar_resource_schema_v1)
            logger.info(f"[SchemaRegistry] ✅ Registered Avatar Resource entity schema with {len(avatar_resource_schema_v1.transformers)} transformers")
            
            logger.info("[SchemaRegistry] ✅ All default schemas registered successfully")
        except Exception as e:
            logger.error(f"[SchemaRegistry] ❌ Failed to register schemas: {e}")
            import traceback
            logger.error(traceback.format_exc())


# Global registry instance
_schema_registry = SchemaRegistry()

# NOTE: Schemas are now registered lazily on first use (in get_schema method)
# This improves startup performance by ~16 seconds


def get_schema_registry() -> SchemaRegistry:
    """Get global Schema registry"""
    return _schema_registry


# Import json module
import json
