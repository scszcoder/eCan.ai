from agent.cloud_api.cloud_api import send_query_components_request_to_cloud



def ecan_ai_api_query_components(empty_components):
    filled_components = []
    filled_components = send_query_components_request_to_cloud(empty_components)
    return filled_components