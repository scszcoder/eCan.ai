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
from agent.ec_skills.llm_utils.llm_utils import find_opposite_agent

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
    try:
        if human_message(state):
            # this is a human to agent chat message
            recipient_agent = find_opposite_agent(agent, state["messages"][1])

            if recipient_agent:
                logger.info("[my_twin_chatter_skill] parrot recipient found:", recipient_agent.card.name)
            else:
                logger.error("[my_twin_chatter_skill] parrot recipient agent not found!")
            # result = await agent.a2a_send_chat_message(recipient_agent, {"chat": state["messages"][-1]})
            result = agent.a2a_send_chat_message(recipient_agent, state)
        else:
            # sendd this message to GUI
            logger.debug("[my_twin_chatter_skill] parrot showing agent msg", state)
            params = state["attributes"]["params"]
            if isinstance(params, TaskSendParams):
                payload_params = params.metadata.get("params", {}) if params.metadata else {}
                content_meta = payload_params.get("content", {}) if isinstance(payload_params, dict) else {}

                dtype = content_meta.get("dtype", "text")
                card = content_meta.get("card", "")
                code = content_meta.get("code", "")
                form = content_meta.get("form", "")
                i_tag = content_meta.get("i_tag", "")
                notification = content_meta.get("notification", "")

                raw_role = payload_params.get("role") if isinstance(payload_params, dict) else None
                if not raw_role and params.message:
                    raw_role = params.message.role

                senderId = payload_params.get("senderId") if isinstance(payload_params, dict) else None
                createAt = payload_params.get("createAt") if isinstance(payload_params, dict) else None
                senderName = payload_params.get("senderName") if isinstance(payload_params, dict) else None
                status = payload_params.get("status") if isinstance(payload_params, dict) else None
                ext = payload_params.get("ext") if isinstance(payload_params, dict) else None
            else:
                logger.warning("strange... shold we be here???")
                dtype = params["metadata"]["dtype"]
                card = params["metadata"]["card"]
                code = params["metadata"]["code"]
                form = params["metadata"]["form"]
                i_tag = params["metadata"]["i_tag"]
                notification = params["metadata"]["notification"]
                raw_role = params.get("role")
                senderId = params["senderId"]
                createAt = params["createAt"]
                senderName = params["senderName"]
                status = params["status"]
                ext = params["ext"]

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
