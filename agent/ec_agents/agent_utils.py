import json

from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
# Use unified CloudAPIService instead of directly importing cloud_api functions
from agent.cloud_api.cloud_api_service import get_cloud_service
from agent.cloud_api.constants import DataType, Operation
# Note: Prefer using DB Model's to_dict() method to avoid field duplication
# DB Model already provides complete field definitions and to_dict() method
# Temporarily keep old imports for functions not yet migrated (Tool, Knowledge)
from agent.cloud_api.cloud_api import (
    # Tool entity operations (renamed to match new naming convention)
    send_add_tools_request_to_cloud,
    send_update_tools_request_to_cloud,
    send_remove_tools_request_to_cloud,
    send_get_agent_tools_request_to_cloud,  # Query function (old name, still exists)
    # Knowledge operations (not yet migrated)
    send_add_knowledges_request_to_cloud,
    send_update_knowledges_request_to_cloud,
    send_get_knowledges_request_to_cloud,
    send_remove_knowledges_request_to_cloud,
)
from agent.ec_agent import *
import traceback
from agent.ec_skill import EC_Skill
from utils.logger_helper import logger_helper as logger
from agent.a2a.langgraph_agent.utils import get_a2a_server_url
from agent.a2a.common.types import AgentCard, AgentCapabilities
import json
from agent.playwright import create_browser_use_llm




import concurrent.futures
SUPPORTED_CONTENT_TYPES = ["text", "text/plain", "json", "file"]


# ============================================================================
# Offline Queue Helper Functions
# ============================================================================

def _save_to_offline_queue(data_type: DataType, cloud_data: list, operation: Operation, errors: list) -> None:
    """
    Save failed sync tasks to offline queue
    
    Args:
        data_type: Data type
        cloud_data: List of cloud format data
        operation: Operation type
        errors: List of error messages
    """
    try:
        from agent.cloud_api.offline_sync_queue import get_sync_queue
        
        sync_queue = get_sync_queue()
        
        # Create a task for each data item
        for data_item in cloud_data:
            task_id = sync_queue.add(
                data_type=str(data_type),
                data=data_item,
                operation=str(operation)
            )
            logger.info(f"💾 Saved to offline queue: {task_id} ({data_type}.{operation})")
            
        error_msg = errors[0] if errors else 'Unknown error'
        logger.warning(f"⚠️ Cloud sync failed, {len(cloud_data)} item(s) saved to offline queue: {error_msg}")
        
    except Exception as e:
        logger.error(f"❌ Failed to save to offline queue: {e}")


# ============================================================================
# Agent Cloud Sync Functions
# ============================================================================

def _cloud_agent_to_local(cloud_agent, mainwin):
    """
    Convert cloud format agent dict to local format using Schema
    Frontend sends cloud format (org_id, supervisor_id, etc.)
    Use Schema to convert to local format (organizations, supervisors, etc.)
    Simplified: removed Adapter layer, use Schema directly
    """
    from agent.cloud_api.schema_registry import get_schema_registry
    schema_registry = get_schema_registry()
    schema = schema_registry.get_schema(DataType.AGENT)
    return schema.from_cloud(cloud_agent)


# ============================================================================
# Unified Model-based conversion (Best practice - no field duplication)
# ============================================================================

def _extract_from_object(obj, mainwin):
    """
    Extract fields from object (fallback for non-DB objects)
    
    Used when object doesn't have to_dict() method (e.g., EC_Agent)
    """
    data = {}
    
    # Extract from card attribute
    if hasattr(obj, 'card'):
        for field in ['id', 'name', 'description', 'url', 'version', 'capabilities', 'created_at', 'updated_at', 'ext']:
            if hasattr(obj.card, field):
                value = getattr(obj.card, field, None)
                if value is not None:
                    data[field] = value
    
    # Extract from object
    for field in ['gender', 'title', 'rank', 'birthday', 'status', 'org_id', 'supervisor_id', 'personalities']:
        if hasattr(obj, field):
            value = getattr(obj, field, None)
            if value is not None:
                data[field] = value
    
    # Special mappings
    if hasattr(obj, 'vehicle'):
        data['vehicle_id'] = obj.vehicle
    
    if hasattr(obj, 'work_flow'):  # Skill special case
        data['langgraph'] = obj.work_flow
    
    # Owner
    if mainwin and 'owner' not in data:
        data['owner'] = mainwin.user
    
    # Extra data
    if hasattr(obj, 'card') and hasattr(obj.card, 'description') and 'extra_data' not in data:
        data['extra_data'] = {'description': obj.card.description}
    
    return data


def _agent_to_dict(agent, mainwin):
    """
    Convert Agent object to dict (Unified Model approach)
    
    Priority:
    1. Dict - return directly
    2. DB Model - use to_dict() method (avoid field duplication)
    3. Other objects - manual field extraction
    
    Benefits:
    - Zero field duplication: DB Model is the single source of truth
    - Zero maintenance cost: adding fields only requires updating DB Model
    - Unified data source: ensures consistency
    """
    # 1. Dict - return directly
    if isinstance(agent, dict):
        if 'owner' not in agent and mainwin:
            agent['owner'] = mainwin.user
        return agent
    
    # 2. DB Model - use to_dict() method
    if hasattr(agent, 'to_dict') and callable(agent.to_dict):
        data = agent.to_dict()
        if mainwin and 'owner' not in data:
            data['owner'] = mainwin.user
        return data
    
    # 3. Other objects - manual extraction
    return _extract_from_object(agent, mainwin)


def _skill_to_dict(skill, mainwin):
    """
    Convert Skill object to dict (Unified Model approach)
    
    Benefits:
    - Prefer DB Model's to_dict() method
    - Avoid field duplication
    """
    if isinstance(skill, dict):
        if 'owner' not in skill and mainwin:
            skill['owner'] = mainwin.user
        return skill
    
    if hasattr(skill, 'to_dict') and callable(skill.to_dict):
        data = skill.to_dict()
        if mainwin and 'owner' not in data:
            data['owner'] = mainwin.user
        return data
    
    return _extract_from_object(skill, mainwin)


def _task_to_dict(task, mainwin):
    """
    Convert Task object to dict (Unified Model approach)
    
    Benefits:
    - Prefer DB Model's to_dict() method
    - Avoid field duplication
    """
    if isinstance(task, dict):
        if 'owner' not in task and mainwin:
            task['owner'] = mainwin.user
        return task
    
    if hasattr(task, 'to_dict') and callable(task.to_dict):
        data = task.to_dict()
        if mainwin and 'owner' not in data:
            data['owner'] = mainwin.user
        return data
    
    return _extract_from_object(task, mainwin)


def _tool_to_dict(tool, mainwin):
    """
    Convert Tool object to dict (Unified Model approach)
    
    Benefits:
    - Prefer DB Model's to_dict() method
    - Avoid field duplication
    """
    if isinstance(tool, dict):
        if 'owner' not in tool and mainwin:
            tool['owner'] = mainwin.user
        return tool
    
    if hasattr(tool, 'to_dict') and callable(tool.to_dict):
        data = tool.to_dict()
        if mainwin and 'owner' not in data:
            data['owner'] = mainwin.user
        return data
    
    return _extract_from_object(tool, mainwin)


def add_new_agents_to_cloud(mainwin, agents):
    """
    Add new Agents to cloud (using unified service interface, auto-cache on failure)
    
    Args:
        mainwin: MainWindow instance
        agents: Agent data list (supports both object and dict format)
        
    Returns:
        Sync result dictionary
    """
    # Ensure all items are dicts (auto-detect type)
    dict_agents = []
    for agent in agents:
        if isinstance(agent, dict):
            # Check if dict is in cloud format (has org_id) or local format (has organizations)
            if 'org_id' in agent or 'supervisor_id' in agent:
                # Cloud format from frontend, need to convert to local format
                dict_agents.append(_cloud_agent_to_local(agent, mainwin))
            else:
                # Already in local format
                dict_agents.append(agent)
        else:
            dict_agents.append(_agent_to_dict(agent, mainwin))
    
    # Call cloud service (adapter handles field mapping)
    service = get_cloud_service(DataType.AGENT)
    result = service.sync_to_cloud(dict_agents, Operation.ADD)
    
    # Auto-save to offline queue on failure
    if not result.get('success'):
        _save_to_offline_queue(DataType.AGENT, dict_agents, Operation.ADD, result.get('errors', []))
    
    return result


def save_agents_to_cloud(mainwin, agents):
    """
    Update Agents to cloud (using unified service interface, auto-cache on failure)
    
    Args:
        mainwin: MainWindow instance
        agents: Agent data list (supports both object and dict format)
        
    Returns:
        Sync result dictionary
    """
    # Ensure all items are dicts (auto-detect type)
    dict_agents = []
    for agent in agents:
        if isinstance(agent, dict):
            dict_agents.append(agent)
        else:
            dict_agents.append(_agent_to_dict(agent, mainwin))
    
    # Call cloud service (adapter handles field mapping)
    service = get_cloud_service(DataType.AGENT)
    result = service.sync_to_cloud(dict_agents, Operation.UPDATE)
    
    # Auto-save to offline queue on failure
    if not result.get('success'):
        _save_to_offline_queue(DataType.AGENT, dict_agents, Operation.UPDATE, result.get('errors', []))
    
    return result



def load_agents_from_cloud(mainwin):
    """Load Agents from cloud"""
    cloud_agents = []
    try:
        from agent.cloud_api.cloud_api import send_get_agents_request_to_cloud
        import requests
        
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return cloud_agents
            
        session = requests.Session()
        jresp = send_get_agents_request_to_cloud(session, auth_token, mainwin.getWanApiEndpoint())
        
        if isinstance(jresp, dict) and 'body' in jresp:
            all_agents = json.loads(jresp['body'])
        else:
            logger.warning("No agents data returned from cloud")
            all_agents = []
        
        # Convert cloud format to local format using Schema
        from agent.cloud_api.schema_registry import get_schema_registry
        schema_registry = get_schema_registry()
        schema = schema_registry.get_schema(DataType.AGENT)
        
        for cloud_agent in all_agents:
            # Convert cloud format to local format
            local_agent = schema.from_cloud(cloud_agent)
            new_agent = gen_new_agent(mainwin, local_agent)
            if new_agent:
                cloud_agents.append(new_agent)

        if cloud_agents:
            mainwin.agents = cloud_agents
        
        return cloud_agents

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorLoadAgentsFromCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorLoadAgentsFromCloud: traceback information not available:" + str(e)
        logger.error(ex_stat)
    
    return cloud_agents


def gen_agent_from_cloud_data(mainwin, ajs):
    try:
        llm = mainwin.llm
        all_skills = mainwin.agent_skills
        all_tasks = mainwin.agent_tasks
        if ajs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in ajs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_skills if sk.getSkid() in skids]

        if ajs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in ajs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = ajs['id'],
            name=ajs['name'],
            description=ajs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)

        # Use mainwin's unified browser_use_llm instance (shared across all agents)
        browser_use_llm = mainwin.browser_use_llm

        new_agent = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skills=agent_skills, tasks=agent_tasks)
        return new_agent
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgent: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def gen_new_agent(mainwin, ajs):
    try:
        llm = mainwin.llm
        all_skills = mainwin.agent_skills
        all_tasks = mainwin.agent_tasks
        logger.debug("ajs:", ajs)
        if ajs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in ajs['skills'].split(",")]
        else:
            skids = []

        logger.debug("skids:", skids, len(all_skills), all_skills[0])
        agent_skills = [sk for sk in all_skills if int(sk.id) in skids]

        if ajs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in ajs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = ajs['id'],
            name=ajs['name'],
            description=ajs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)

        # Use mainwin's unified browser_use_llm instance (shared across all agents)
        browser_use_llm = mainwin.browser_use_llm

        new_agent = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skills=agent_skills, tasks=agent_tasks)
        return new_agent
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgent: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


# ============================================================================
# DEPRECATED: Old prep functions (kept for reference)
# Now using _xxx_to_dict() + Adapter for data conversion
# ============================================================================

# def prep_agent_data_for_cloud(mainwin, agents):
#     try:
#         ajs = []
#         for agent in agents:
#             aj = {
#                 "agid": agent.card.id,
#                 "owner": mainwin.user,
#                 "gender": agent.gender,
#                 "organizations": agent.organizations,
#                 "rank": agent.rank,
#                 "supervisors": agent.supervisors,
#                 "subordinates": agent.subordinates,
#                 "title": agent.title,
#                 "personalities": agent.personalities,
#                 "birthday": agent.birthday,
#                 "name": agent.card.name,
#                 "status": agent.status,
#                 "metadata": json.dumps({"description": agent.card.description}),
#                 "vehicle": agent.vehicle,
#                 "skills": json.dumps([sk.id for sk in agent.skill_set]),
#                 "tasks": json.dumps([task.id for task in agent.tasks]),
#                 "knowledges": ""
#             }
#             ajs.append(aj)
#
#         return ajs
#     except Exception as e:
#         traceback_info = traceback.extract_tb(e.__traceback__)
#         if traceback_info:
#             ex_stat = "ErrorNewAgent:" + traceback.format_exc() + " " + str(e)
#         else:
#             ex_stat = "ErrorNewAgent: traceback information not available:" + str(e)
#         logger.error(ex_stat)
#         return None


def remove_agents_from_cloud(mainwin, agents):
    """
    Delete Agents from cloud (using unified service interface, auto-cache on failure)
    
    Args:
        mainwin: MainWindow instance
        agents: Agent data list (supports both object and dict format)
        
    Returns:
        Sync result dictionary
    """
    # Ensure all items are dicts (auto-detect type)
    dict_agents = []
    for agent in agents:
        if isinstance(agent, dict):
            dict_agents.append(agent)
        else:
            dict_agents.append(_agent_to_dict(agent, mainwin))
    
    # Call cloud service (adapter handles field mapping)
    service = get_cloud_service(DataType.AGENT)
    result = service.sync_to_cloud(dict_agents, Operation.DELETE)
    
    # Auto-save to offline queue on failure
    if not result.get('success'):
        _save_to_offline_queue(DataType.AGENT, dict_agents, Operation.DELETE, result.get('errors', []))
    
    return result

# ###########################################################################################
# agent skill related
# ###########################################################################################

def add_new_agent_skills_to_cloud(mainwin, skills):
    """Add new Skills to cloud (using unified service interface, auto-cache on failure)"""
    # Ensure all items are dicts (auto-detect type)
    dict_skills = []
    for skill in skills:
        if isinstance(skill, dict):
            dict_skills.append(skill)
        else:
            dict_skills.append(_skill_to_dict(skill, mainwin))
    
    service = get_cloud_service(DataType.SKILL)
    result = service.sync_to_cloud(dict_skills, Operation.ADD)
    
    if not result.get('success'):
        _save_to_offline_queue(DataType.SKILL, dict_skills, Operation.ADD, result.get('errors', []))
    
    return result


def save_agent_skills_to_cloud(mainwin, skills):
    """Update Skills to cloud (using unified service interface, auto-cache on failure)"""
    # Ensure all items are dicts (auto-detect type)
    dict_skills = []
    for skill in skills:
        if isinstance(skill, dict):
            dict_skills.append(skill)
        else:
            dict_skills.append(_skill_to_dict(skill, mainwin))
    
    service = get_cloud_service(DataType.SKILL)
    result = service.sync_to_cloud(dict_skills, Operation.UPDATE)
    
    if not result.get('success'):
        _save_to_offline_queue(DataType.SKILL, dict_skills, Operation.UPDATE, result.get('errors', []))
    
    return result


def load_agent_skills_from_cloud(mainwin):
    """Load Skills from cloud"""
    cloud_agent_skills = []
    try:
        from agent.cloud_api.cloud_api import send_get_agent_skills_request_to_cloud
        import requests
        
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return cloud_agent_skills
            
        session = requests.Session()
        jresp = send_get_agent_skills_request_to_cloud(session, auth_token, mainwin.getWanApiEndpoint())
        
        if isinstance(jresp, dict) and 'body' in jresp:
            all_agent_skills = json.loads(jresp['body'])
        else:
            logger.warning("No agent skills data returned from cloud")
            all_agent_skills = []
            
        # Convert cloud format to local format using Schema
        from agent.cloud_api.schema_registry import get_schema_registry
        schema_registry = get_schema_registry()
        schema = schema_registry.get_schema(DataType.SKILL)
        
        for cloud_skill in all_agent_skills:
            # Convert cloud format to local format
            local_skill = schema.from_cloud(cloud_skill)
            new_agent_skill = gen_new_agent_skill(mainwin, local_skill)
            if new_agent_skill:
                cloud_agent_skills.append(new_agent_skill)

        if cloud_agent_skills:
            mainwin.agent_skills = cloud_agent_skills
        
        return cloud_agent_skills

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorLoadAgentSkillsFromCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorLoadAgentSkillsFromCloud: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return []

    return cloud_agent_skills


def gen_agent_skill_from_cloud_data(mainwin, askjs):
    try:
        llm = mainwin.llm
        all_skills = mainwin.agent_skills
        all_tasks = mainwin.agent_tasks
        if askjs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in askjs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_skills if sk.getSkid() in skids]

        if askjs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in askjs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = askjs['id'],
            name=askjs['name'],
            description=askjs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)

        # Use mainwin's unified browser_use_llm instance (shared across all agents)
        browser_use_llm = mainwin.browser_use_llm

        new_agent = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skills=agent_skills, tasks=agent_tasks)
        return new_agent
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgent: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def gen_new_agent_skill(mainwin, askjs):
    try:
        llm = mainwin.llm
        all_skills = mainwin.agent_skills
        all_tasks = mainwin.agent_tasks
        if askjs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in askjs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_skills if sk.getSkid() in skids]

        if askjs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in askjs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = askjs['id'],
            name=askjs['name'],
            description=askjs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)

        new_agent_skill = EC_Skill(mainwin=mainwin, llm=llm, card=agent_card, skills=agent_skills, tasks=agent_tasks)
        return new_agent_skill
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgentSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgentSkill: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


# def prep_agent_skills_data_for_cloud(mainwin, agent_skills):
#     try:
#         askjs = []
#         for ask in agent_skills:
#             askj = {
#                 "askid": ask.id,
#                 "owner": mainwin.user,
#                 "name": ask.name,
#                 "description": ask.description,
#                 "status": ask.status,
#                 "path": ask.path,
#                 "flowgram": json.dumps(ask.diagram),
#                 "langgraph": json.dumps(ask.work_flow),
#                 "config": json.dumps(ask.config),
#                 "price": str(ask.price)
#             }
#             askjs.append(askj)
#
#         return askjs
#     except Exception as e:
#         traceback_info = traceback.extract_tb(e.__traceback__)
#         if traceback_info:
#             ex_stat = "ErrorNewAgentSkill:" + traceback.format_exc() + " " + str(e)
#         else:
#             ex_stat = "ErrorNewAgentSkill: traceback information not available:" + str(e)
#         logger.error(ex_stat)
#         return None


def remove_agent_skills_from_cloud(mainwin, agent_skills):
    """Delete Skills from cloud (using unified service interface, auto-cache on failure)"""
    # Ensure all items are dicts (auto-detect type)
    dict_skills = []
    for skill in agent_skills:
        if isinstance(skill, dict):
            dict_skills.append(skill)
        else:
            dict_skills.append(_skill_to_dict(skill, mainwin))
    
    service = get_cloud_service(DataType.SKILL)
    result = service.sync_to_cloud(dict_skills, Operation.DELETE)
    
    if not result.get('success'):
        _save_to_offline_queue(DataType.SKILL, dict_skills, Operation.DELETE, result.get('errors', []))
    
    return result

# ###########################################################################################
# agent task related
# ###########################################################################################

def add_new_agent_tools_to_cloud(mainwin, tools):
    """Add new Tools to cloud (using unified service interface, auto-cache on failure)"""
    # Ensure all items are dicts (auto-detect type)
    dict_tools = []
    for tool in tools:
        if isinstance(tool, dict):
            dict_tools.append(tool)
        else:
            dict_tools.append(_tool_to_dict(tool, mainwin))
    
    service = get_cloud_service(DataType.TOOL)
    result = service.sync_to_cloud(dict_tools, Operation.ADD)
    
    if not result.get('success'):
        _save_to_offline_queue(DataType.TOOL, dict_tools, Operation.ADD, result.get('errors', []))
    
    return result


def save_agent_tools_to_cloud(mainwin, tools):
    """Update Tools to cloud (using unified service interface, auto-cache on failure)"""
    # Ensure all items are dicts (auto-detect type)
    dict_tools = []
    for tool in tools:
        if isinstance(tool, dict):
            dict_tools.append(tool)
        else:
            dict_tools.append(_tool_to_dict(tool, mainwin))
    
    service = get_cloud_service(DataType.TOOL)
    result = service.sync_to_cloud(dict_tools, Operation.UPDATE)
    
    if not result.get('success'):
        _save_to_offline_queue(DataType.TOOL, dict_tools, Operation.UPDATE, result.get('errors', []))
    
    return result



def load_agent_tools_from_cloud(mainwin):
    try:
        cloud_agent_tools = []
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return cloud_agent_tools
        jresp = send_get_agent_tools_request_to_cloud(mainwin.session, auth_token, mainwin.getWanApiEndpoint())
        if isinstance(jresp, dict) and 'body' in jresp:
            all_agent_tools = json.loads(jresp['body'])
        else:
            logger.warning("No agent tools data returned from cloud")
            all_agent_tools = []
        
        # Convert cloud format to local format using Schema
        from agent.cloud_api.schema_registry import get_schema_registry
        schema_registry = get_schema_registry()
        schema = schema_registry.get_schema(DataType.TOOL)
        
        for cloud_tool in all_agent_tools:
            # Convert cloud format to local format
            local_tool = schema.from_cloud(cloud_tool)
            new_agent_tool = gen_new_agent_tools(mainwin, local_tool)
            if new_agent_tool:
                cloud_agent_tools.append(new_agent_tool)

        if cloud_agent_tools:
            mainwin.agent_tools = cloud_agent_tools
        
        return cloud_agent_tools

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorLoadAgentToolsFromCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorLoadAgentToolsFromCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return []


def gen_agent_tools_from_cloud_data(mainwin, taskjs):
    try:
        llm = mainwin.llm
        all_tasks = mainwin.agent_tasks
        if taskjs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in taskjs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_tasks if sk.getSkid() in skids]

        if taskjs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in taskjs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = taskjs['id'],
            name=taskjs['name'],
            description=taskjs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)
        # Use mainwin's unified browser_use_llm instance (shared across all agents)
        browser_use_llm = mainwin.browser_use_llm
        new_agent = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skills=agent_skills, tasks=agent_tasks)
        return new_agent
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgentTasks:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgentTasks: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def gen_new_agent_tools(mainwin, tooljs):
    try:
        llm = mainwin.llm
        all_tasks = mainwin.agent_tasks
        if tooljs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in tooljs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_tasks if sk.getSkid() in skids]

        if tooljs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in tooljs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = tooljs['id'],
            name=tooljs['name'],
            description=tooljs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)

        new_agent_task = EC_Skill(mainwin=mainwin, llm=llm, card=agent_card, skills=agent_skills, tasks=agent_tasks)
        return new_agent_task
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgentTools:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgentTools: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


# def prep_agent_tools_data_for_cloud(mainwin, agent_tools):
#     try:
#         tooljs = []
#         for tool in agent_tools:
#             toolj = {
#                 "agid": tool.card.id,
#                 "owner": mainwin.user,
#                 "gender": tool.gender,
#                 "organizations": tool.organizations,
#                 "rank": tool.rank,
#                 "supervisors": tool.supervisors,
#                 "subordinates": tool.subordinates,
#                 "title": tool.title,
#                 "personalities": tool.personalities,
#                 "birthday": tool.birthday,
#                 "name": tool.card.name,
#                 "status": tool.status,
#                 "metadata": json.dumps({"description": tool.card.description}),
#                 "vehicle": tool.vehicle,
#                 "skills": json.dumps([sk.id for sk in tool.skill_set]),
#                 "tasks": json.dumps([task.id for task in tool.tasks]),
#                 "knowledges": ""
#             }
#             tooljs.append(toolj)
#
#         return tooljs
#     except Exception as e:
#         traceback_info = traceback.extract_tb(e.__traceback__)
#         if traceback_info:
#             ex_stat = "ErrorNewAgentTools:" + traceback.format_exc() + " " + str(e)
#         else:
#             ex_stat = "ErrorNewAgentTools: traceback information not available:" + str(e)
#         logger.error(ex_stat)
#         return None


def remove_agent_tools_from_cloud(mainwin, agent_tools):
    """Delete Tools from cloud (using unified service interface, auto-cache on failure)"""
    # Ensure all items are dicts (auto-detect type)
    dict_tools = []
    for tool in agent_tools:
        if isinstance(tool, dict):
            dict_tools.append(tool)
        else:
            dict_tools.append(_tool_to_dict(tool, mainwin))
    
    service = get_cloud_service(DataType.TOOL)
    result = service.sync_to_cloud(dict_tools, Operation.DELETE)
    
    if not result.get('success'):
        _save_to_offline_queue(DataType.TOOL, dict_tools, Operation.DELETE, result.get('errors', []))
    
    return result

# ###########################################################################################
# agent tools related
# ###########################################################################################

def add_new_agent_tasks_to_cloud(mainwin, tasks):
    """Add new Tasks to cloud (using unified service interface, auto-cache on failure)"""
    # Ensure all items are dicts (auto-detect type)
    dict_tasks = []
    for task in tasks:
        if isinstance(task, dict):
            dict_tasks.append(task)
        else:
            dict_tasks.append(_task_to_dict(task, mainwin))
    
    service = get_cloud_service(DataType.TASK)
    result = service.sync_to_cloud(dict_tasks, Operation.ADD)
    
    if not result.get('success'):
        _save_to_offline_queue(DataType.TASK, dict_tasks, Operation.ADD, result.get('errors', []))
    
    return result


def save_agent_tasks_to_cloud(mainwin, tasks):
    """Update Tasks to cloud (using unified service interface, auto-cache on failure)"""
    # Ensure all items are dicts (auto-detect type)
    dict_tasks = []
    for task in tasks:
        if isinstance(task, dict):
            dict_tasks.append(task)
        else:
            dict_tasks.append(_task_to_dict(task, mainwin))
    
    service = get_cloud_service(DataType.TASK)
    result = service.sync_to_cloud(dict_tasks, Operation.UPDATE)
    
    if not result.get('success'):
        _save_to_offline_queue(DataType.TASK, dict_tasks, Operation.UPDATE, result.get('errors', []))
    
    return result



def load_agent_tasks_from_cloud(mainwin):
    """Load Tasks from cloud"""
    cloud_agent_tasks = []
    try:
        from agent.cloud_api.cloud_api import send_get_agent_tasks_request_to_cloud
        import requests
        
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return cloud_agent_tasks
            
        session = requests.Session()
        jresp = send_get_agent_tasks_request_to_cloud(session, auth_token, mainwin.getWanApiEndpoint())
        
        if isinstance(jresp, dict) and 'body' in jresp:
            all_agent_tasks = json.loads(jresp['body'])
        else:
            logger.warning("No agent tasks data returned from cloud")
            all_agent_tasks = []
            
        # Convert cloud format to local format using Schema
        from agent.cloud_api.schema_registry import get_schema_registry
        schema_registry = get_schema_registry()
        schema = schema_registry.get_schema(DataType.TASK)
        
        for cloud_task in all_agent_tasks:
            # Convert cloud format to local format
            local_task = schema.from_cloud(cloud_task)
            new_agent_task = gen_new_agent_tasks(mainwin, local_task)
            if new_agent_task:
                cloud_agent_tasks.append(new_agent_task)

        if cloud_agent_tasks:
            mainwin.agent_tasks = cloud_agent_tasks
        
        return cloud_agent_tasks

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorLoadAgentTasksFromCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorLoadAgentTasksFromCloud: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return []

    return cloud_agent_tasks


def gen_agent_tasks_from_cloud_data(mainwin, taskjs):
    try:
        llm = mainwin.llm
        all_tasks = mainwin.agent_tasks
        if taskjs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in taskjs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_tasks if sk.getSkid() in skids]

        if taskjs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in taskjs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = taskjs['id'],
            name=taskjs['name'],
            description=taskjs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)
        # Use mainwin's unified browser_use_llm instance (shared across all agents)
        browser_use_llm = mainwin.browser_use_llm
        new_agent = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skills=agent_skills, tasks=agent_tasks)
        return new_agent
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgentTasks:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgentTasks: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def gen_new_agent_tasks(mainwin, taskjs):
    try:
        llm = mainwin.llm
        all_tasks = mainwin.agent_tasks
        if taskjs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in taskjs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_tasks if sk.getSkid() in skids]

        if taskjs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in taskjs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = taskjs['id'],
            name=taskjs['name'],
            description=taskjs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)

        new_agent_task = EC_Skill(mainwin=mainwin, llm=llm, card=agent_card, skills=agent_skills, tasks=agent_tasks)
        return new_agent_task
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgentTasks:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgentTasks: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


# def prep_agent_tasks_data_for_cloud(mainwin, agent_tasks):
#     try:
#         taskjs = []
#         for task in agent_tasks:
#             taskj = {
#                 "toolid": getattr(task, 'id', ''),
#                 "owner": mainwin.user,
#                 "name": getattr(task, 'name', ''),
#                 "description": getattr(task, 'description', ''),
#                 "link": getattr(task, 'link', ''),
#                 "protocol": json.dumps(getattr(task, 'protocol', {})),
#                 "status": getattr(task, 'status', 'active'),
#                 "metadata": json.dumps(getattr(task, 'work_flow', {})),
#                 "price": json.dumps(getattr(task, 'config', {}))
#             }
#             taskjs.append(taskj)
#
#         return taskjs
#     except Exception as e:
#         logger.error(f"ErrorPrepAgentTasks: {traceback.format_exc()}")
#         return []


def remove_agent_tasks_from_cloud(mainwin, agent_tasks):
    """Delete Tasks from cloud (using unified service interface, auto-cache on failure)"""
    # Ensure all items are dicts (auto-detect type)
    dict_tasks = []
    for task in agent_tasks:
        if isinstance(task, dict):
            dict_tasks.append(task)
        else:
            dict_tasks.append(_task_to_dict(task, mainwin))
    
    service = get_cloud_service(DataType.TASK)
    result = service.sync_to_cloud(dict_tasks, Operation.DELETE)
    
    if not result.get('success'):
        _save_to_offline_queue(DataType.TASK, dict_tasks, Operation.DELETE, result.get('errors', []))
    
    return result

# ###########################################################################################
# agent knowledge related
# ###########################################################################################

def add_new_knowledges_to_cloud(mainwin, knowledges):
    try:
        cloud_knowledges = prep_knowledges_data_for_cloud(mainwin, knowledges)
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return {"success": False, "message": "No authentication token"}
        jresp = send_add_knowledges_request_to_cloud(mainwin.session, cloud_knowledges, auth_token, mainwin.getWanApiEndpoint())
        return jresp
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAddNewKnowledgesToCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAddNewKnowledgesToCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return []


def save_knowledges_to_cloud(mainwin, knowledges):
    try:
        cloud_knowledges = prep_knowledges_data_for_cloud(mainwin, knowledges)
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return {"success": False, "message": "No authentication token"}
        jresp = send_update_knowledges_request_to_cloud(mainwin.session, cloud_knowledges,
                                                 auth_token,
                                                 mainwin.getWanApiEndpoint())
        return jresp
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAddNewKnowledgesToCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAddNewKnowledgesToCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return []



def load_knowledges_from_cloud(mainwin):
    try:
        cloud_knowledges = []
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return cloud_knowledges
        jresp = send_get_knowledges_request_to_cloud(mainwin.session, auth_token, mainwin.getWanApiEndpoint())
        if isinstance(jresp, dict) and 'body' in jresp:
            all_knowledges = json.loads(jresp['body'])
        else:
            logger.warning("No knowledges data returned from cloud")
            all_knowledges = []
        for kjs in all_knowledges:
            new_knowledge = gen_new_knowledge(mainwin, kjs)
            if new_knowledge:
                cloud_knowledges.append(new_knowledge)

        mainwin.knowledges = cloud_knowledges
        return cloud_knowledges

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorLoadKnowledgesFromCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorLoadKnowledgesFromCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return []


def gen_knowledge_from_cloud_data(mainwin, kjs):
    try:
        llm = mainwin.llm
        all_skills = mainwin.agent_skills
        all_tasks = mainwin.agent_tasks
        if kjs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in kjs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_skills if sk.getSkid() in skids]

        if kjs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in kjs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = kjs['id'],
            name=kjs['name'],
            description=kjs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)
        # Use mainwin's unified browser_use_llm instance (shared across all agents)
        browser_use_llm = mainwin.browser_use_llm
        new_agent = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skills=agent_skills, tasks=agent_tasks)
        return new_agent
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewKnowledges:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewKnowledges: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def gen_new_knowledge(mainwin, kjs):
    try:
        llm = mainwin.llm
        all_skills = mainwin.agent_skills
        all_tasks = mainwin.agent_tasks
        if kjs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in kjs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_skills if sk.getSkid() in skids]

        if kjs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in kjs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = kjs['id'],
            name=kjs['name'],
            description=kjs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("knowledge created:", agent_card.name, agent_card.url)
        # Use unified function to create browser_use LLM from mainwin configuration (no fallback)
        from agent.ec_skills.llm_utils.llm_utils import create_browser_use_llm
        browser_use_llm = create_browser_use_llm(mainwin=mainwin, skip_playwright_check=True)
        if not browser_use_llm:
            raise ValueError("Failed to create browser_use LLM from mainwin. Please configure LLM provider API key in Settings.")
        new_knowledge = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skills=agent_skills, tasks=agent_tasks)
        return new_knowledge
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewKnowledges:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewKnowledges: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def prep_knowledges_data_for_cloud(mainwin, knowledges):
    try:
        knjs = []
        for knowledge in knowledges:
            knj = {
                "knid": knowledge.card.id,
                "owner": mainwin.user,
                "name": knowledge.name,
                "description": knowledge.description,
                "path": knowledge.path,
                "status": knowledge.status,
                "metadata": json.dumps(knowledge.metadata),
                "rag": knowledge.rag
            }
            knjs.append(knj)

        return knjs
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        if traceback_info:
            ex_stat = "ErrorNewKnowledges:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewKnowledges: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return None



def remove_knowledges_from_cloud(mainwin, knowledges):
    try:
        api_removes=[{"id": item.id, "owner": "", "reason": ""} for item in knowledges]
        jresp = send_remove_knowledges_request_to_cloud(mainwin.session, api_removes, mainwin.get_auth_token(), mainwin.getWanApiEndpoint())

    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorRemoveKnowledges:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorRemoveKnowledges: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def add_tasks_to_agent(mainwin, agent_name, tasks):
    found_agent = next((ag for ag in mainwin.agents if agent_name.lower() in ag.card.name.lower()), None)
    if found_agent:
        if isinstance(tasks, list):
            found_agent.tasks.extend(tasks)
        else:
            found_agent.tasks.append(tasks)

    return found_agent
