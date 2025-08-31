from utils.logger_helper import get_agent_by_id, get_traceback
from utils.logger_helper import logger_helper as logger

from agent.cloud_api.cloud_api import send_query_components_request_to_cloud, send_get_nodes_prompts_request_to_cloud
import json


def ecan_ai_api_query_components(mainwin, empty_components):
    filled_components = []
    try:
        session = mainwin.session
        token = mainwin.get_auth_token()

        img_engine = mainwin.getImageEngine()
        if img_engine == "lan":
            img_endpoint = mainwin.getLanImageEndpoint()
            logger.debug("img endpoint:", img_endpoint)
        else:
            img_endpoint = mainwin.getWanImageEndpoint()

        response = send_query_components_request_to_cloud(session, token, empty_components, img_endpoint)
        logger.debug("send_query_components_request_to_cloud: respnose:", response)
        filled_components = json.loads(response["body"])["data"]
        logger.debug("filled_components:", filled_components)

    except Exception as e:
        err_trace = get_traceback(e, "ErrorEcanAiApiQueryComponents")
        logger.error(err_trace)
    return filled_components

def api_ecan_ai_get_nodes_prompts(mainwin, nodes):
    try:
        session = mainwin.session
        token = mainwin.get_auth_token()

        wan_api_endpoint = mainwin.wan_api_endpoint
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

        wan_api_endpoint = mainwin.wan_api_endpoint
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