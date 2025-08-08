from utils.logger_helper import get_agent_by_id, get_traceback
from utils.logger_helper import logger_helper as logger

from agent.cloud_api.cloud_api import send_query_components_request_to_cloud, send_get_nodes_prompts_request_to_cloud
import json


def ecan_ai_api_query_components(mainwin, empty_components):
    filled_components = []
    try:
        session = mainwin.session
        token = mainwin.tokens['AuthenticationResult']['IdToken']

        img_engine = mainwin.getImageEngine()
        if img_engine == "lan":
            img_endpoint = mainwin.getLanImageEndpoint()
            print("img endpoint:", img_endpoint)
        else:
            img_endpoint = mainwin.getWanImageEndpoint()

        response = send_query_components_request_to_cloud(session, token, empty_components, img_endpoint)
        print("send_query_components_request_to_cloud: respnose:", response)

    except Exception as e:
        err_trace = get_traceback(e, "ErrorEcanAiApiQueryComponents")
        logger.debug(err_trace)
    return filled_components

def api_ecan_ai_get_nodes_prompts(mainwin, nodes):
    try:
        session = mainwin.session
        token = mainwin.tokens['AuthenticationResult']['IdToken']

        wan_api_endpoint = mainwin.wan_api_endpoint
        print("wan api endpoint:", wan_api_endpoint)
        response = send_get_nodes_prompts_request_to_cloud(session, token, nodes, wan_api_endpoint)
        print("api_ecan_ai_get_nodes_prompts: respnose:", response)
        prompts = json.loads(response["body"])["data"]
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
        logger.debug(err_trace)
        usable_prompts = []
    return usable_prompts