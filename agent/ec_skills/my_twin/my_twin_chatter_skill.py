import traceback
import typing
from typing import TypedDict
import uuid
import time

from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
from agent.a2a.common.types import SendTaskRequest, TaskSendParams

from agent.ec_skill import *
from app_context import AppContext
from utils.logger_helper import logger_helper as logger
from agent.agent_service import get_agent_by_id
if typing.TYPE_CHECKING:
    from gui.MainGUI import MainWindow
from agent.ec_skills.llm_utils.llm_utils import find_opposite_agent, parse_a2a_message_params

# this is simply a parrot agent, no thinking, no intelligent, simply pipe human message to agent
# and pipe agent response back to human

def human_message(state):
    human_msg = state["attributes"].get("human", False)
    logger.debug(f"[my_twin_chatter_skill] human message? {human_msg}")
    return human_msg

def parrot(state: NodeState) -> NodeState:
    # this function simply routes the incoming chat message, if the chat message is for
    # human, then sends it to the GUI section, (update message DB)
    # if the chat message is for agent, then sends it to the recipient agent using A2A protocol (update message DB)
    logger.debug("[my_twin_chatter_skill] my twin parrot chatting...", state)
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = AppContext.get_main_window()
    
    # Log current LLM being used by the agent
    # IMPORTANT: For skill execution, agent.skill_llm is the LLM actually used
    if agent:
        # Determine which LLM is actually used for skill execution
        actual_llm = None
        actual_llm_type = None
        actual_llm_source = None
        
        # Skill execution uses skill_llm (primary for skills)
        if hasattr(agent, 'skill_llm') and agent.skill_llm:
            actual_llm = agent.skill_llm
            actual_llm_type = type(agent.skill_llm).__name__
            actual_llm_source = "skill_llm"
        # Fallback to agent.llm if skill_llm is not available
        elif hasattr(agent, 'llm') and agent.llm:
            actual_llm = agent.llm
            actual_llm_type = type(agent.llm).__name__
            actual_llm_source = "agent.llm (fallback)"
        
        # Also check main_window.llm via run_context (used by some skills)
        run_context_llm = None
        if mainwin and hasattr(mainwin, 'llm') and mainwin.llm:
            run_context_llm = mainwin.llm
            run_context_llm_type = type(mainwin.llm).__name__
        
        # Build comprehensive LLM info
        llm_info_parts = []
        
        if actual_llm:
            # Get provider info for the actual LLM
            provider_info = ""
            if mainwin and hasattr(mainwin, 'config_manager'):
                default_llm = mainwin.config_manager.general_settings.default_llm
                if default_llm:
                    provider = mainwin.config_manager.llm_manager.get_provider(default_llm)
                    if provider:
                        provider_display = provider.get('display_name', default_llm)
                        model_name = provider.get('default_model', 'unknown')
                        provider_info = f" | Provider: {provider_display} ({default_llm}), Model: {model_name}"
            
            llm_info_parts.append(f"✅ ACTUAL LLM (used by skill): {actual_llm_type} (source: {actual_llm_source}){provider_info}")
        
        # Show agent.llm info if different from actual
        if hasattr(agent, 'llm') and agent.llm and agent.llm is not actual_llm:
            agent_llm_type = type(agent.llm).__name__
            
            # Get detailed info for agent.llm (browser_use LLM)
            agent_llm_info = f"{agent_llm_type} (browser_use LLM, not used by skill)"
            
            # Try to extract model and provider info from agent.llm
            try:
                model_info = []
                
                # Extract model name
                if hasattr(agent.llm, 'model_name'):
                    model_info.append(f"model={agent.llm.model_name}")
                elif hasattr(agent.llm, 'model'):
                    model_info.append(f"model={agent.llm.model}")
                
                # Extract base_url or endpoint
                if hasattr(agent.llm, 'openai_api_base') and agent.llm.openai_api_base:
                    base_url = agent.llm.openai_api_base
                    model_info.append(f"endpoint={base_url}")
                elif hasattr(agent.llm, 'base_url') and agent.llm.base_url:
                    base_url = agent.llm.base_url
                    model_info.append(f"endpoint={base_url}")
                
                # Try to match provider from mainwin config
                if mainwin and hasattr(mainwin, 'config_manager') and model_info:
                    default_llm = mainwin.config_manager.general_settings.default_llm
                    if default_llm:
                        provider = mainwin.config_manager.llm_manager.get_provider(default_llm)
                        if provider:
                            provider_display = provider.get('display_name', default_llm)
                            model_info.append(f"provider={provider_display}")
                
                if model_info:
                    agent_llm_info = f"{agent_llm_type} ({', '.join(model_info)})"
            except Exception as e:
                logger.debug(f"[my_twin_chatter_skill] Error extracting agent.llm info: {e}")
            
            llm_info_parts.append(f"   Agent.llm (browser_use): {agent_llm_info}")
        
        # Show main_window.llm info if different
        if run_context_llm and run_context_llm is not actual_llm:
            llm_info_parts.append(f"   MainWindow.llm (run_context): {run_context_llm_type} (available via run_context)")
        
        if llm_info_parts:
            logger.info(f"[my_twin_chatter_skill] 📋 LLM Usage Info:\n" + "\n".join(llm_info_parts))
        else:
            logger.warning(f"[my_twin_chatter_skill] ⚠️ No LLM information available for agent")
    try:
        if human_message(state):
            # this is a human to agent chat message
            recipient_agent = find_opposite_agent(agent, state["messages"][1])

            if recipient_agent:
                logger.info("[my_twin_chatter_skill] parrot recipient found:", recipient_agent.card.name)
            else:
                logger.error("[my_twin_chatter_skill] parrot recipient agent not found!")
            # Use non-blocking send: A sends to B and returns immediately
            # B will send response back to A via a2a_send_chat_message_async
            # A's parrot skill will receive the response and display to GUI
            result = agent.a2a_send_chat_message_async(recipient_agent, state)
            logger.info("[my_twin_chatter_skill] message forwarded to recipient (non-blocking)")
        else:
            # Send this message to GUI
            logger.debug("[my_twin_chatter_skill] parrot showing agent msg", state)
            params = state["attributes"]["params"]
            
            # Use unified parser for consistent message format handling
            parsed = parse_a2a_message_params(params)
            logger.debug("[my_twin_chatter_skill] parsed params:", parsed)
            
            dtype = parsed["dtype"]
            card = parsed["card"]
            code = parsed["code"]
            form = parsed["form"]
            i_tag = parsed["i_tag"]
            notification = parsed["notification"]
            raw_role = parsed["role"]
            senderId = parsed["senderId"]
            createAt = parsed["createAt"]
            senderName = parsed["senderName"]
            status = parsed["status"]
            ext = parsed["ext"]

            # Determine final role to use in frontend payload
            role = raw_role or "agent"
            if notification:
                role = "system"
            else:
                twin_agent_id = getattr(agent.card, "id", None) if agent and getattr(agent, "card", None) else None
                if role == "user" or not role:
                    if senderId and twin_agent_id and senderId != twin_agent_id:
                        role = "agent"
                    elif role == "user":
                        role = "user"
                    else:
                        role = "agent"

            senderId = senderId or getattr(agent.card, "id", "")
            createAt = createAt or int(time.time() * 1000)
            senderName = senderName or getattr(agent.card, "name", "")

            frontend_message = {
                "content": {
                    "type": dtype,
                    "text": state["messages"][-1],
                    "card": card,
                    "code": code,
                    "form": form,
                    "i_tag": i_tag,
                    "notification": notification,
                },
                "role": role,
                "senderId": senderId,
                "createAt": createAt,
                "senderName": senderName,
                "status": status or "success",
                "ext": ext or {},
            }
            logger.debug("[my_twin_chatter_skill] parrot supposed chat id:", state["messages"][1])
            logger.debug("[my_twin_chatter_skill] parrot pushing frontend message", frontend_message)

            if not notification:
                mainwin.db_chat_service.push_message_to_chat(state["messages"][1], frontend_message)
            else:
                logger.debug("pushing notification...", frontend_message)
                mainwin.db_chat_service.push_notification_to_chat(state["messages"][1], frontend_message)
        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateMyTwinChatterSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateMyTwinChatterSkill: traceback information not available:" + str(e)
        logger.error(ex_stat)
        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

    return result_state

# only 2 possible types of message to this skill
# serialized IPCRequest
# {
#     "id": "3739721e-8205-4174-abb7-bd1223bea161",
#     "type": "request",
#     "method": "send_chat",
#     "params": {
#         "chatId": "chat-804150",
#         "senderId": "4864a82d505d4c89b965d848ea832c56",
#         "role": "user",
#         "content": "f",
#         "createAt": "1759801807448",
#         "senderName": "My Twin Agent",
#         "status": "complete",
#         "attachments": [],
#         "i_tag": "",
#         "token": "df9bf922126d4b0d94f96e230c583bd7",
#         "human": True
#     },
#     "timestamp": 1759801807469
# }
#  or
# class TaskSendParams(BaseModel):
#     id: str
#     sessionId: str = Field(default_factory=lambda: uuid4().hex)
#     message: Message
#     acceptedOutputModes: Optional[List[str]] = None
#     pushNotification: PushNotificationConfig | None = None
#     historyLength: int | None = None
#     metadata: dict[str, Any] | None = None
#
TWIN_CHATTER_MAPPING_RULES = [
          {
            "from": ["event.data.params", "event.data.params.metadata.params"],
            "to": [
              {"target": "state.attributes.params"}
            ],
            "on_conflict": "overwrite"
          },
          {
            "from": ["event.data.method", "event.data.params.metadata.method"],
            "to": [
              {"target": "state.attributes.method"}
            ],
            "on_conflict": "overwrite"
          }
    ]

async def create_my_twin_chatter_skill(mainwin: 'MainWindow'):
    try:
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        chatter_skill = EC_Skill(name="chatter for my digital twin",
                             description="chat on behalf of human.")
        chatter_skill.mapping_rules["developing"]["mappings"] = TWIN_CHATTER_MAPPING_RULES
        chatter_skill.mapping_rules["released"]["mappings"] = TWIN_CHATTER_MAPPING_RULES
        # await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")

        workflow = StateGraph(NodeState, WorkFlowContext)
        workflow.add_node("relay", parrot)
        workflow.set_entry_point("relay")
        workflow.add_edge("relay", END)

        chatter_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        chatter_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        logger.info("[my_twin_chatter_skill] my_twin_chatter_skill build is done!")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateMyTwinChatterSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateMyTwinChatterSkill: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return None

    return chatter_skill


def build_skill(run_context: dict | None = None, mainwin=None) -> EC_Skill:
    """
    Standard entry point for skill building system.
    
    ⚠️ IMPORTANT: This function is currently NOT actively used!
    
    Current Loading Method:
    -----------------------
    This skill is loaded via build_agent_skills_parallel() which directly calls:
        await create_my_twin_chatter_skill(mainwin)
    
    When Would This Be Used:
    ------------------------
    This build_skill() function would only be called if:
    1. This skill file is moved to ec_skills/ as an external/plugin skill
    2. It's NOT hardcoded in build_agent_skills_parallel()
    3. The system uses build_agent_skills_from_files() for dynamic loading
    
    Why Keep It:
    ------------
    - Future plugin architecture support
    - Backward compatibility
    - Standard interface for all code-based skills
    
    See: agent/ec_skills/skill_build_template.py for detailed documentation
    """
    from agent.ec_skills.skill_build_template import sync_to_async_bridge
    return sync_to_async_bridge(create_my_twin_chatter_skill, mainwin, run_context)
