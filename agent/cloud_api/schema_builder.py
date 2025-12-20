"""
Schema Builder - Auto-build Schema from JSON mapping

Core Ideas:
1. Read field mapping from JSON mapping file
2. Auto-generate SchemaVersion
3. Only configure special transformation rules (e.g., JSON serialization)
"""

import json
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from agent.cloud_api.constants import DataType
from agent.cloud_api.schema_registry import SchemaVersion, FieldTransformer, FieldAction


@dataclass
class SchemaConfig:
    """Schema configuration (simplified)"""
    data_type: DataType
    version: str = "1.0"
    mapping_file: Optional[str] = None  # JSON mapping file path
    
    # Only configure fields that need special handling
    json_fields: List[str] = None  # Fields that need JSON serialization (local field names)
    custom_transformers: List[FieldTransformer] = None  # Custom transformers
    
    def __post_init__(self):
        if self.json_fields is None:
            self.json_fields = []
        if self.custom_transformers is None:
            self.custom_transformers = []


class SchemaBuilder:
    """Auto-build Schema from JSON mapping"""
    
    @staticmethod
    def build_from_config(config: SchemaConfig) -> SchemaVersion:
        """
        Build Schema from configuration
        
        Args:
            config: Schema configuration
            
        Returns:
            SchemaVersion instance
        """
        # 1. Load JSON mapping
        mapping_data = SchemaBuilder._load_mapping(config.data_type, config.mapping_file)
        
        # 2. Extract field mapping and required fields
        # Note: field_mapping now only contains mappings for fields with different names
        # Fields with same names will be handled automatically in SchemaVersion
        field_mapping = mapping_data.get('field_mapping', {})
        required_fields = mapping_data.get('cloud_required_fields', {})
        default_values = mapping_data.get('default_values', {})
        # Merge default_values into required_fields
        required_fields = {**default_values, **required_fields}
        excluded_fields = mapping_data.get('excluded_fields', [])
        aws_date_fields = mapping_data.get('aws_date_fields', [])
        aws_datetime_fields = mapping_data.get('aws_datetime_fields', [])
        
        # 3. Auto-generate transformers
        transformers = SchemaBuilder._build_transformers(
            field_mapping,
            config.json_fields,
            mapping_data.get('json_serialize_fields', []),
            excluded_fields,
            aws_date_fields,
            aws_datetime_fields,
            config.custom_transformers
        )
        
        # 4. Create SchemaVersion
        return SchemaVersion(
            version=config.version,
            fields=field_mapping,
            required_fields=required_fields,
            transformers=transformers
        )
    
    @staticmethod
    def _load_mapping(data_type: DataType, mapping_file: Optional[str] = None) -> Dict[str, Any]:
        """Load JSON mapping file"""
        if mapping_file is None:
            # Default path
            base_dir = os.path.dirname(__file__)
            mapping_file = os.path.join(
                base_dir, 'mappings',
                f'{data_type.value}_mapping.json'
            )
        
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: Mapping file not found: {mapping_file}")
            return {}
        except Exception as e:
            print(f"Error loading mapping file: {e}")
            return {}
    
    @staticmethod
    def _build_transformers(
        field_mapping: Dict[str, str],
        json_fields: List[str],
        json_serialize_fields: List[str],
        excluded_fields: List[str],
        aws_date_fields: List[str],
        aws_datetime_fields: List[str],
        custom_transformers: List[FieldTransformer]
    ) -> List[FieldTransformer]:
        """Auto-build transformer list"""
        from datetime import datetime, date
        import uuid
        
        transformers = []
        
        # 0. Add ID generation transformers for mapped ID fields
        # Generate UUID for empty ID fields (agid, askid, ataskid, toolid)
        for local_field, cloud_field in field_mapping.items():
            if local_field == 'id' and cloud_field in ['agid', 'askid', 'ataskid', 'toolid']:
                def make_id_generator(id_field):
                    def generate_id_if_empty(value):
                        if not value or value == '':
                            return str(uuid.uuid4())
                        return value
                    return generate_id_if_empty
                
                transformers.append(
                    FieldTransformer(
                        action=FieldAction.TRANSFORM,
                        source_field=cloud_field,
                        transform_func=make_id_generator(cloud_field)
                    )
                )
        
        # 1. Add REMOVE transformers for excluded fields
        for field in excluded_fields:
            transformers.append(
                FieldTransformer(
                    action=FieldAction.REMOVE,
                    source_field=field
                )
            )
        
        # 2. Add AWS Date transformers
        for local_field in aws_date_fields:
            cloud_field = field_mapping.get(local_field, local_field)
            
            def make_aws_date_func():
                def to_aws_date(value):
                    if value is None or value == '':
                        return None
                    if isinstance(value, str):
                        # Parse ISO 8601 and extract date part
                        if 'T' in value:
                            return value.split('T')[0]  # YYYY-MM-DD
                        return value
                    elif isinstance(value, datetime):
                        return value.strftime('%Y-%m-%d')
                    elif isinstance(value, date):
                        return value.strftime('%Y-%m-%d')
                    return str(value)
                return to_aws_date
            
            transformers.append(
                FieldTransformer(
                    action=FieldAction.TRANSFORM,
                    source_field=cloud_field,
                    transform_func=make_aws_date_func()
                )
            )
        
        # 3. Add AWS DateTime transformers
        for local_field in aws_datetime_fields:
            cloud_field = field_mapping.get(local_field, local_field)
            
            def make_aws_datetime_func():
                def to_aws_datetime(value):
                    if value is None or value == '':
                        return None
                    if isinstance(value, str):
                        # Already ISO 8601 format or timestamp string
                        if value.isdigit():
                            # Timestamp string, convert to int then to ISO 8601
                            timestamp_ms = int(value)
                            dt = datetime.fromtimestamp(timestamp_ms / 1000.0)
                            return dt.isoformat() + 'Z'
                        return value
                    elif isinstance(value, int):
                        # Timestamp in milliseconds
                        dt = datetime.fromtimestamp(value / 1000.0)
                        return dt.isoformat() + 'Z'
                    elif isinstance(value, datetime):
                        return value.isoformat() + 'Z' if value.tzinfo is None else value.isoformat()
                    elif isinstance(value, date):
                        return datetime.combine(value, datetime.min.time()).isoformat() + 'Z'
                    return str(value)
                return to_aws_datetime
            
            transformers.append(
                FieldTransformer(
                    action=FieldAction.TRANSFORM,
                    source_field=cloud_field,
                    transform_func=make_aws_datetime_func()
                )
            )
        
        # 4. Merge JSON field lists
        all_json_fields = set(json_fields) | set(json_serialize_fields)
        
        # 5. Create transformer for each JSON field
        for local_field in all_json_fields:
            # Get cloud field name, use same field name if no explicit mapping
            cloud_field = field_mapping.get(local_field, local_field)
            
            # Create separate functions to avoid closure issues
            def make_serialize_func():
                def serialize(x):
                    if isinstance(x, (dict, list)):
                        return json.dumps(x, ensure_ascii=False)
                    # Handle empty string or None - convert to empty JSON object
                    if x == '' or x is None:
                        return '{}'
                    return x
                return serialize
            
            def make_deserialize_func():
                def deserialize(x):
                    if isinstance(x, str) and x:
                        try:
                            return json.loads(x)
                        except:
                            return x
                    return x if x else {}
                return deserialize
            
            transformers.append(
                FieldTransformer(
                    action=FieldAction.TRANSFORM,
                    source_field=cloud_field,  # Cloud field name
                    transform_func=make_serialize_func(),
                    reverse_transform_func=make_deserialize_func()
                )
            )
        
        # 6. Add custom transformers
        transformers.extend(custom_transformers)
        
        return transformers


# Convenience function
def build_schema(
    data_type: DataType,
    version: str = "1.0",
    json_fields: List[str] = None,
    custom_transformers: List[FieldTransformer] = None
) -> SchemaVersion:
    """
    Convenience function: Build Schema from JSON mapping
    
    Args:
        data_type: Data type
        version: Version number
        json_fields: Fields that need JSON serialization (local field names)
        custom_transformers: Custom transformers
        
    Returns:
        SchemaVersion instance
        
    Example:
        # Simplest usage (auto-load from mapping file)
        schema = build_schema(DataType.SKILL)
        
        # Specify fields that need JSON serialization
        schema = build_schema(
            DataType.SKILL,
            json_fields=['diagram', 'config']
        )
        
        # Add custom transformers
        schema = build_schema(
            DataType.SKILL,
            json_fields=['diagram', 'config'],
            custom_transformers=[
                FieldTransformer(
                    action=FieldAction.ADD,
                    target_field="category",
                    default_value="general"
                )
            ]
        )
    """
    config = SchemaConfig(
        data_type=data_type,
        version=version,
        json_fields=json_fields or [],
        custom_transformers=custom_transformers or []
    )
    
    return SchemaBuilder.build_from_config(config)
