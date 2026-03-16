"""
FK Metadata - Foreign Key Constraint Metadata

定义数据库外键约束的元数据，用于自动化依赖处理。
这个文件是 FK 约束的单一真实来源（Single Source of Truth）。
"""

from agent.cloud_api.constants import DataType


# FK 约束元数据定义
# 格式：{
#     'table_name': {
#         'fk_constraint_name': {
#             'field': '本表中的外键字段名',
#             'references': DataType 枚举值,
#             'service': '对应的 DB 服务名',
#         }
#     }
# }
FK_CONSTRAINTS = {
    # agent_orgs 表
    'agent_orgs': {
        'fk_agent_org_parent': {
            'field': 'parent_id',
            'references': DataType.ORGANIZATION,
            'service': 'org_service',
        },
    },
    
    # agents 表
    'agents': {
        'fk_agent_supervisor': {
            'field': 'supervisor_id',
            'references': DataType.AGENT,
            'service': 'agent_service',
        },
        'fk_agent_avatar': {
            'field': 'avatar_resource_id',
            'references': DataType.AVATAR_RESOURCE,
            'service': 'avatar_service',
        },
    },
    
    # agent_tasks 表
    'agent_tasks': {
        'fk_agent_task_org': {
            'field': 'org_id',
            'references': DataType.ORGANIZATION,
            'service': 'org_service',
        },
    },
    
    # agent_org_rels 表
    'agent_org_rels': {
        'fk_aor_agent': {
            'field': 'agent_id',
            'references': DataType.AGENT,
            'service': 'agent_service',
        },
        'fk_aor_org': {
            'field': 'org_id',
            'references': DataType.ORGANIZATION,
            'service': 'org_service',
        },
    },
    
    # agent_skill_rels 表
    'agent_skill_rels': {
        'fk_asr_agent': {
            'field': 'agent_id',
            'references': DataType.AGENT,
            'service': 'agent_service',
        },
        'fk_asr_skill': {
            'field': 'skill_id',
            'references': DataType.SKILL,
            'service': 'skill_service',
        },
    },
    
    # agent_task_rels 表
    'agent_task_rels': {
        'fk_atr_agent': {
            'field': 'agent_id',
            'references': DataType.AGENT,
            'service': 'agent_service',
        },
        'fk_atr_task': {
            'field': 'task_id',
            'references': DataType.TASK,
            'service': 'task_service',
        },
        'fk_atr_vehicle': {
            'field': 'vehicle_id',
            'references': DataType.VEHICLE,
            'service': 'vehicle_service',
        },
    },
    
    # agent_skill_tool_rels 表
    'agent_skill_tool_rels': {
        'fk_ast_skill': {
            'field': 'skill_id',
            'references': DataType.SKILL,
            'service': 'skill_service',
        },
        'fk_ast_tool': {
            'field': 'tool_id',
            'references': DataType.TOOL,
            'service': 'tool_service',
        },
    },
    
    # agent_skill_knowledge_rels 表
    'agent_skill_knowledge_rels': {
        'fk_ask_skill': {
            'field': 'skill_id',
            'references': DataType.SKILL,
            'service': 'skill_service',
        },
        'fk_ask_knowledge': {
            'field': 'knowledge_id',
            'references': DataType.KNOWLEDGE,
            'service': 'knowledge_service',
        },
    },
    
    # agent_task_skill_rels 表
    'agent_task_skill_rels': {
        'fk_ats_task': {
            'field': 'task_id',
            'references': DataType.TASK,
            'service': 'task_service',
        },
        'fk_ats_skill': {
            'field': 'skill_id',
            'references': DataType.SKILL,
            'service': 'skill_service',
        },
    },
}


# DataType 到表名的映射
DATATYPE_TO_TABLE = {
    DataType.ORGANIZATION: 'agent_orgs',
    DataType.AGENT: 'agents',
    DataType.SKILL: 'agent_skills',
    DataType.TASK: 'agent_tasks',
    DataType.TOOL: 'agent_tools',
    DataType.KNOWLEDGE: 'agent_knowledges',
    DataType.AVATAR_RESOURCE: 'avatar_resources',
    DataType.VEHICLE: 'agent_vehicles',
    DataType.AGENT_ORG: 'agent_org_rels',
    DataType.AGENT_SKILL: 'agent_skill_rels',
    DataType.AGENT_TASK: 'agent_task_rels',
    DataType.SKILL_TOOL: 'agent_skill_tool_rels',
    DataType.SKILL_KNOWLEDGE: 'agent_skill_knowledge_rels',
    DataType.TASK_SKILL: 'agent_task_skill_rels',
}


def get_fk_constraints_for_datatype(data_type: DataType) -> dict:
    """
    获取指定 DataType 对应表的所有 FK 约束
    
    Args:
        data_type: DataType 枚举值
        
    Returns:
        FK 约束字典，格式：{fk_name: {field, references, service}}
    """
    table_name = DATATYPE_TO_TABLE.get(data_type)
    if not table_name:
        return {}
    
    return FK_CONSTRAINTS.get(table_name, {})


def get_fk_dependency_info(data_type: DataType, fk_constraint_name: str) -> dict:
    """
    获取指定 FK 约束的依赖信息
    
    Args:
        data_type: DataType 枚举值
        fk_constraint_name: FK 约束名称
        
    Returns:
        依赖信息字典：{field, references, service}，如果不存在返回 None
    """
    constraints = get_fk_constraints_for_datatype(data_type)
    return constraints.get(fk_constraint_name)


def build_fk_dependency_config() -> dict:
    """
    动态构建 FK 依赖配置
    
    从 FK_CONSTRAINTS 元数据自动生成完整的依赖配置字典。
    支持 ADD 和 UPDATE 操作。
    
    Returns:
        配置字典，格式：{(data_type, operation, fk_constraint): (field, dep_type, service, DataType)}
    """
    config = {}
    
    for data_type, table_name in DATATYPE_TO_TABLE.items():
        constraints = FK_CONSTRAINTS.get(table_name, {})
        
        for fk_name, fk_info in constraints.items():
            field = fk_info['field']
            ref_datatype = fk_info['references']
            service = fk_info['service']
            
            # 从 DataType 枚举值中提取类型名称（用于日志）
            dep_type_name = ref_datatype.value
            
            # 为 ADD 和 UPDATE 操作都添加配置
            for operation in ['add', 'update']:
                key = (data_type.value, operation, fk_name)
                value = (field, dep_type_name, service, ref_datatype)
                config[key] = value
    
    return config
