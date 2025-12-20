
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
from agent.ec_skills.llm_utils.llm_utils import build_a2a_response_message


def send_data_to_agent(recipient_id, dtype, data, state) -> NodeState:
    try:
        agent_id = state["messages"][0]
        self_agent = get_agent_by_id(agent_id)
        recipient_agent = get_agent_by_id(recipient_id)

        print("[send_data_to_agent] send_response_back:", state)
        chat_id = state["messages"][1]
        msg_id = str(uuid.uuid4())
        llm_result = state["result"]["llm_result"]
        
        # Determine message type and data
        form = data if dtype == "form" else None
        notification = data if dtype == "notification" else None
        msg_type = dtype if dtype in ("form", "notification") else "text"

        # Use standardized message builder
        agent_response_message = build_a2a_response_message(
            agent_id=self_agent.card.id,
            chat_id=chat_id,
            msg_id=msg_id,
            task_id="",
            msg_text=llm_result,
            sender_name=self_agent.card.name,
            msg_type=msg_type,
            attachments=state.get("attachments", []),
            form=form,
            notification=notification,
        )
        print("sending response msg back to recipient:", agent_response_message)
        # Use non-blocking send to avoid deadlock
        send_result = self_agent.a2a_send_chat_message_async(recipient_agent, agent_response_message)
        return send_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSendResponseBack")
        logger.debug(err_trace)
        return err_trace



