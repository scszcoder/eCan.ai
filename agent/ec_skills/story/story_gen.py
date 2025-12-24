import re
import time
import random
import json
import os
import base64
import threading
import websocket
from typing import Optional, Tuple, Dict, Any, Callable
from urllib.parse import urlparse, urlencode, urlunparse, parse_qsl

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback

# Scene style options
SCENE_STYLES = ["ANIME", "REALISTIC", "CARTOON", "PIXEL_ART", "MINIMALIST"]

# Output format options
OUTPUT_FORMATS = ["WEBM", "GIF", "MP4", "ANIMATED_PNG"]

# Scene status
SCENE_STATUS = ["PENDING", "GENERATING", "COMPLETED", "FAILED"]


def get_mainwin():
    """Get MainWindow instance for accessing session and auth."""
    try:
        from app_context import AppContext
        return AppContext.get_main_window()
    except Exception:
        return None


def start_soap(
    agent_ids: list[str],
    theme: str = None,
    mood: str = None,
    settings: dict = None
) -> dict:
    """
    Start a continuous soap opera (story generation) for the specified agents.
    
    Args:
        agent_ids: List of agent IDs to participate in the soap opera
        theme: Optional theme for the story (e.g., "office drama", "adventure")
        mood: Optional mood setting (e.g., "comedic", "dramatic", "romantic")
        settings: Optional additional settings dict
        
    Returns:
        dict with soap_id, status, message or error info
    """
    try:
        logger.info(f"[StoryGen] Starting soap opera for agents: {agent_ids}")
        
        mainwin = get_mainwin()
        if not mainwin:
            logger.error("[StoryGen] MainWindow not available")
            return {"errorType": "NotInitialized", "message": "MainWindow not available"}
        
        from agent.cloud_api.cloud_api import send_start_soap_to_cloud
        
        # Build the soap input
        soap_input = {
            "acctSiteID": mainwin.user,  # Use user email as acctSiteID
            "agent_ids": agent_ids,
            "theme": theme,
            "mood": mood,
            "settings": settings
        }
        
        response = send_start_soap_to_cloud(
            mainwin.session,
            soap_input,
            mainwin.get_auth_token(),
            mainwin.getWanApiEndpoint()
        )
        
        logger.info(f"[StoryGen] start_soap response: {response}")
        return response
        
    except Exception as e:
        err_msg = get_traceback(e, "ErrorStartSoap")
        logger.error(f"{err_msg}")
        return {"errorType": "Exception", "message": str(e)}


def stop_soap(soap_id: str) -> bool:
    """
    Stop a running soap opera.
    
    Args:
        soap_id: The soap opera ID to stop
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"[StoryGen] Stopping soap opera: {soap_id}")
        
        mainwin = get_mainwin()
        if not mainwin:
            logger.error("[StoryGen] MainWindow not available")
            return False
        
        from agent.cloud_api.cloud_api import send_stop_soap_to_cloud
        
        result = send_stop_soap_to_cloud(
            mainwin.session,
            soap_id,
            mainwin.get_auth_token(),
            mainwin.getWanApiEndpoint()
        )
        
        logger.info(f"[StoryGen] stop_soap result: {result}")
        return result
        
    except Exception as e:
        err_msg = get_traceback(e, "ErrorStopSoap")
        logger.error(f"{err_msg}")
        return False


def req_scene(
    agent_id: str,
    emotion: str = None,
    mind_state: str = None,
    description: str = None,
    style: str = "ANIME",
    output_format: str = "WEBM",
    duration_hint_ms: int = None,
    context: dict = None
) -> dict:
    """
    Request generation of a scene/video based on agent's emotion or mind state.
    
    This is an async operation - the function returns immediately with a request_id.
    The actual generated scene will be delivered via the onSceneComplete subscription.
    
    Args:
        agent_id: The agent ID for which to generate the scene
        emotion: Agent's emotion (e.g., "happy", "sad", "excited", "thinking", "confused")
        mind_state: Agent's mental state description (free-form text)
        description: Free-form description of the desired scene
        style: Visual style - one of ANIME, REALISTIC, CARTOON, PIXEL_ART, MINIMALIST
        output_format: Output format - one of WEBM, GIF, MP4, ANIMATED_PNG
        duration_hint_ms: Suggested duration in milliseconds
        context: Additional context dict (e.g., conversation history)
        
    Returns:
        dict with request_id, status, message, estimated_time_ms or error info
    """
    try:
        logger.info(f"[StoryGen] Requesting scene for agent {agent_id}, emotion={emotion}, mind_state={mind_state}")
        
        # Validate style
        if style not in SCENE_STYLES:
            logger.warning(f"[StoryGen] Invalid style '{style}', defaulting to ANIME")
            style = "ANIME"
        
        # Validate output format
        if output_format not in OUTPUT_FORMATS:
            logger.warning(f"[StoryGen] Invalid output_format '{output_format}', defaulting to WEBM")
            output_format = "WEBM"
        
        mainwin = get_mainwin()
        if not mainwin:
            logger.error("[StoryGen] MainWindow not available")
            return {"errorType": "NotInitialized", "message": "MainWindow not available"}
        
        from agent.cloud_api.cloud_api import send_req_scene_to_cloud
        
        # Build the scene input
        scene_input = {
            "acctSiteID": mainwin.user,  # Use user email as acctSiteID
            "agent_id": agent_id,
            "emotion": emotion,
            "mind_state": mind_state,
            "description": description,
            "style": style,
            "output_format": output_format,
            "duration_hint_ms": duration_hint_ms,
            "context": context
        }
        
        response = send_req_scene_to_cloud(
            mainwin.session,
            scene_input,
            mainwin.get_auth_token(),
            mainwin.getWanApiEndpoint()
        )
        
        logger.info(f"[StoryGen] req_scene response: {response}")
        return response
        
    except Exception as e:
        err_msg = get_traceback(e, "ErrorReqScene")
        logger.error(f"{err_msg}")
        return {"errorType": "Exception", "message": str(e)}


def get_scene(scene_id: str) -> dict:
    """
    Get a scene by ID from the cloud.
    
    Args:
        scene_id: The scene ID to retrieve
        
    Returns:
        Scene object or error info
    """
    try:
        logger.debug(f"[StoryGen] Getting scene: {scene_id}")
        
        mainwin = get_mainwin()
        if not mainwin:
            logger.error("[StoryGen] MainWindow not available")
            return {"errorType": "NotInitialized", "message": "MainWindow not available"}
        
        from agent.cloud_api.cloud_api import send_get_scene_to_cloud
        
        response = send_get_scene_to_cloud(
            mainwin.session,
            scene_id,
            mainwin.get_auth_token(),
            mainwin.getWanApiEndpoint()
        )
        
        return response
        
    except Exception as e:
        err_msg = get_traceback(e, "ErrorGetScene")
        logger.error(f"{err_msg}")
        return {"errorType": "Exception", "message": str(e)}


def query_scenes(
    agent_id: str = None,
    label: str = None,
    emotion: str = None,
    status: str = None,
    limit: int = 20,
    next_token: str = None
) -> dict:
    """
    Query scenes with filters.
    
    Args:
        agent_id: Filter by agent ID
        label: Filter by scene label
        emotion: Filter by emotion
        status: Filter by status (PENDING, GENERATING, COMPLETED, FAILED)
        limit: Max results to return (default 20)
        next_token: Pagination token for next page
        
    Returns:
        dict with items list and nextToken, or error info
    """
    try:
        logger.debug(f"[StoryGen] Querying scenes: agent_id={agent_id}, label={label}")
        
        mainwin = get_mainwin()
        if not mainwin:
            logger.error("[StoryGen] MainWindow not available")
            return {"errorType": "NotInitialized", "message": "MainWindow not available"}
        
        from agent.cloud_api.cloud_api import send_query_scenes_to_cloud
        
        query_input = {
            "acctSiteID": mainwin.user,
            "agent_id": agent_id,
            "label": label,
            "emotion": emotion,
            "status": status,
            "limit": limit,
            "nextToken": next_token
        }
        
        response = send_query_scenes_to_cloud(
            mainwin.session,
            query_input,
            mainwin.get_auth_token(),
            mainwin.getWanApiEndpoint()
        )
        
        return response
        
    except Exception as e:
        err_msg = get_traceback(e, "ErrorQueryScenes")
        logger.error(f"{err_msg}")
        return {"errorType": "Exception", "message": str(e)}


# Callback registry for scene completion events
_scene_complete_callbacks: Dict[str, Callable[[dict], None]] = {}


def register_scene_callback(request_id: str, callback: Callable[[dict], None]):
    """
    Register a callback to be invoked when a scene generation completes.
    
    Args:
        request_id: The request_id returned by req_scene
        callback: Function to call with the scene result
    """
    _scene_complete_callbacks[request_id] = callback
    logger.debug(f"[StoryGen] Registered callback for request_id: {request_id}")


def unregister_scene_callback(request_id: str):
    """Unregister a scene completion callback."""
    if request_id in _scene_complete_callbacks:
        del _scene_complete_callbacks[request_id]
        logger.debug(f"[StoryGen] Unregistered callback for request_id: {request_id}")


def _handle_scene_complete(scene_result: dict):
    """
    Internal handler for scene completion events from subscription.
    Dispatches to registered callbacks and updates frontend.
    """
    try:
        request_id = scene_result.get("request_id")
        agent_ids = scene_result.get("agent_ids", [])
        video_urls = scene_result.get("video", [])
        status = scene_result.get("status")
        
        logger.info(f"[StoryGen] Scene complete: request_id={request_id}, status={status}")
        
        # Invoke registered callback if any
        if request_id and request_id in _scene_complete_callbacks:
            try:
                callback = _scene_complete_callbacks[request_id]
                callback(scene_result)
            except Exception as cb_err:
                logger.error(f"[StoryGen] Callback error: {cb_err}")
            finally:
                # Clean up callback after invocation
                unregister_scene_callback(request_id)
        
        # If scene completed successfully, update frontend with the new scene
        if status == "COMPLETED" and video_urls and agent_ids:
            from agent.ec_skills.story.scene_utils import update_scene
            
            for agent_id in agent_ids:
                # Build scene data for frontend
                scenes = [{
                    "label": scene_result.get("emotion", "generated"),
                    "clip": video_urls[0] if video_urls else "",
                    "n_repeat": 1,
                    "priority": 4,  # HIGH priority for generated scenes
                    "captions": [scene_result.get("description", "")]
                }]
                
                update_scene(
                    agent_id=agent_id,
                    scenes=scenes,
                    play_label=scene_result.get("emotion", "generated")
                )
                logger.info(f"[StoryGen] Updated frontend scene for agent {agent_id}")
                
    except Exception as e:
        err_msg = get_traceback(e, "ErrorHandleSceneComplete")
        logger.error(f"{err_msg}")



# related to websocket sub/push to get scene generation results
def subscribe_cloud_show(acctSiteID: str, id_token: str, ws_url: Optional[str] = None) -> Tuple[websocket.WebSocketApp, threading.Thread]:
    """Subscribe to scene generation completion events (soap opera / cloud show).

    Parameters:
        acctSiteID: Account/site identifier used by the subscription filter.
        id_token: Cognito/AppSync ID token (Authorization header).
        ws_url: Optional AppSync GraphQL endpoint; if https, auto-converted to realtime wss.
        
    Returns:
        Tuple of (WebSocketApp, Thread) for the subscription connection.
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
                # Updated subscription matching the new schema
                subscription = """
                    subscription OnSceneReady($acctSiteID: String!) {
                      onSceneComplete(acctSiteID: $acctSiteID) {
                        id
                        acctSiteID
                        request_id
                        scene_id
                        agent_ids
                        video
                        thumbnail
                        description
                        emotion
                        mind_state
                        dialogs
                        actions
                        duration_ms
                        timestamp
                        status
                        error
                      }
                    }
                """
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
                logger.info("[CloudShow] connection_ack received, sending start subscription")
                ws.send(json.dumps(start_payload))
            except Exception as e:
                logger.error(f"[CloudShow] Failed to send start payload: {e}")

        elif msg_type in ("ka", "keepalive"):
            # Keep-alive from server; no action required
            return
            
        elif msg_type == "data" and isinstance(data.get("payload"), dict) and data.get("id") == "scene1":
            # Handle scene completion event
            payload_data = data.get("payload", {}).get("data", {})
            if isinstance(payload_data, dict):
                scene_result = payload_data.get("onSceneComplete")
                if scene_result:
                    logger.info(f"[CloudShow] Received scene completion: {json.dumps(scene_result, indent=2, ensure_ascii=False)}")
                    # Dispatch to the scene completion handler
                    try:
                        _handle_scene_complete(scene_result)
                    except Exception as handler_err:
                        logger.error(f"[CloudShow] Error handling scene complete: {handler_err}")

    def on_error(ws, error):
        logger.error(f"[CloudShow] WebSocket error: {error}")

    def on_close(ws, status_code, msg):
        logger.warning(f"[CloudShow] WebSocket closed: code={status_code}, msg={msg}")

    def on_open(ws):
        logger.debug("[CloudShow] WebSocket opened")
        init_payload = {
            "type": "connection_init",
            "payload": {}
        }
        try:
            logger.debug("[CloudShow] Sending connection_init...")
            ws.send(json.dumps(init_payload))
        except Exception as e:
            logger.error(f"[CloudShow] Failed to send connection_init: {e}")

    # Resolve WS URL and ensure it's the AppSync realtime endpoint
    if not ws_url:
        ws_url = os.getenv("ECAN_WS_URL", "")
    if not ws_url:
        logger.warning(
            "[CloudShow] WebSocket URL not provided and ECAN_WS_URL is not set. Subscription will be disabled.")
        raise ValueError("WebSocket URL not provided and ECAN_WS_URL is not set")

    if ws_url.startswith("https://") and "appsync-api" in ws_url:
        try:
            prefix = "https://"
            rest = ws_url[len(prefix):]
            rest = rest.replace("appsync-api", "appsync-realtime-api", 1)
            ws_url = "wss://" + rest
            logger.info(f"[CloudShow] Converted to realtime endpoint: {ws_url}")
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
