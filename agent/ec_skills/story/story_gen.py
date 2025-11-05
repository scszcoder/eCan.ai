import re
import time
import random

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback

def start_soap():
    try:
        logger.debug("start_soap....")
    except Exception as e:
        err_msg = get_traceback(e, "ErrorStartSoap")
        logger.error(f"{err_msg}")

def req_scene():
    try:
        logger.debug("req_scene....")
    except Exception as e:
        err_msg = get_traceback(e, "ErrorReqScene")
        logger.error(f"{err_msg}")



# related to websocket sub/push to get long running task results
def subscribe_cloud_show(acctSiteID: str, id_token: str, ws_url: Optional[str] = None) -> Tuple[websocket.WebSocketApp, threading.Thread]:
    from agent.agent_service import get_agent_by_id
    """Subscribe to ever running soap opera.

    Parameters:
        acctSiteID: Account/site identifier used by the subscription filter.
        id_token: Cognito/AppSync ID token (Authorization header).
        ws_url: Optional AppSync GraphQL endpoint; if https, auto-converted to realtime wss.
    """

    def on_message(ws, message):
        logger.debug("[CloudShow] Received WebSocket message")
        try:
            data = json.loads(message)
        except Exception:
            data = {"raw": message}
        logger.debug("[CloudShow] Subscription update: %s", json.dumps(data, indent=2))
        # Determine message type for protocol handling
        msg_type = data.get("type")

        if msg_type == "connection_ack":
            # After ack, start the subscription (AppSync format: data + extensions.authorization)
            try:
                # Match updated schema: requires acctSiteID variable
                subscription = (
                    """
                    subscription OnSceneReady($acctSiteID: String!) {
                      onSceneComplete(acctSiteID: $acctSiteID) {
                        id
                        acctSiteID
                        scene_id: ID!
                        agent_ids: [String]!
                        video: [String]!
                        description: String
                        dialogs: [AWSJSON]!
                        actions: [AWSJSON]!
                        timestamp
                      }
                    }
                    """
                )
                data_obj = {
                    "query": subscription,
                    "operationName": "OnSceneReady",
                    "variables": {"acctSiteID": acctSiteID},
                }
                start_payload = {
                    "id": "scene1",
                    "type": "start",
                    "payload": {
                        "data": json.dumps(data_obj),
                        "extensions": {
                            "authorization": {
                                "host": api_host,
                                "Authorization": id_token,
                            }
                        },
                    },
                }
                logger.info("[CloudShow] connection_ack received, sending start subscription", start_payload)
                ws.send(json.dumps(start_payload))
            except Exception as e:
                logger.error(f"[CloudShow] Failed to send start payload: {e}")

        elif msg_type in ("ka", "keepalive"):
            # Keep-alive from server; no action required
            return
        elif msg_type == "data" and isinstance(data.get("payload"), dict) and data.get("id") == "LongLLM1":
            # Extract structured object result per schema
            payload_data = data.get("payload", {}).get("data", {})
            result_obj = None
            if isinstance(payload_data, dict):
                result_obj = payload_data.get("onLongLLMTaskComplete")
                logger.debug(f"Received long LLM Task subscription result:{json.dumps(result_obj, indent=2, ensure_ascii=False)}")
                # now we can send result_obj to resume the pending workflow.
                # which msg queue should this be put into? (agent should maintain some kind of cloud_task_id to agent_task_queue LUT)
                agent_id = result_obj["agentID"]
                work_type = result_obj["workType"]
                handler_agent = get_agent_by_id(agent_id)
                # Convert cloud result to TaskSendParams format for _build_resume_payload()
                converted_result = convert_cloud_result_to_task_send_params(result_obj, work_type)
                # event_response = handler_agent.runner.sync_task_wait_in_line(work_type, converted_result)
                event_response = handler_agent.runner.sync_task_wait_in_line(work_type, converted_result, source="cloud_websocket")

    def on_error(ws, error):
        logger.error(f"[CloudShow] WebSocket error: {error}")

    def on_close(ws, status_code, msg):
        logger.warning(f"[CloudShow] WebSocket closed: code={status_code}, msg={msg}")

    def on_open(ws):
        logger_helper.debug("[CloudShow] web socket opened.......")
        init_payload = {
            "type": "connection_init",
            "payload": {}
        }
        try:
            logger_helper.debug("[CloudShow] sending connection_init ...")
            ws.send(json.dumps(init_payload))
        except Exception as e:
            logger.error(f"[CloudShow] Failed to send connection_init: {e}")

    # Resolve WS URL and ensure it's the AppSync realtime endpoint
    if not ws_url:
        ws_url = os.getenv("ECAN_WS_URL", "")
    if not ws_url:
        logger_helper.warning(
            "Warning: WebSocket URL not provided and ECAN_WS_URL is not set. Cloud LLM subscription will be disabled.")
        raise ValueError("WebSocket URL not provided and ECAN_WS_URL is not set")

    if ws_url.startswith("https://") and "appsync-api" in ws_url:
        try:
            prefix = "https://"
            rest = ws_url[len(prefix):]
            rest = rest.replace("appsync-api", "appsync-realtime-api", 1)
            ws_url = "wss://" + rest
            logger_helper.info(f"Converted to realtime endpoint: {ws_url}")
        except Exception:
            pass

    parsed = urlparse(ws_url)
    api_host = parsed.netloc.replace("appsync-realtime-api", "appsync-api")
    header_obj = {
        "host": api_host,
        "Authorization": id_token,
    }
    payload_obj = {}
    header_b64 = base64.b64encode(json.dumps(header_obj).encode("utf-8")).decode("utf-8")
    payload_b64 = base64.b64encode(json.dumps(payload_obj).encode("utf-8")).decode("utf-8")

    query = dict(parse_qsl(parsed.query))
    query.update({
        "header": header_b64,
        "payload": payload_b64,
    })
    signed_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        urlencode(query),
        parsed.fragment,
    ))

    logger.debug("[CloudShow] ws_url ok")
    headers = []

    logger.debug("[CloudShow] token seems to be ok")

    ws = websocket.WebSocketApp(
        signed_url,
        header=headers,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open,
        subprotocols=["graphql-ws"],
    )

    logger.info("[CloudShow] Launching web socket thread")
    # Configure SSL options to handle certificate verification issues
    import ssl
    ssl_context = ssl.create_default_context()
    # For development/testing, you might want to disable certificate verification
    # ssl_context.check_hostname = False
    # ssl_context.verify_mode = ssl.CERT_NONE

    t = threading.Thread(target=lambda: ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}), daemon=True)
    t.start()
    logger.info("[CloudShow] Web socket thread launched")
    return ws, t
