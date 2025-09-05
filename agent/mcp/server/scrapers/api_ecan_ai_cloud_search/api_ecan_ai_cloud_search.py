
from typing import Dict, List, Tuple
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
import requests

def api_ecan_ai_cloud_search():
    try:
        url = "http://52.204.81.197:5808/search_components"
        payload = {
            "message": "Find an audio-PA for my bluetooth speaker",
            "thread_id": "component_001",
            "origin": "NYC",
            "destination": "LAX",
            "departure_date": "2025-09-01",
            "return_date": "2025-09-10",
            "travelers": 2,
            "hotel_stars": 4,
            "budget": "1500"
        }

        response = requests.post(url, json=payload)
        print(response.json())

    except Exception as e:
        err_trace = get_traceback(e, "ErrorEcanCloudSearch")
        logger.debug(err_trace)