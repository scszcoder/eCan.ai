
import traceback
import socket

from utils.logger_helper import logger_helper as logger

def get_lan_ip():
    try:
        # Connect to an external address, but don't actually send anything
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Google's DNS IP
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"  # fallback

def get_a2a_server_url(mainwin):
    """
    Get A2A server URL with port allocation.
    Always returns a valid URL with format: http://host:port
    
    Returns:
        str: Valid URL with allocated port, or fallback URL if allocation fails
    """
    try:
        host = get_lan_ip()
        free_ports = mainwin.get_free_agent_ports(1)
        logger.debug("getting a2a server ports:", host, free_ports)
        
        if not free_ports:
            # No free ports available, use default port
            logger.warning("No free ports available, using default port 3600")
            return f"http://{host}:3600"
        
        a2a_server_port = free_ports[0]
        url = f"http://{host}:{a2a_server_port}"
        logger.debug("a2a server url:", url)
        return url

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGetA2AServerURL:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorGetA2AServerURL: traceback information not available:" + str(e)
        logger.error(ex_stat)
        
        # Always return a valid fallback URL
        fallback_url = "http://127.0.0.1:3600"
        logger.warning(f"Returning fallback URL: {fallback_url}")
        return fallback_url


from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from agent.ec_skill import *


def send_data_to_agent(recipient_id, dtype, data, state) -> NodeState:
    try:
        agent_id = state["messages"][0]
        # _ensure_context(runtime.context)
        self_agent = get_agent_by_id(agent_id)
        recipient_agent = get_agent_by_id(recipient_id)
        mainwin = self_agent.mainwin
        twin_agent = next((ag for ag in mainwin.agents if "twin" in ag.card.name.lower()), None)

        print("standard_post_llm_hook send_response_back:", state)
        chat_id = state["messages"][1]
        msg_id = str(uuid.uuid4()),
        # send self a message to trigger the real component search work-flow
        if dtype == "form":
            card = {}
            code = {}
            form = data
            gp_data = {}
            notification = {}
        elif dtype == "notification":
            card = {}
            code = {}
            form = {}
            notification = data
            gp_data = {}
        else:
            card = {}
            code = {}
            form = {}
            notification = {}
            gp_data = data

        agent_response_message = {
            "id": str(uuid.uuid4()),
            "chat": {
                "input": state["result"]["llm_result"],
                "attachments": [],
                "messages": [self_agent.card.id, chat_id, msg_id, "", state["result"]["llm_result"]],
            },
            "params": {
                "content": state["result"]["llm_result"],
                "attachments": state["attachments"],
                "metadata": {
                    "msg_type": "send_task", # "text", "code", "form", "notification", "card
                    "data_type": dtype,
                    "card": card,
                    "code": code,
                    "form": form,
                    "notification": notification,
                    "general_purpose": gp_data
                },
                "role": "",
                "senderId": f"{agent_id}",
                "createAt": int(time.time() * 1000),
                "senderName": f"{self_agent.card.name}",
                "status": "success",
                "ext": "",
                "human": False
            }
        }
        print("sending response msg back to twin:", agent_response_message)
        send_result = self_agent.a2a_send_chat_message(recipient_agent, agent_response_message)
        # state.result = result
        return send_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSendResponseBack")
        logger.debug(err_trace)
        return err_trace



