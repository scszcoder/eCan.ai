from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from utils.logger_helper import logger_helper as logger

from agent.cloud_api.cloud_api import (
    send_query_components_request_to_cloud,
    send_get_nodes_prompts_request_to_cloud,
    send_query_fom_request_to_cloud,
    send_rank_results_request_to_cloud, send_start_long_llm_task_to_cloud
)
import json


def ecan_ai_api_query_components(mainwin, empty_components):
    filled_components = []
    try:
        session = mainwin.session
        token = mainwin.get_auth_token()

        network_api_engine = mainwin.getNetworkApiEngine()
        if network_api_engine == "lan":
            img_endpoint = mainwin.getLanApiEndpoint()
            logger.debug("img endpoint:", img_endpoint)
        else:
            img_endpoint = mainwin.getWanApiEndpoint()

        response = send_query_components_request_to_cloud(session, token, empty_components, img_endpoint)
        logger.debug("send_query_components_request_to_cloud: respnose:", response)

        # Check for errors in the response
        if "errors" in response or "body" not in response:
            logger.error(f"Error from cloud: {response.get('errors')}")
            return []

        body = json.loads(response["body"])
        if body.get("result") == "error":
            logger.error(f"Error from cloud lambda: {body.get('error')}")
            return []

        filled_components = body["data"]
        logger.debug("filled_components:", filled_components)

    except Exception as e:
        err_trace = get_traceback(e, "ErrorEcanAiApiQueryComponents")
        logger.error(err_trace)
    return filled_components


def ecan_ai_api_query_fom(mainwin, fom_query):
    filled_components = []
    try:
        session = mainwin.session
        token = mainwin.get_auth_token()

        network_api_engine = mainwin.getNetworkApiEngine()
        if network_api_engine == "lan":
            img_endpoint = mainwin.getLanApiEndpoint()
            logger.debug("img endpoint:", img_endpoint)
        else:
            img_endpoint = mainwin.getWanApiEndpoint()

        response = send_query_fom_request_to_cloud(session, token, fom_query, img_endpoint)
        logger.debug("send_query_fom_request_to_cloud: respnose:", response)

        # Check for errors in the response
        if "errors" in response or "body" not in response:
            logger.error(f"Error from cloud: {response.get('errors')}")
            return []

        body = json.loads(response["body"])
        if body.get("result") == "error":
            logger.error(f"Error from cloud lambda: {body.get('error')}")
            return []

        fom_info = body["data"]
        logger.debug("fom_info:", fom_info)

    except Exception as e:
        err_trace = get_traceback(e, "ErrorEcanAiApiQueryFOM")
        logger.error(err_trace)
        fom_info = {}

    return fom_info


#
# def ecan_ai_api_rerank_results(mainwin, rank_query):
#     filled_components = []
#     try:
#         session = mainwin.session
#         token = mainwin.get_auth_token()
#
#         network_api_engine = mainwin.getNetworkApiEngine()
#         if network_api_engine == "lan":
#             img_endpoint = mainwin.getLanApiEndpoint()
#             logger.debug("img endpoint:", img_endpoint)
#         else:
#             img_endpoint = mainwin.getWanApiEndpoint()
#
#         response = send_rank_results_request_to_cloud(session, token, rank_query, img_endpoint)
#         logger.debug("send_query_fom_request_to_cloud: respnose:", response)
#
#         # Check for errors in the response
#         if "errors" in response or "body" not in response:
#             logger.error(f"Error from cloud: {response.get('errors')}")
#             return []
#
#         body = json.loads(response["body"])
#         if body.get("result") == "error":
#             logger.error(f"Error from cloud lambda: {body.get('error')}")
#             return []
#
#         scores = body["data"]
#         logger.debug("score board:", scores)
#
#     except Exception as e:
#         err_trace = get_traceback(e, "ErrorEcanAiApiRerankResults")
#         logger.error(err_trace)
#         fom_info = {}
#
#     return scores


# since rerank take a long time, we have to use an async version, this
# request will return a task id (sort of a ticket number), and the result
# be pushed down from the cloud side when it is ready.
def ecan_ai_api_rerank_results(mainwin, rank_query):
    filled_components = []
    cloud_task_id = ""
    try:
        session = mainwin.session
        token = mainwin.get_auth_token()

        network_api_engine = mainwin.getNetworkApiEngine()
        if network_api_engine == "lan":
            img_endpoint = mainwin.getLanApiEndpoint()
            logger.debug("img endpoint:", img_endpoint)
        else:
            img_endpoint = mainwin.getWanApiEndpoint()

        rank_request = {
            "acct_site_id": mainwin.getAcctSiteID(),
            "agent_id": rank_query["agent_id"],
            "work_type": "rerank_search_results",
            "task_data": rank_query["setup"]
        }

        response = send_start_long_llm_task_to_cloud(session, token, rank_request, img_endpoint)
        logger.debug("send_start_long_llm_task_to_cloud::: respnose:", response)

        # Check for errors in the response
        if "errors" in response or "body" not in response:
            logger.error(f"Error from cloud: {response.get('errors')}")
            return []

        body = response["body"]
        if body.get("result") == "error":
            logger.error(f"Error from cloud lambda: {body.get('error')}")
            return []

        cloud_task_id = body["id"]
        logger.debug("cloud_task_id:", cloud_task_id)

    except Exception as e:
        err_trace = get_traceback(e, "ErrorEcanAiApiRerankResults")
        logger.error(err_trace)
        fom_info = {}

    return cloud_task_id


def api_ecan_ai_get_nodes_prompts(mainwin, nodes):
    try:
        session = mainwin.session
        token = mainwin.get_auth_token()

        wan_api_endpoint = mainwin.getWanApiEndpoint()
        logger.debug("wan api endpoint:", wan_api_endpoint)
        response = send_get_nodes_prompts_request_to_cloud(session, token, nodes, wan_api_endpoint)
        logger.debug("api_ecan_ai_get_nodes_prompts: respnose:", response)
        
        # 检查响应是否包含错误
        if "errors" in response:
            logger.debug("API returned errors:", response["errors"])
            return []
        
        # 检查响应格式
        if "body" not in response:
            logger.debug("Response missing 'body' field:", response)
            return []

        raw_body = response["body"]

        # First decode
        level1 = json.loads(raw_body)  # dict with keys: data
        level2 = json.loads(level1["data"]["body"])  # inner string -> dict
        prompts = level2["data"]  # [[[ "system", "..."], ["human", "..."]]]

        # prompts = json.loads(response["body"])["data"]
        usable_prompts = []
        for prompt in prompts:
            usable_prompts.append(
                [
                    {
                        "role": "system",
                        "content": prompt[0][1]
                    },
                    {
                        "role": "user",
                        "content": prompt[1][1]
                    }
                ]
            )
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEcanAiApiGetNodesPrompts")
        logger.error(err_trace)
        usable_prompts = []
    return usable_prompts


def api_ecan_ai_ocr_read_screen(mainwin, nodes):
    try:
        session = mainwin.session
        token = mainwin.get_auth_token()

        wan_api_endpoint = mainwin.getWanApiEndpoint()
        logger.debug("wan api endpoint:", wan_api_endpoint)
        response = send_get_nodes_prompts_request_to_cloud(session, token, nodes, wan_api_endpoint)
        logger.debug("api_ecan_ai_get_nodes_prompts: respnose:", response)

        # 检查响应是否包含错误
        if "errors" in response:
            logger.debug("API returned errors:", response["errors"])
            return []

        # 检查响应格式
        if "body" not in response:
            logger.debug("Response missing 'body' field:", response)
            return []

        raw_body = response["body"]

        # First decode
        level1 = json.loads(raw_body)  # dict with keys: data
        level2 = json.loads(level1["data"]["body"])  # inner string -> dict
        prompts = level2["data"]  # [[[ "system", "..."], ["human", "..."]]]

        # prompts = json.loads(response["body"])["data"]
        usable_prompts = []
        for prompt in prompts:
            usable_prompts.append(
                [
                    {
                        "role": "system",
                        "content": prompt[0][1]
                    },
                    {
                        "role": "user",
                        "content": prompt[1][1]
                    }
                ]
            )
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEcanAiApiGetNodesPrompts")
        logger.error(err_trace)
        usable_prompts = []
    return usable_prompts


def add_ecan_ai_api_get_agent_status_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ecan_ai_api_get_agent_status",
        description="Get an agent's current status, such as running tasks, scheduled tasks, finished tasks, chat interactions etc.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["agent_id"],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "agent id",
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def ecan_ai_api_get_agent_status(mainwin, config):
    try:
        agent_id = config.get("agent_id", "")
        status = {
            "agent_id": agent_id,
            "completed_tasks":[],
            "running_tasks":[],
            "unrun_tasks":[],
            "chat_interactions":[],
            "tool_calls": {}
        }
        if agent_id:
            # get various agent's running status.
            # 1) # of running task
            # 2) for each finished or running task for today, get
            #   2.1) task id
            #   2.2) task status
            #   2.3) task progress (percentage, which langgraph node is it on
            #   2.4) task start time, end time(duration)
            #   2.5) # of re-tries (retry reasons)
            # 3) for each unrun task, get
            #   3.1) task id
            #   3.2) task schedule
            # 4) # of chat interactions so far today (and with whom)
            # 5) # of tool calls so far today.

            logger.debug("api_ecan_ai_get_nodes_prompts: respnose:", status)
        else:
            status = "Error: Agent Not Found!"
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEcanAiApiGetAgentStatus")
        logger.error(err_trace)
        status = err_trace
    return status


