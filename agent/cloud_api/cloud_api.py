import json
import os
import base64
import requests
import asyncio
import time
from config.envi import getECBotDataHome
from utils.logger_helper import logger_helper as logger
from utils.app_env import is_cn
import traceback
from config.constants import API_DEV_MODE
from aiolimiter import AsyncLimiter
import websocket
from websocket import WebSocketException
import threading
from urllib.parse import urlparse, urlencode, urlunparse, parse_qsl
from typing import Optional, Tuple, Any
from utils.logger_helper import logger_helper
from agent.cloud_api.constants import cloud_api, DataType, Operation
import aiohttp
# Import new generic GraphQL builder
from agent.cloud_api.graphql_builder import build_mutation

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from datetime import datetime

limiter = AsyncLimiter(1, 1)  # Max 5 requests per second

ecb_data_homepath = getECBotDataHome()

_LONG_LLM_TASK_WAITERS: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Future]] = {}
_LONG_LLM_TASK_WAITERS_LOCK = threading.Lock()

# Thread tracking for AppSync WebSocket subscriptions (memory leak fix)
# All WebSocket threads are tracked here for cleanup on shutdown
_appsync_ws_threads: list[threading.Thread] = []
_appsync_ws_threads_lock = threading.Lock()


def _track_appsync_ws_thread(t: threading.Thread) -> threading.Thread:
    """Track a WebSocket thread for cleanup."""
    with _appsync_ws_threads_lock:
        _appsync_ws_threads.append(t)
        logger.debug(f"[cloud_api] Tracking AppSync WS thread: {t.name} (total: {len(_appsync_ws_threads)})")
    return t


def get_appsync_ws_thread_count() -> int:
    """Get the count of tracked AppSync WebSocket threads."""
    with _appsync_ws_threads_lock:
        alive = [t for t in _appsync_ws_threads if t.is_alive()]
        # Prune dead threads
        if len(alive) < len(_appsync_ws_threads):
            _appsync_ws_threads[:] = alive
        return len(alive)


def cleanup_appsync_ws_threads(timeout: float = 5.0) -> int:
    """Clean up all tracked AppSync WebSocket threads.
    
    Args:
        timeout: Seconds to wait for each thread to finish
        
    Returns:
        Number of threads successfully cleaned up
    """
    cleaned = 0
    with _appsync_ws_threads_lock:
        threads_to_join = list(_appsync_ws_threads)
        _appsync_ws_threads.clear()
    
    for t in threads_to_join:
        try:
            t.join(timeout=timeout)
            if not t.is_alive():
                cleaned += 1
                logger.debug(f"[cloud_api] Cleaned up AppSync WS thread: {t.name}")
            else:
                logger.warning(f"[cloud_api] AppSync WS thread did not stop: {t.name}")
        except Exception as e:
            logger.warning(f"[cloud_api] Error joining thread {t.name}: {e}")
    
    logger.info(f"[cloud_api] AppSync WS threads cleanup done: {cleaned}/{len(threads_to_join)} joined")
    return cleaned


def register_long_llm_task_waiter(task_id: str, loop: asyncio.AbstractEventLoop, future: asyncio.Future) -> None:
    with _LONG_LLM_TASK_WAITERS_LOCK:
        _LONG_LLM_TASK_WAITERS[task_id] = (loop, future)


def cancel_long_llm_task_waiter(task_id: str) -> None:
    with _LONG_LLM_TASK_WAITERS_LOCK:
        _LONG_LLM_TASK_WAITERS.pop(task_id, None)


def try_resolve_long_llm_task_waiter(result_obj: dict) -> bool:
    try:
        task_id = (result_obj or {}).get("taskID")
        if not task_id:
            return False
        with _LONG_LLM_TASK_WAITERS_LOCK:
            entry = _LONG_LLM_TASK_WAITERS.pop(task_id, None)
        if not entry:
            return False

        loop, future = entry
        if future.cancelled() or future.done():
            return True

        def _set_result() -> None:
            try:
                if not future.cancelled() and not future.done():
                    future.set_result(result_obj)
            except Exception:
                # Avoid crashing the subscription thread.
                logger.error("[CloudLLMTask] Failed to resolve waiter", exc_info=True)

        loop.call_soon_threadsafe(_set_result)
        return True
    except Exception:
        logger.error("[CloudLLMTask] try_resolve_long_llm_task_waiter unexpected error", exc_info=True)
        return False

# ==========================================================
_APPSYNC_ENDPOINT_LOGGED = False

# ==========================================================

def is_cn_app() -> bool:
    """Check if running CN version. Delegates to utils.app_env."""
    return is_cn()


def get_tcb_api_url() -> str:
    """Get TCB GraphQL HTTP endpoint URL (CN only).
    
    Delegates to CloudEndpointConfig. Kept for backward compatibility.
    """
    from agent.cloud_api.endpoints import get_endpoint_config
    cfg = get_endpoint_config()
    return cfg.graphql_endpoint


def get_appsync_endpoint() -> str:
    """Get the active cloud GraphQL endpoint URL (CN/Intl unified).
    
    Delegates to CloudEndpointConfig which reads APPSYNC.GRAPHQL_ENDPOINT
    from the current app's auth_config.yml. No hardcoded fallbacks.
    """
    from agent.cloud_api.endpoints import get_endpoint_config
    global _APPSYNC_ENDPOINT_LOGGED
    cfg = get_endpoint_config()
    endpoint = cfg.graphql_endpoint
    if not _APPSYNC_ENDPOINT_LOGGED:
        logger_helper.info(f"[CloudAPI] Using GraphQL endpoint: {endpoint}")
        _APPSYNC_ENDPOINT_LOGGED = True
    return endpoint


# resp is the response from requesting the presigned_url
def send_file_with_presigned_url(src_file, resp):
    # Upload file to S3 using presigned URL
    # Calculate dynamic timeout based on file size
    file_size = os.path.getsize(src_file)
    timeout = _calculate_upload_timeout(file_size)
    file_size_mb = file_size / (1024 * 1024)
    logger_helper.info(f"[S3Upload] Uploading {os.path.basename(src_file)}: {file_size_mb:.2f} MB, timeout: {timeout}s")
    
    with open(src_file, 'rb') as f:
        files = {'file': f}
        r = requests.post(resp['url'], data=resp['fields'], files=files, timeout=timeout)
    # r = requests.post(resp['body'][0], files=files)
    logger_helper.debug(str(r.status_code))


def _calculate_upload_timeout(file_size_bytes, min_speed_kbps=50):
    """
    Calculate dynamic timeout based on file size and minimum acceptable speed.
    
    Args:
        file_size_bytes: File size in bytes
        min_speed_kbps: Minimum acceptable upload speed in KB/s (default: 50 KB/s)
    
    Returns:
        Timeout in seconds (minimum 30s, maximum 600s)
    """
    # Calculate base timeout: file_size / min_speed
    base_timeout = file_size_bytes / (min_speed_kbps * 1024)
    
    # Add 20% buffer for network fluctuations
    timeout_with_buffer = base_timeout * 1.2
    
    # Clamp between 30s and 600s (10 minutes)
    return max(30, min(600, int(timeout_with_buffer)))


# Upload file to S3 using PUT presigned URL (for avatar uploads)
def upload_file_to_presigned_url(file_path, presigned_url, content_type=None):
    """
    Upload a file to S3 using a PUT presigned URL.
    
    Args:
        file_path: Local path to the file to upload
        presigned_url: The presigned PUT URL from the server
        content_type: Optional content type. If None, tries without Content-Type first,
                      then with auto-detected Content-Type as fallback.
    
    Returns:
        dict with success status and any error message
    """
    if not file_path or not presigned_url:
        return {"success": False, "error": "Missing file_path or presigned_url"}
    
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}
    
    try:
        # Get file size for dynamic timeout calculation
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)
        
        # Calculate dynamic timeout based on file size
        timeout = _calculate_upload_timeout(file_size)
        logger.info(f"[S3Upload] File: {os.path.basename(file_path)}, Size: {file_size_mb:.2f} MB, Timeout: {timeout}s")
        
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # Strategy: Try multiple approaches since presigned URL may or may not include Content-Type
        # 1. If content_type provided, try with that first
        # 2. Try without Content-Type header (for presigned URLs generated without it)
        # 3. Try with auto-detected Content-Type as fallback
        
        attempts = []
        
        if content_type:
            # Try with provided content_type first
            attempts.append(('provided', {'Content-Type': content_type}))
        
        # Try without Content-Type (presigned URL may not have included it in signature)
        attempts.append(('no-content-type', {}))
        
        # Auto-detect content type for fallback
        ext = os.path.splitext(file_path)[1].lower()
        content_types_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
        }
        auto_content_type = content_types_map.get(ext, 'application/octet-stream')
        
        if not content_type or content_type != auto_content_type:
            attempts.append(('auto-detected', {'Content-Type': auto_content_type}))
        
        # Retry logic: up to 3 attempts with exponential backoff
        max_retries = 3
        last_error = None
        
        for retry in range(max_retries):
            for attempt_name, headers in attempts:
                try:
                    if retry > 0:
                        logger.info(f"[S3Upload] Retry {retry}/{max_retries-1} for {attempt_name}")
                    else:
                        logger.debug(f"[S3Upload] Trying upload with {attempt_name}: headers={headers}")
                    
                    response = requests.put(presigned_url, data=file_data, headers=headers, timeout=timeout)
                    
                    if response.status_code in [200, 204]:
                        logger.info(f"✅ Successfully uploaded {file_path} to S3 (attempt: {attempt_name}, retry: {retry})")
                        return {"success": True}
                    else:
                        last_error = f"{response.status_code} - {response.text[:200]}"
                        logger.debug(f"[S3Upload] Attempt {attempt_name} failed: {response.status_code}")
                        
                except requests.Timeout:
                    last_error = f"Timeout after {timeout}s (file: {file_size_mb:.2f} MB)"
                    if retry < max_retries - 1:
                        wait_time = 2 ** retry  # 1s, 2s, 4s
                        logger.warning(f"⏱️  Upload timeout, retrying in {wait_time}s... (attempt: {attempt_name})")
                        import time
                        time.sleep(wait_time)
                        break  # Break inner loop to retry all attempts
                    else:
                        logger.error(f"❌ Upload timeout after {max_retries} retries")
                        
                except Exception as e:
                    last_error = str(e)
                    logger.error(f"❌ Upload error: {e}")
                    if retry == max_retries - 1:
                        break
            else:
                # Inner loop completed without break (all attempts failed)
                if retry < max_retries - 1:
                    wait_time = 2 ** retry
                    logger.warning(f"All content-type attempts failed, retrying in {wait_time}s...")
                    import time
                    time.sleep(wait_time)
                continue
            break  # Break outer loop if inner loop was broken (timeout occurred)
        
        # All retries exhausted
        logger.error(f"❌ Failed to upload {file_path} after {max_retries} retries: {last_error}")
        return {"success": False, "error": f"Upload failed after {max_retries} retries: {last_error}"}
        
    except Exception as e:
        logger.error(f"❌ Exception uploading {file_path}: {e}")
        return {"success": False, "error": str(e)}


# resp is the response from requesting the presigned_url
def get_file_with_presigned_url(dest_file, url):
    # Download file to S3 using presigned URL with dynamic timeout
    # First get headers to determine file size
    try:
        head_response = requests.head(url, timeout=10)
        content_length = head_response.headers.get('Content-Length')
        if content_length:
            file_size = int(content_length)
            timeout = _calculate_upload_timeout(file_size, min_speed_kbps=100)  # Assume faster download
            file_size_mb = file_size / (1024 * 1024)
            logger_helper.info(f"[S3Download] File size: {file_size_mb:.2f} MB, timeout: {timeout}s")
        else:
            timeout = 300  # Default 5 minutes
            logger_helper.info(f"[S3Download] File size unknown, using default timeout: {timeout}s")
    except:
        timeout = 300  # Default if HEAD request fails
        logger_helper.debug(f"[S3Download] Could not determine file size, using default timeout: {timeout}s")
    
    # Download file with calculated timeout
    http_response = requests.get(url, stream=True, timeout=timeout)
    print("DL presigned:", http_response)
    if http_response.status_code == 200:
        dest_dir = os.path.dirname(dest_file)

        # Check if the directory exists, and if not, create it
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)

        with open(dest_file, 'wb') as f:
            # http_response.raw.decode_content = True
            # shutil.copyfileobj(http_response.raw, f)

            f.write(http_response.content)

            f.close()


def gen_query_reg_steps_string(query):
    logger_helper.debug("in query:" + json.dumps(query))
    query_string = """
        query MyQuery {
      regSteps (inSteps:[
    """
    rec_string = ""
    for i in range(len(query)):
        # rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ type: \"" + query[i]["type"] + "\", "
        rec_string = rec_string + "data: \"" + query[i]["data"] + "\", "
        rec_string = rec_string + "start_time: \"" + query[i]["start_time"] + "\", "
        rec_string = rec_string + "end_time: \"" + query[i]["end_time"] + "\", "
        rec_string = rec_string + "result: \"" + str(query[i]["result"]) + "\" }"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
    ]) 
    }"""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_query_chat_request_string(query):
    logger_helper.debug("in query:" + json.dumps(query))
    query_string = """
        query MyQuery {
      queryChats (msgs:[
    """
    rec_string = ""
    for i in range(len(query)):
        # rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ msgID: \"" + query[i]["msgID"] + "\", "
        rec_string = rec_string + "user: \"" + query[i]["user"] + "\", "
        rec_string = rec_string + "timeStamp: \"" + query[i]["timeStamp"] + "\", "
        rec_string = rec_string + "products: \"" + query[i]["products"] + "\", "
        rec_string = rec_string + "goals: \"" + query[i]["goals"] + "\", "
        rec_string = rec_string + "options: \"" + query[i]["options"] + "\", "
        rec_string = rec_string + "background: \"" + query[i]["background"] + "\", "
        rec_string = rec_string + "msg: \"" + query[i]["msg"] + "\" }"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
    ]) 
    }"""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_file_op_request_string(query):
    logger_helper.debug("in query:" + json.dumps(query))
    if not query:
        return "query MyQuery { reqFileOp (fo:[]) }"
    parts = []
    for item in query:
        parts.append(
            f'{{ op: "{item["op"]}", '
            f'names: "{item["names"]}", '
            f'options: "{item["options"]}" }}'
        )
    query_string = (
        "query MyQuery {\n"
        "      reqFileOp (fo:[\n"
        + ",\n".join(parts) +
        "\n    ])\n"
        "    }"
    )
    logger_helper.debug(query_string)
    return query_string



def gen_account_info_request_string(query):
    logger_helper.debug("in query:" + json.dumps(query))
    if not query:
        return "query MyQuery { reqAccountInfo (ops:[]) }"
    parts = []
    for item in query:
        parts.append(
            f'{{ actid: "{item["actid"]}", '
            f'op: {json.dumps(item["op"])}, '
            f'options: "{item["options"]}" }}'
        )
    query_string = (
        "query MyQuery {\n"
        "      reqAccountInfo (ops:[\n"
        + ",\n".join(parts) +
        "\n    ])\n"
        "    }"
    )
    logger_helper.debug(query_string)
    return query_string


# graphQL schema:
# type Query {
#   reqScreenRead(inScrn: [ScreenImg]!): [ScreenInfo]
#   genSchedules(bots: [String]!, settings: SchSettings): [Schedule]
# input ScreenImg {
#   mid: Int
#   os: String
#   app: String
#   domain: String
#   page: String
#   skill: String
#   lastMove: String
#   mode: String
#   imageFile: String
# }
def gen_screen_read_request_string(query):
    logger_helper.debug("in query:" + json.dumps(query))
    if not query:
        return "query MyQuery { reqScreenTxtRead (inScrn:[]) }"
    parts = []
    for item in query:
        parts.append(
            f'{{ mid: {str(int(item["mid"]))}, '
            f'bid: {str(int(item["bid"]))}, '
            f'os: "{item["os"]}", '
            f'app: "{item["app"]}", '
            f'domain: "{item["domain"]}", '
            f'page: "{item["page"]}", '
            f'layout: "{item["layout"]}", '
            f'skill: "{item["skill"]}", '
            f'psk: "{item["psk"]}", '
            f'csk: "{item["csk"]}", '
            f'lastMove: "{item["lastMove"]}", '
            f'options: "{item["options"]}", '
            f'theme: "{item["theme"]}", '
            f'imageFile: "{item["imageFile"]}", '
            f'factor:  "{str(item["factor"])}" }}'
        )
    query_string = (
        "query MyQuery {\n"
        "      reqScreenTxtRead (inScrn:[\n"
        + ",\n".join(parts) +
        "\n    ])\n"
        "    }"
    )
    logger_helper.debug(query_string)
    return query_string


def gen_obtain_review_request_string(query):
    logger_helper.debug("in query:" + json.dumps(query))
    query_string = """
            query MyQuery {
          getFB (fb_reqs:[
        """
    rec_string = ""
    for i in range(len(query)):
        # rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ number: 1, "
        rec_string = rec_string + "product: \"" + query[i]["product"] + "\", "
        rec_string = rec_string + "orderID: \"\", "
        rec_string = rec_string + "payType: \"\", "
        rec_string = rec_string + "total: 0, "
        rec_string = rec_string + "transactionID: \"\", "
        rec_string = rec_string + "customerMail: \"songc@yahoo.com\", "
        rec_string = rec_string + "customerPhone: \"\", "
        rec_string = rec_string + "instructions: \"" + query[i]["instructions"] + "\", "
        rec_string = rec_string + "origin:  \"ecbot app\"" + " }"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ])
        }"""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string



def gen_report_vehicles_string(vehicles):
    """Generate GraphQL mutation string for reporting vehicles.
    
    Now uses updateVehicles API instead of deprecated reportVehicles.
    Maps old field names to new VehicleUpdateInput schema.
    """
    query_string = """
        mutation MyMutation {
      updateVehicles (input:[
    """
    rec_string = ""
    for i in range(len(vehicles)):
        v = vehicles[i]
        # Use vname as the vehicle ID (unique identifier)
        vname = v.get("vname", "")
        
        rec_string += "{ "
        rec_string += f'id: "{vname}"'
        rec_string += f', name: "{vname}"'
        rec_string += f', status: "{v.get("status", "")}"'
        rec_string += f', architecture: "{v.get("hardware", "")}"'
        rec_string += f', platform: "{v.get("software", "")}"'
        rec_string += f', ip_address: "{v.get("ip", "")}"'
        
        # Store additional fields in extra_metadata as JSON
        extra_metadata = {
            "owner": v.get("owner", ""),
            "lastseen": v.get("lastseen", ""),
            "functions": v.get("functions", ""),
            "agent_ids": v.get("agent_ids", ""),
            "vid": v.get("vid", 0),
            "created_at": v.get("created_at", "")
        }
        extra_json = json.dumps(extra_metadata, ensure_ascii=False).replace('"', '\\"')
        rec_string += f', extra_metadata: "{extra_json}"'
        
        # Store functions/capabilities
        if v.get("functions"):
            caps = {"functions": v.get("functions", "")}
            caps_json = json.dumps(caps, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', capabilities: "{caps_json}"'
        
        rec_string += " }"

        if i != len(vehicles) - 1:
            rec_string += ', '
        else:
            rec_string += ']'

    tail_string = """
        ) { id success error }
        } """
    query_string = query_string + rec_string + tail_string

    logger_helper.debug(query_string)
    return query_string


def gen_dequeue_tasks_string(vehicles):
    vnames = ",".join([v["vname"] for v in vehicles])

    query_string = """
        mutation MyMutation {
      dequeueTasks (input:[
    """
    rec_string = ""
    rec_string = rec_string + "{ "
    rec_string = rec_string + "vehicles: \"" + vnames + "\" }"

    rec_string = rec_string + ']'

    tail_string = """
        ) 
        } """
    query_string = query_string + rec_string + tail_string

    logger_helper.debug(query_string)
    return query_string




def gen_query_manager_missions_string(query):
    query_string = """
        query MyQuery {
      getManagerMissions (qm:
    """
    # rec_string = json.dumps({"a": "b"}).replace('"', '\"')
    rec_string = "\"{ \\\"byowneruser\\\": true}\""

    tail_string = """
        )
        }"""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_schedule_request_string(test_name, schedule_settings):
    if test_name == "":
        qvs = None
        query_string = "query MySchQuery { genSchedules(settings: \"{ \\\"testmode\\\": false, \\\"test_name\\\": \\\"" + test_name + "\\\", \\\"forceful\\\": " + schedule_settings.get(
            "forceful", "false") + ", \\\"skillPreferences\\\": " + schedule_settings.get("skillPreferences",
                                                                                          "{\\\"no_preference\\\":false, \\\"use_in_browser_skill\\\":true}") + ", \\\"tz\\\": \\\"" + schedule_settings.get(
            "tz", "America/Los_Angeles") + "\\\"}\") } "
    else:
        serialized_settings = json.dumps(schedule_settings)
        escaped_settings = serialized_settings.replace('"', '\"')

        query_string = '''
        query MySchQuery {
            genSchedules(settings: "%s")
        }
        ''' % serialized_settings.replace('"', '\\"')  # Escaping quotes

    logger_helper.debug(query_string)
    return query_string




def gen_update_vehicles_string(vehicles):
    query_string = """
        mutation MyMutation {
      updateVehicles (input:[
    """
    rec_string = ""
    for i in range(len(vehicles)):
        rec_string = rec_string + "{ vid: " + str(int(vehicles[i]["vid"])) + ", "
        rec_string = rec_string + "vname: \"" + vehicles[i]["vname"] + "\", "
        rec_string = rec_string + "owner: \"" + vehicles[i]["owner"] + "\", "
        rec_string = rec_string + "status: \"" + vehicles[i]["status"] + "\", "
        rec_string = rec_string + "lastseen: \"" + vehicles[i]["lastseen"] + "\", "
        rec_string = rec_string + "functions: \"" + vehicles[i]["functions"] + "\", "
        rec_string = rec_string + "bids: \"" + vehicles[i]["agent_ids"] + "\", "
        rec_string = rec_string + "hardware: \"" + vehicles[i]["hardware"] + "\", "
        rec_string = rec_string + "software: \"" + vehicles[i]["software"] + "\", "
        rec_string = rec_string + "ip: \"" + vehicles[i]["ip"] + "\", "
        rec_string = rec_string + "created_at: \"" + vehicles[i]["created_at"] + "\" }"

        if i != len(vehicles) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
        ) 
        } """
    query_string = query_string + rec_string + tail_string

    logger_helper.debug(query_string)
    return query_string



def gen_feedback_request_string(fbReq):
    query_string = """
            mutation MyUBMutation {
          getFB (input:[
        """
    rec_string = ""
    for i in range(len(fbReq)):
        rec_string = rec_string + "{ mid: " + str(fbReq[i]["mid"]) + ", "
        rec_string = rec_string + "bid: '" + str(fbReq[i]["bid"]) + "', "
        rec_string = rec_string + "status: \"" + fbReq[i]["status"] + "\", "
        rec_string = rec_string + "starttime: \"" + fbReq[i]["starttime"] + "\", "
        rec_string = rec_string + "endtime: \"" + fbReq[i]["endtime"] + "\"} "

        if i != len(fbReq) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
        ) 
        } """
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_rag_store_request_string(ragReqs):
    query_string = """
            mutation MyRAGMutation {
          reqRAGStore (input:[
        """
    rec_string = ""
    for i in range(len(ragReqs)):
        rec_string = rec_string + "{ fid: " + str(ragReqs[i]["fid"]) + ", "
        rec_string = rec_string + "pid: " + str(ragReqs[i]["pid"]) + ", "
        rec_string = rec_string + "file: \"" + ragReqs[i]["file"] + "\", "
        rec_string = rec_string + "type: \"" + ragReqs[i]["type"] + "\", "
        rec_string = rec_string + "format: \"" + ragReqs[i]["format"] + "\", "
        rec_string = rec_string + "options: \"" + ragReqs[i]["options"] + "\", "
        rec_string = rec_string + "version: \"" + ragReqs[i]["version"] + "\"} "

        if i != len(ragReqs) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
        ) 
        } """
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_wan_send_chat_message_string():
    send_msg_mutation = """
        mutation sendWanMessage($input: WanChatMessageInput!) {
          sendWanMessage(input: $input) {
            id
            chatID
            sender
            receiver
            type
            contents
            parameters
            timestamp
          }
        }
        """

    return send_msg_mutation


def gen_wan_subscription_connection_string():
    sub_conn_string = """
        subscription onMessageReceived($chatID: String!) {
          onMessageReceived(chatID: $chatID) {
            id
            chatID
            sender
            receiver
            type
            contents
            parameters
            timestamp
          }
        }
        """

    return sub_conn_string


def set_up_cloud():
    this_session = requests.Session()
    return this_session


async def set_up_cloud8():
    REGION = 'us-east-1'
    this_session = None
    # session = requests.Session()

    async with aiohttp.ClientSession() as session:
        this_session = session
    return this_session


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_schedule_request_to_cloud(session, token, ts_name, schedule_settings, endpoint):
    mutation = gen_schedule_request_string(ts_name, schedule_settings)

    jresp = appsync_http_request2(mutation, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        print("cloud schedule error:", jresp)
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["genSchedules"])
        # no logging, the data could be large.
        # logger_helper.debug("reponse:"+json.dumps(jresponse))

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def req_cloud_read_screen(session, request, token, endpoint):
    query = gen_screen_read_request_string(request)

    jresp = appsync_http_request(query, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqScreenTxtRead"])

    return jresponse


async def req_cloud_read_screen8(session, request, token, endpoint):
    query = gen_screen_read_request_string(request)

    jresp = await appsync_http_request8(query, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqScreenTxtRead"])

    return jresponse


def req_cloud_obtain_review(session, request, token, endpoint):
    query = gen_obtain_review_request_string(request)

    jresp = appsync_http_request(query, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        print("JRESP:", jresp)
        logger_helper.debug("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["errorInfo"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getFB"])

    return jresponse


def req_cloud_obtain_review_w_aipkey(session, request, apikey, endpoint):
    query = gen_obtain_review_request_string(request)

    jresp = appsync_http_request_w_apikey(query, session, apikey, endpoint)

    if "errors" in jresp:
        screen_error = True
        print("JRESP:", jresp)
        logger_helper.debug("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["errorInfo"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getFB"])

    return jresponse



def send_update_vehicles_request_to_cloud(session, vehicles, token, endpoint):
    mutationInfo = gen_update_vehicles_string(vehicles)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateVehicles"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_make_order_request_to_cloud(session, orders, token, endpoint):
    mutationInfo = gen_make_order_string(orders)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addBots"])

    return jresponse



def send_report_vehicles_to_cloud(session, token, vehicles, endpoint):
    """Report vehicle status to cloud using updateVehicles API.
    
    Note: Previously used deprecated reportVehicles API, now uses updateVehicles.
    Includes upsert logic: if updateVehicles returns NOT_FOUND for any vehicle,
    auto-registers them via addVehicles and retries the update.
    """
    queryInfo = gen_report_vehicles_string(vehicles)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    if "errors" in jresp:
        screen_error = True
        print("JRESP:", jresp)
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        # updateVehicles returns [VehicleMutationResult!]! not AWSJSON
        jresponse = jresp.get("data", {}).get("updateVehicles", [])

        # Upsert: auto-register vehicles that returned NOT_FOUND, then retry update
        not_found_ids = set()
        if isinstance(jresponse, list):
            for item in jresponse:
                if isinstance(item, dict) and not item.get("success"):
                    err = item.get("error", "")
                    if "NOT_FOUND" in err:
                        not_found_ids.add(item.get("id", ""))

        if not_found_ids:
            # Build addVehicles input from the original report data
            vehicles_to_add = []
            for v in vehicles:
                vname = v.get("vname", "")
                if vname in not_found_ids:
                    vehicles_to_add.append({
                        "id": vname,
                        "name": vname,
                        "status": v.get("status", ""),
                        "ip_address": v.get("ip", ""),
                        "platform": v.get("software", ""),
                        "architecture": v.get("hardware", ""),
                    })

            if vehicles_to_add:
                logger_helper.info(
                    f"[CloudVehicle] Auto-registering {len(vehicles_to_add)} vehicle(s) "
                    f"not found in cloud: {[v['id'] for v in vehicles_to_add]}"
                )
                add_mutation = gen_add_vehicles_string(vehicles_to_add)
                add_resp = appsync_http_request(add_mutation, session, token, endpoint)
                if "errors" in add_resp:
                    logger_helper.warning(
                        f"[CloudVehicle] addVehicles failed: {add_resp['errors']}"
                    )
                else:
                    add_results = add_resp.get("data", {}).get("addVehicles", [])
                    logger_helper.info(f"[CloudVehicle] addVehicles result: {add_results}")

                    # Retry the original update now that vehicles exist
                    jresp2 = appsync_http_request(queryInfo, session, token, endpoint)
                    if "errors" not in jresp2:
                        jresponse = jresp2.get("data", {}).get("updateVehicles", [])

    return jresponse


def send_dequeue_tasks_to_cloud(session, token, vehicles, endpoint):
    queryInfo = gen_dequeue_tasks_string(vehicles)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        print("JRESP:", jresp)
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["dequeueTasks"])

    return jresponse



def send_query_chat_request_to_cloud(session, token, chat_request, endpoint):
    queryInfo = gen_query_chat_request_string(chat_request)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryChats"])

    return jresponse


async def send_query_chat_request_to_cloud8(session, token, chat_request, endpoint):
    queryInfo = gen_query_chat_request_string(chat_request)

    jresp = await appsync_http_request8(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryChats"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_file_op_request_to_cloud(session, fops, token, endpoint):
    queryInfo = gen_file_op_request_string(fops)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqFileOp"])

    return jresponse


def _appsync_http_request_with_fresh_token_backoff(
    query_string,
    session,
    token,
    endpoint,
    *,
    max_attempts=3,
    sleep_seconds=15.0,
    operation_name="",
):
    """Wrap ``appsync_http_request`` with cache-lag retry.

    CloudBase's SCF gateway takes 30-60s to propagate a freshly minted
    JWT to its auth cache, so a 401 right after login is almost always
    cache lag rather than a real auth failure. SessionSupervisor already
    suppresses ``on_session_expired`` for the grace window, and
    OfflineSyncManager already backs the offline queue off for the same
    reason, but synchronous startup calls (``queryAgents``, ``reqAccountInfo``)
    don't go through either — without help, the user would briefly see
    an empty agent list and an "account info unavailable" warning.

    This wrapper detects "401 + supervisor.fresh" and retries up to
    ``max_attempts`` times with ``sleep_seconds`` between attempts. The
    retry budget is bounded so it can't block a caller forever; if the
    cache really hasn't caught up, the last 401 falls through unchanged.

    Default timing (3 attempts × 15s sleep ≈ 30s total) was chosen to
    span the lower bound of CloudBase's documented 30-60s cache-lag
    window. Earlier settings (3 × 5s ≈ 10s) were too short — verified
    empirically on 2026-08-15 that the cache lag routinely exceeds
    10s, leaving queryAgents + reqAccountInfo to fall through with
    "Bearer token required" on cold starts.
    """
    last_resp = None
    for attempt in range(1, max_attempts + 1):
        resp = appsync_http_request(query_string, session, token, endpoint)
        last_resp = resp
        if not _is_unauthenticated_error(resp):
            return resp
        if attempt >= max_attempts:
            break
        if not _supervisor_says_fresh_token():
            # 401 with stale token — real auth failure, do not retry.
            break
        logger_helper.info(
            f"[AppSync] {operation_name or 'request'} hit 401 but "
            f"SessionSupervisor marks the token fresh (cache lag). "
            f"Retrying in {sleep_seconds:.0f}s "
            f"(attempt {attempt}/{max_attempts - 1})."
        )
        time.sleep(sleep_seconds)
    return last_resp


def _is_unauthenticated_error(jresp):
    """True if the AppSync response is a 401 'Invalid or expired access token'."""
    if not isinstance(jresp, dict) or "errors" not in jresp:
        return False
    for err in jresp.get("errors") or []:
        if not isinstance(err, dict):
            continue
        msg = str(err.get("message", ""))
        ext = err.get("extensions") or {}
        if "Invalid or expired access token" in msg or ext.get("code") == "UNAUTHENTICATED":
            return True
    return False


def _supervisor_says_fresh_token():
    """True iff a SessionSupervisor is wired AND its token is fresh."""
    try:
        from auth.session_supervisor import get_session_supervisor
        supervisor = get_session_supervisor()
    except Exception:
        return False
    if supervisor is None:
        return False
    return bool(supervisor.is_fresh_token_rejection())


def send_account_info_request_to_cloud(session, acct_ops, token, endpoint):
    queryInfo = gen_account_info_request_string(acct_ops)

    jresp = _appsync_http_request_with_fresh_token_backoff(
        queryInfo, session, token, endpoint,
        operation_name="reqAccountInfo",
    )

    logger_helper.debug("account info response:" + json.dumps(jresp)[:500])
    if "errors" in jresp:
        error_obj = jresp["errors"][0]
        error_type = error_obj.get("errorType", error_obj.get("type", "Unknown"))
        error_msg = error_obj.get("message", str(error_obj))
        if _is_token_expired_error_message(error_msg):
            logger_helper.warning(f"🔑 reqAccountInfo token expired: {error_msg}")
            logger_helper.debug(f"📋 Full error response: {json.dumps(jresp, ensure_ascii=False)}")
        else:
            logger_helper.error(f"ERROR Type: {error_type} ERROR Info: {error_msg}")
        jresponse = {"errorType": error_type, "message": error_msg}
    else:
        jresponse = json.loads(jresp["data"]["reqAccountInfo"])

    return jresponse


def req_api_key(session, token, endpoint, customer='guest'):
    """Request a new API key from cloud via reqApiKey mutation.

    Args:
        session: requests.Session
        token: Cognito auth token
        endpoint: AppSync endpoint URL
        customer: customer identifier (default 'guest')

    Returns:
        dict with apiKey, apiKeyId, message on success, or error dict
    """
    query = f'''mutation {{
        reqApiKey(input: {{customer: "{customer}"}}) {{
            apiKey
            apiKeyId
            message
        }}
    }}'''
    jresp = appsync_http_request(query, session, token, endpoint)
    logger_helper.debug(f"reqApiKey response: {json.dumps(jresp)}")
    if "errors" in jresp:
        error_obj = jresp["errors"][0]
        error_type = error_obj.get("errorType", error_obj.get("type", "Unknown"))
        error_msg = error_obj.get("message", str(error_obj))
        logger_helper.error(f"[reqApiKey] ERROR Type: {error_type} Info: {error_msg}")
        return {"errorType": error_type, "message": error_msg}
    data = jresp.get("data", {}).get("reqApiKey", {})
    return data


def remove_api_key(session, token, endpoint, masked_keys):
    """Remove API key(s) via removeApiKey mutation.

    Args:
        session: requests.Session
        token: Cognito auth token
        endpoint: AppSync endpoint URL
        masked_keys: list of masked key strings (first6 + '*' + last6)

    Returns:
        parsed response dict or error dict
    """
    keys_str = ', '.join(f'"{k}"' for k in masked_keys)
    query = f'''mutation {{
        removeApiKey(input: [{keys_str}])
    }}'''
    jresp = appsync_http_request(query, session, token, endpoint)
    logger_helper.debug(f"removeApiKey response: {json.dumps(jresp)}")
    if "errors" in jresp:
        error_obj = jresp["errors"][0]
        error_type = error_obj.get("errorType", error_obj.get("type", "Unknown"))
        error_msg = error_obj.get("message", str(error_obj))
        logger_helper.error(f"[removeApiKey] ERROR Type: {error_type} Info: {error_msg}")
        return {"errorType": error_type, "message": error_msg}
    raw = jresp.get("data", {}).get("removeApiKey", "{}")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {"result": raw}
    return raw


def send_reg_steps_to_cloud(session, localSteps, token, endpoint):
    queryInfo = gen_query_reg_steps_string(localSteps)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["regSteps"])

    return jresponse


def send_feedback_request_to_cloud(session, fb_reqs, token, endpoint):
    queryInfo = gen_feedback_request_string(fb_reqs)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getFB"])

    return jresponse


def send_rag_store_request_to_cloud(session, fb_reqs, token, endpoint):
    queryInfo = gen_rag_store_request_string(fb_reqs)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqRAGStore"])

    return jresponse


def findIdx(list, element):
    try:
        index_value = list.index(element)
    except ValueError:
        index_value = -1
    return index_value


def upload_file(session, f2ul, destination, token, endpoint, ftype="general"):
    try:
        logger_helper.debug(
            ">>>>>>>>>>>>>>>>>>>>>file Upload time stamp1: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

        fname = os.path.basename(f2ul)
        fwords = f2ul.split("/")
        relf2ul = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
        if destination:
            prefix = ftype + "|" + destination
        else:
            prefix = ftype + "|" + os.path.dirname(f2ul).replace("\\", "\\\\")

        fopreqs = [{"op": "upload", "names": fname, "options": prefix}]
        logger_helper.debug("fopreqs:" + json.dumps(fopreqs))

        res = send_file_op_request_to_cloud(session, fopreqs, token, endpoint)
        logger_helper.debug("cloud response: " + json.dumps(res['body']['urls']['result']))
        logger_helper.debug(
            ">>>>>>>>>>>>>>>>>>>>>file Upload time stamp2: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

        resd = json.loads(res['body']['urls']['result'])
        logger_helper.debug("resd: " + json.dumps(resd))

        # now perform the upload of the presigned URL
        logger_helper.debug("f2ul:" + json.dumps(f2ul))
        resp = send_file_with_presigned_url(f2ul, resd['body'][0])
        #  logger_helper.debug("upload result: "+json.dumps(resp))
        logger_helper.debug(
            ">>>>>>>>>>>>>>>>>>>>>file Upload time stamp: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        link = resd['body'][0]['fields']['key']

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "Errorupload_file:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "Errorupload_file traceback information not available:" + str(e)
        link = ""

    return link


# datahome should ends with "/", f2dl should starts with "runlogs"
def download_file(session, datahome, f2dl, source, token, endpoint, ftype="general"):
    try:
        fname = os.path.basename(f2dl)
        fwords = f2dl.split("/")
        relf2dl = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
        if source:
            prefix = ftype + "|" + source
        else:
            prefix = ftype + "|" + os.path.dirname(f2dl)

        # local_f2dl = re.sub(r'(runlogs/)[^/]+/', r'\1', f2dl)
        local_f2dl = f2dl

        fopreqs = [{"op": "download", "names": fname, "options": prefix}]
        print("FOPREQS:", fopreqs)

        res = send_file_op_request_to_cloud(session, fopreqs, token, endpoint)
        # logger_helper.debug("cloud response: "+json.dumps(res['body']['urls']['result']))

        resd = json.loads(res['body']['urls']['result'])
        print("RESD:", resd, resd['body'][0])
        # logger_helper.debug("cloud response data: "+json.dumps(resd))
        resp = get_file_with_presigned_url(datahome + "/" + local_f2dl, resd['body'][0])
        #
        # logger_helper.debug("resp:"+json.dumps(resp))
        link = datahome + "/" + local_f2dl

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "Errordownload_file:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "Errordownload_file traceback information not available:" + str(e)
        link = ""

    return link


# def download_file8(session, datahome, f2dl, token, endpoint, ftype="general"):
#     try:
#         fname = os.path.basename(f2dl)
#         fwords = f2dl.split("/")
#         relf2dl = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
#         prefix = ftype + "|" + os.path.dirname(f2dl)

#         fopreqs = [{"op": "download", "names": fname, "options": prefix}]

#         res = send_file_op_request_to_cloud(session, fopreqs, token, endpoint)
#         # logger_helper.debug("cloud response: "+json.dumps(res['body']['urls']['result']))

#         resd = json.loads(res['body']['urls']['result'])
#         # logger_helper.debug("cloud response data: "+json.dumps(resd))
#         resp = get_file_with_presigned_url(datahome+f2dl, resd['body'][0])
#         #
#         # logger_helper.debug("resp:"+json.dumps(resp))
#         link = resd['body'][0]

#     except Exception as e:
#         # Get the traceback information
#         traceback_info = traceback.extract_tb(e.__traceback__)
#         # Extract the file name and line number from the last entry in the traceback
#         if traceback_info:
#             ex_stat = "Errordownload_file8:" + traceback.format_exc() + " " + str(e)
#         else:
#             ex_stat = "Errordownload_file8 traceback information not available:" + str(e)
#         link = ""

#     return link


# list dir on my cloud storage
# def cloud_ls(session, token, endpoint):
#     flist = []
#     fopreqs = [{"op" : "list", "names": "", "options": ""}]
#     res = send_file_op_request_to_cloud(session, fopreqs, token, endpoint)
#     # logger_helper.debug("cloud response: "+json.dumps(res['body']['urls']['result']))

#     for k in res['body']["urls"][0]['Contents']:
#         flist.append(k['Key'])

#     return flist


# def cloud_rm(session, f2rm, token, endpoint):
#     fopreqs = [{"op": "delete", "names": f2rm, "options": ""}]
#     res = send_file_op_request_to_cloud(session, fopreqs, token, endpoint)
#     logger_helper.debug("cloud response: "+json.dumps(res['body']))

_wechat_session_auth_mgr = None
_wechat_session_token_announced = False
_http_session_mint_last_attempt = 0.0
_HTTP_SESSION_MINT_RETRY_S = 300.0


def _try_lazy_http_session_mint() -> None:
    """Best-effort mint of the CN HTTP session token from a LIVE session.

    2026-08-25: a running (or restored) session can lack the eCan session
    token — e.g. the login-time mint failed because the server had not yet
    deployed mintHttpSessionToken. Without this retry, every HTTP GraphQL
    call keeps failing "Bearer token required" until the user logs out and
    back in. Uses the live AppContext auth manager (it holds the CloudBase
    access token the mint needs); throttled to one attempt per 5 minutes.
    """
    global _http_session_mint_last_attempt
    import time as _t
    now = _t.time()
    if now - _http_session_mint_last_attempt < _HTTP_SESSION_MINT_RETRY_S:
        return
    _http_session_mint_last_attempt = now
    try:
        from app_context import AppContext
        login = AppContext.get_login()
        live_mgr = getattr(login, "auth_manager", None)
        if live_mgr is None or not getattr(live_mgr, "signed_in", False):
            return
        logger_helper.info(
            "[AppSync] No CN HTTP session token — attempting lazy mint via live auth manager"
        )
        live_mgr._finalize_http_session_token()
    except Exception as e:
        logger_helper.debug(f"[AppSync] lazy HTTP session mint failed: {e}")


def _get_wechat_http_session_token() -> str:
    """Return the eCan-minted 30-day session token, or '' if unavailable.

    The SCF HTTP GraphQL gate (cloudbase-graphql/scf/auth.js resolveIdentity)
    can only validate the eCan self-signed HS256 session token (minted by
    registerWeChatSession for WeChat logins, mintHttpSessionToken for
    email/phone/password logins) — it cannot validate the raw CloudBase
    access token over plain HTTPS. So CN HTTP requests must authenticate
    with the session token; the access token stays in use for WS paths.
    """
    global _wechat_session_auth_mgr, _wechat_session_token_announced
    try:
        if _wechat_session_auth_mgr is None:
            from auth.auth_manager import AuthManager
            _wechat_session_auth_mgr = AuthManager()
        # Re-sync username from uli.json each call: the cached instance's
        # current_user snapshot would otherwise go stale on account switch.
        saved_user = _wechat_session_auth_mgr._get_saved_username()
        if saved_user:
            _wechat_session_auth_mgr.current_user = saved_user
        ok, tok = _wechat_session_auth_mgr._get_wechat_session_token()
        if ok and tok:
            if not _wechat_session_token_announced:
                _wechat_session_token_announced = True
                logger_helper.info("[AppSync] Using 30-day session token for CN HTTP auth")
            return tok
        # No stored session token — self-heal from the live session
        # (throttled), then re-read.
        _try_lazy_http_session_mint()
        ok, tok = _wechat_session_auth_mgr._get_wechat_session_token()
        if ok and tok:
            if not _wechat_session_token_announced:
                _wechat_session_token_announced = True
                logger_helper.info("[AppSync] Using 30-day session token for CN HTTP auth (lazy mint)")
            return tok
    except Exception as e:
        logger_helper.debug(f"[AppSync] session token unavailable: {e}")
    return ""


def normalize_cloud_owner(owner: str) -> str:
    """Cloud-side identity for owner-enforced resolvers.

    MainWindow.user carries a synthetic ``@local`` suffix for CN WeChat
    logins (``wechat_<openid>@local``); the cloud knows only the bare
    username and rejects the suffixed form with FORBIDDEN
    ("Cross-owner access is forbidden" — verified empirically 2026-08-20).
    Real emails (Intl logins) pass through unchanged.
    """
    if owner and owner.endswith("@local"):
        return owner[: -len("@local")]
    return owner


def _http_auth_header(token: str) -> str:
    """Authorization header value for an HTTP cloud (GraphQL) request.

    CN: prefer the eCan 30-day session token (minted by registerWeChatSession)
    — it is the only bearer the SCF HTTP gate can verify (HS256, sub=openid).
    Fall back to the JWT extracted from the combined ``<id>/@@/<jwt>`` access
    token when no session token exists (e.g. email/CIAM login).

    Intl: unchanged — Cognito sends the IdToken raw (no ``Bearer`` prefix).

    Only the HTTP paths use this; the WS subscription paths keep sending the
    combined token verbatim (the WS bridge parses ``<id>/@@/<jwt>``).
    """
    if not token:
        return ""
    if is_cn_app():
        session_tok = _get_wechat_http_session_token()
        if session_tok:
            return f"Bearer {session_tok}"
        jwt = token.split('/@@/', 1)[-1] if '/@@/' in token else token
        return f"Bearer {jwt}"
    return token


def appsync_http_request(query_string, session, token, endpoint=None, timeout=180, variables=None):
    """
    Send AppSync GraphQL request with authentication.
    Supports both Cognito User Pool tokens and Google ID tokens.
    Also supports CN version (TCB Auth).

    Args:
        query_string: GraphQL query string
        session: requests.Session object
        token: Authentication token
        endpoint: API endpoint URL (optional, will use get_appsync_endpoint() if not provided)
        timeout: Request timeout in seconds (default: 180)
        variables: Optional dict of GraphQL variables
    """
    # 如果没有提供 endpoint，使用通用方法获取
    if not endpoint:
        endpoint = get_appsync_endpoint()

    # Diagnostic logging for token debugging
    if token:
        token_preview = token[:50] if len(token) > 50 else token
        is_jwt = token.startswith("eyJ") and token.count(".") == 2
        logger_helper.info(f"[AppSync] Token present: {len(token)} chars, JWT format: {is_jwt}, preview: {token_preview}...")
    else:
        logger_helper.warning("[AppSync] Token is None or empty!")

    # CN version uses application/json, Intl uses application/graphql.
    # Authorization: CN → 'Bearer <jwt>' (JWT extracted from the combined
    # session token); Intl → raw Cognito token. See _http_auth_header.
    auth_header = _http_auth_header(token)

    # CN fail-fast (2026-09-01): the HTTP gate only accepts JWT bearers
    # (HS256 session token or a CloudBase JWT). New-flow WeChat desktop
    # logins hand the app an OPAQUE 43-char website session token; when
    # registerWeChatSession fails to mint the HS256 session, every request
    # would go out with that opaque bearer and be rejected "Bearer token
    # required" — 48 rejections in one customer session, seen server-side
    # as an UNAUTHENTICATED storm. Refuse to send a known-bad bearer.
    if is_cn_app():
        bearer_value = auth_header[7:] if auth_header.lower().startswith("bearer ") else auth_header
        if bearer_value and bearer_value.count(".") != 2:
            if not getattr(appsync_http_request, "_cn_opaque_warned", False):
                appsync_http_request._cn_opaque_warned = True
                logger_helper.warning(
                    "[AppSync] CN bearer is not a JWT (opaque website session "
                    "token?) — skipping cloud request instead of a guaranteed "
                    "UNAUTHENTICATED. Session registration must mint the HS256 "
                    "token first (see registerWeChatSession)."
                )
            return {"errors": [{"errorType": "UNAUTHENTICATED",
                                "message": "No JWT bearer available (opaque session token) — request not sent"}]}

    headers = {
        'Content-Type': "application/json" if is_cn_app() else "application/graphql",
        'Authorization': auth_header,
        'cache-control': "no-cache"
    }

    try:
        # Send the request with configurable timeout
        payload = {'query': query_string}
        if variables:
            payload['variables'] = variables
        response = session.request(
            url=endpoint,
            method='POST',
            timeout=timeout,
            headers=headers,
            json=payload
        )
        
        # Enhanced response logging
        logger_helper.info(f"[AppSync] Response status: {response.status_code} {response.reason}")
        logger_helper.debug(f"[AppSync] Response headers: {dict(response.headers)}")
        logger_helper.debug(f"[AppSync] Response size: {len(response.content)} bytes")
        
        jresp = response.json()
        
        # Log response structure
        if isinstance(jresp, dict):
            logger_helper.debug(f"[AppSync] Response keys: {list(jresp.keys())}")
            if 'data' in jresp:
                data_keys = list(jresp['data'].keys()) if isinstance(jresp['data'], dict) else 'N/A'
                logger_helper.debug(f"[AppSync] Response data keys: {data_keys}")
            if 'errors' in jresp:
                logger_helper.warning(f"[AppSync] Response contains {len(jresp['errors'])} error(s)")
        elif isinstance(jresp, list):
            logger_helper.debug(f"[AppSync] Response is a list with {len(jresp)} item(s)")
        
        # Log response preview (first 500 chars)
        response_preview = json.dumps(jresp, ensure_ascii=False, default=str)[:500]
        logger_helper.debug(f"[AppSync] Response preview: {response_preview}...")
        
        # Check for authentication errors
        if "errors" in jresp:
            for error in jresp["errors"]:
                error_msg = error.get("message", "")
                error_type = error.get("errorType", "")

                if error_type == "UnauthorizedException":
                    logger_helper.error(f"AppSync authentication failed: {error_msg}")
                    logger_helper.error(f"Token format: {token[:50]}...")

                # Log detailed error info for type mismatch errors.
                #
                # Rate-limit (2026-05-13): a known recurring schema mismatch on
                # ``addVehicles`` (backend expects a different VehicleInput shape
                # than what the offline-sync queue serialises) was spamming ~600
                # ERROR lines per session — 7 lines × ~85 retries of the same
                # queued job.  We still want the diagnostic on the first hit so
                # the schema drift gets noticed, but the loud version after that
                # is pure noise that buries real errors.  Strategy: emit the
                # full 7-line block once per (error-path, error-message) tuple
                # per process; subsequent identical mismatches log a single
                # compact DEBUG line.
                if "type mismatch" in error_msg.lower() or "expected type" in error_msg.lower():
                    _err_path = str(error.get('path', 'N/A'))
                    _err_key = (_err_path, error_msg)
                    if not hasattr(appsync_http_request, "_seen_type_mismatch"):
                        appsync_http_request._seen_type_mismatch = set()
                    _seen = appsync_http_request._seen_type_mismatch
                    if _err_key not in _seen:
                        _seen.add(_err_key)
                        logger_helper.error(f"[AppSync] ❌ GraphQL Type Mismatch Error detected!")
                        logger_helper.error(f"[AppSync] Error message: {error_msg}")
                        logger_helper.error(f"[AppSync] Error path: {_err_path}")
                        logger_helper.error(f"[AppSync] Error locations: {error.get('locations', 'N/A')}")
                        logger_helper.error(f"[AppSync] This usually indicates backend schema mismatch.")
                        logger_helper.error(f"[AppSync] The GraphQL server expects a different input type than what was sent.")
                        # Log the query string for debugging (truncated to avoid log spam)
                        logger_helper.error(f"[AppSync] Query causing error (truncated): {query_string[:500]}...")
                        logger_helper.error(f"[AppSync] (Subsequent identical mismatches will log at DEBUG only.)")
                    else:
                        logger_helper.debug(
                            f"[AppSync] type-mismatch repeat (suppressed) "
                            f"path={_err_path!r} msg={error_msg[:120]!r}"
                        )

        return jresp

    except Exception as e:
        logger_helper.error(f"AppSync request failed: {e}")
        return {
            'errors': [{
                'errorType': 'RequestError',
                'message': str(e)
            }]
        }


def appsync_http_request_w_apikey(query_string, session, apikey, endpoint):
    headers = {
        'Content-Type': "application/graphql",
        'Authorization': apikey,
        'x-custom-api-key': apikey,
        'x-api-caller': "songc@yahoo.com",
        'cache-control': "no-cache"
    }

    # Now we can simply post the request...
    response = session.request(
        url=endpoint,
        method='POST',
        timeout=300,
        headers=headers,
        json={'query': query_string}
    )
    # save response to a log file. with a time stamp.
    # print(response)

    jresp = response.json()

    return jresp


def appsync_http_request2(query_string, session, token, endpoint):
    headers = {
        'Content-Type': "application/json",
        'Authorization': _http_auth_header(token),
        'cache-control': "no-cache",
    }

    # Now we can simply post the request...
    response = session.request(
        url=endpoint,
        method='POST',
        timeout=300,
        headers=headers,
        json={'query': query_string}
    )
    # save response to a log file. with a time stamp.
    # print(response)

    jresp = response.json()

    return jresp


async def appsync_http_request8(query_string, token, endpoint, retries=3):
    headers = {
        'Content-Type': "application/graphql",
        'Authorization': _http_auth_header(token),
        'cache-control': "no-cache",
    }

    for attempt in range(retries):
        try:
            async with limiter:  # Ensure only 5 requests run per second
                async with aiohttp.ClientSession() as session8:
                    async with session8.post(
                            url=endpoint,
                            timeout=aiohttp.ClientTimeout(total=300),
                            headers=headers,
                            json={'query': query_string}
                    ) as response:
                        return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff (2s, 4s, 8s...)

    raise Exception("Failed after multiple retries")
    # headers = {
    #     'Content-Type': "application/graphql",
    #     'Authorization': token,
    #     'cache-control': "no-cache",
    # }
    # async with aiohttp.ClientSession() as session8:
    #     async with session8.post(
    #             url=endpoint,
    #             timeout=aiohttp.ClientTimeout(total=300),
    #             headers=headers,
    #             json={'query': query_string}
    #     ) as response:
    #         jresp = await response.json()
    #         # print(jresp)
    #         return jresp


async def send_file_op_request_to_cloud8(session, fops, token, endpoint):
    queryInfo = gen_file_op_request_string(fops)

    jresp = await appsync_http_request8(queryInfo, session, token, endpoint)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.debug("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqFileOp"])

    return jresponse


async def send_file_with_presigned_url8(session, src_file, resp):
    async with aiohttp.ClientSession() as session:
        with open(src_file, 'rb') as f:
            form = aiohttp.FormData()
            for key, value in resp['fields'].items():
                form.add_field(key, value)
            form.add_field('file', f, filename=src_file)
            async with session.post(resp['url'], data=form) as r:
                logger_helper.debug("SENDING PRESIGNED URL STATUS:" + str(r.status))
                # print("PRESIGNED RESPONSE:",r)
                f.close()
                return r.status


async def upload_file8(session, f2ul, token, endpoint, ftype="general"):
    logger_helper.debug(
        ">>>>>>>>>>>>>>>>>>>>>file Upload time stamp1: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    fname = os.path.basename(f2ul)
    fwords = f2ul.split("/")
    relf2ul = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
    prefix = ftype + "|" + os.path.dirname(f2ul).replace("\\", "\\\\")

    fopreqs = [{"op": "upload", "names": fname, "options": prefix}]
    logger_helper.debug("fopreqs:" + json.dumps(fopreqs))

    # get presigned URL
    res = await send_file_op_request_to_cloud8(session, fopreqs, token, endpoint)
    logger_helper.debug("cloud response: " + json.dumps(res['body']['urls']['result']))
    logger_helper.debug(
        ">>>>>>>>>>>>>>>>>>>>>file Upload time stamp2: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    resd = json.loads(res['body']['urls']['result'])
    logger_helper.debug("resd: " + json.dumps(resd))

    # now perform the upload of the presigned URL
    logger_helper.debug("f2ul:" + json.dumps(f2ul))
    resp = await send_file_with_presigned_url8(session, f2ul, resd['body'][0])
    #  logger_helper.debug("upload result: "+json.dumps(resp))
    logger_helper.debug(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

# ==========================================================================================
#	requestRunExtAgentSkill(input: [SkillRun]): AWSJSON!
# 	skid: ID!
# 	owner: String
# 	name: String
# 	start: AWSDateTime
# 	in_data: AWSJSON!
# 	verbose: Boolean
def gen_query_reqest_run_ext_agent_skill_string(query):
    logger.debug("in query:"+json.dumps(query))
    query_string = """
        mutation MyMutation {
      requestRunExtAgentSkill (input:[
    """
    rec_string = ""
    for i in range(len(query)):
        #rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ askid: " + str(query[i]["askid"]) + ", "
        rec_string = rec_string + "requester_mid: " + str(query[i]["requester_mid"]) + ", "
        rec_string = rec_string + "owner: \"" + query[i]["owner"] + "\", "
        rec_string = rec_string + "start: \"" + query[i]["start"] + "\", "
        rec_string = rec_string + "name: \"" + query[i]["name"] + "\", "
        rec_string = rec_string + "in_data: \"" + query[i]["in_data"] + "\", "
        # rec_string = rec_string + "verbose: " + str(query[i]["verbose"]) + " }"
        rec_string += "verbose: " + ("true" if query[i]["verbose"] else "false") + " }"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
    ]) 
    }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string

#
def gen_query_report_run_ext_agent_skill_status_string(query):
    logger.debug("in query:"+json.dumps(query))
    query_string = """
        mutation MyMutation {
      reportRunExtAgentSkillStatus (input:[
    """
    rec_string = ""
    for i in range(len(query)):
        #rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ run_id: " + str(query[i]["run_id"]) + ", "
        rec_string = rec_string + "skid: " + str(query[i]["skid"]) + ", "
        rec_string = rec_string + "runner_mid: " + str(query[i]["runner_mid"]) + ", "
        rec_string = rec_string + "runner_bid: " + str(query[i]["runner_bid"]) + ", "
        rec_string = rec_string + "requester: \"" + str(query[i]["requester"]) + "\", "
        rec_string = rec_string + "status: \"" + query[i]["status"] + "\", "
        rec_string = rec_string + "start_time: \"" + query[i]["start_time"] + "\", "
        rec_string = rec_string + "end_time: \"" + query[i]["end_time"] + "\", "
        rec_string = rec_string + "result_data: \"" + query[i]["result_data"] + "\" }"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
    ]) 
    }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string



def gen_add_agents_string(agents):
    """
    Generate GraphQL mutation string for adding agents
    
    ✅ Now uses generic GraphQL builder based on Schema
    ✅ No hardcoded fields - all fields come from data and Schema mapping
    """
    return build_mutation(DataType.AGENT, Operation.ADD, agents)


def gen_update_agents_string(agents):
    """
    Generate GraphQL mutation string for updating agents
    
    ✅ Now uses generic GraphQL builder based on Schema
    ✅ No hardcoded fields - all fields come from data and Schema mapping
    """
    return build_mutation(DataType.AGENT, Operation.UPDATE, agents)




def gen_remove_agents_string(removeOrders):
    """
    Generate GraphQL mutation string for removing agents
    
    Now uses generic GraphQL builder
    """
    return build_mutation(DataType.AGENT, Operation.DELETE, removeOrders)


def gen_query_agents_string(q_setting):
    """Generate GraphQL query string for querying agents
    
    New schema: queryAgents(input: AgentQueryInput): [Agent!]!
    AgentQueryInput has: id, name, description (all optional)
    """
    # Build input object based on q_setting
    input_parts = []
    if q_setting.get("id"):
        input_parts.append(f'id: "{q_setting["id"]}"')
    if q_setting.get("name"):
        input_parts.append(f'name: "{q_setting["name"]}"')
    if q_setting.get("description"):
        input_parts.append(f'description: "{q_setting["description"]}"')
    
    input_str = ", ".join(input_parts) if input_parts else ""
    
    query_string = f'''query MyAgentQuery {{
  queryAgents(input: {{ {input_str} }}) {{
    id
    owner
    name
    title
    supervisor_id
    birthday
    gender
    personalities
    status
    rank
    vehicle_id
    avatar_resource_id
    description
    url
    version
    extra_data
    capabilities
  }}
}}'''
    logger.debug(query_string)
    return query_string

def gen_get_agents_string():
    """Generate GraphQL query string for getting all agents for current user"""
    # Use queryAgents with input parameter (AgentQueryInput type)
    # Returns [Agent!]! so we need to specify which fields to select
    query_string = '''query MyGetAgentQuery {
  queryAgents(input: {}) {
    id
    owner
    name
    title
    supervisor_id
    birthday
    gender
    personalities
    status
    rank
    vehicle_id
    avatar_resource_id
    description
    url
    version
    extra_data
    capabilities
  }
}'''
    logger.debug(query_string)
    return query_string



def gen_add_agent_skills_string(skills):
    """
    Generate GraphQL mutation string for adding skills
    
    ✅ Now uses generic GraphQL builder based on Schema
    ✅ No hardcoded fields - all fields come from data and Schema mapping
    """
    return build_mutation(DataType.SKILL, Operation.ADD, skills)





def gen_update_agent_skills_string(skills):
    """
    Generate GraphQL mutation string for updating skills
    
    ✅ Now uses generic GraphQL builder based on Schema
    ✅ No hardcoded fields - all fields come from data and Schema mapping
    """
    return build_mutation(DataType.SKILL, Operation.UPDATE, skills)




def gen_remove_agent_skills_string(removeOrders):
    """
    Generate GraphQL mutation string for removing skills
    
    Now uses generic GraphQL builder
    """
    return build_mutation(DataType.SKILL, Operation.DELETE, removeOrders)



def gen_query_agent_skills_string(q_setting):
    if q_setting["byowneruser"]:
        query_string = "query MySkQuery { queryAgentSkillRels(input: \"{ \\\"byowneruser\\\": true}\") } "
    else:
        query_string = "query MySkQuery { queryAgentSkillRels(input: \"{ \\\"byowneruser\\\": false, \\\"qphrase\\\": \\\"" +q_setting["qphrase"]+"\\\"}\") } "

    rec_string = ""
    tail_string = ""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string

def gen_get_agent_skills_string(public_catalog: bool = False):
    """Generate GraphQL query string for getting skills.

    Server schema: queryAgentSkills(input: SkillQueryInput): [AgentSkill!]!
    SkillQueryInput: { id: ID, name: String, description: String }
    AgentSkill fields: id, askid, owner, name, description, version, level, config, diagram,
                       tags, examples, inputModes, outputModes, apps, limitations, path,
                       source, price, price_model, public, rentable

    Args:
        public_catalog: when True, request the PUBLIC skill catalog
            (``input: {isPublic: true}``) — the CN/TCB resolver skips owner
            scoping in this mode and returns every skill with isPublic=true
            (skill store). Default False = the caller's own skills.
            NOTE: the AWS AppSync SkillQueryInput does not define isPublic —
            callers must be prepared for a validation error there and fall
            back to the getPublicSkills Lambda query (cloud_get_public_skills).

    NOTE on 'source' field:
      The 'source' field returned by the GraphQL query is a SkillSource enum value
      ('ui' | 'code' | 'subscribed' | 'external'), NOT a list of file paths.
      See SkillSource in constants.py for the full definition.
      This contrasts with the Python-side prepare_skill_with_source() function which
      populates 'source' as comma-separated code filenames for upload purposes.
    """
    # Query all skills by passing empty input (no filters)
    # AWS schema uses snake_case: price_model, public (see scripts/appsync_schema_latest.graphql)
    _input = '{isPublic: true}' if public_catalog else '{}'
    # Catalog variant must ALSO select `isPublic`: the CN/TCB resolver
    # populates isPublic (prisma field) while the legacy `public` alias can
    # resolve null — and GraphQL returns ONLY selected fields, so without
    # this the response rows carry no usable flag at all and the store
    # filter drops every row (customer log 2026-08-25: catalog returned 4
    # skills, store stayed empty). CN-only selection: on AWS this makes the
    # catalog attempt fail validation, which is fine — that path already
    # falls back to the getPublicSkills Lambda query.
    _extra_fields = '\n            isPublic' if public_catalog else ''
    query_string = '''query MyGetAgentSkillsQuery {
        queryAgentSkills(input: ''' + _input + ''') {''' + _extra_fields + '''
            id
            askid
            owner
            name
            description
            version
            level
            config
            diagram
            tags
            examples
            inputModes
            outputModes
            apps
            limitations
            path
            source
            price
            price_model
            public
            rentable
        }
    }'''
    logger.debug(query_string)
    return query_string


def gen_add_agent_tasks_string(tasks, test_settings=None):
    """
    Generate GraphQL mutation string for adding tasks
    
    Now uses generic GraphQL builder based on Schema
    No hardcoded fields - all fields come from data and Schema mapping
    """
    # Don't pass settings - GraphQL schema doesn't support it
    return build_mutation(DataType.TASK, Operation.ADD, tasks)


def gen_remove_agent_tasks_string(removeOrders):
    """
    Generate GraphQL mutation string for removing tasks
    
    Now uses generic GraphQL builder
    """
    return build_mutation(DataType.TASK, Operation.DELETE, removeOrders)



def gen_update_agent_tasks_string(tasks):
    """
    Generate GraphQL mutation string for updating tasks
    
    Now uses generic GraphQL builder based on Schema
    No hardcoded fields - all fields come from data and Schema mapping
    """
    return build_mutation(DataType.TASK, Operation.UPDATE, tasks)



def gen_query_agent_tasks_by_time_string(query):

    query_string = """
        query MyQuery {
      queryAgentTasks (qm:[
    """
    rec_string = ""
    for i in range(len(query)):
        rec_string = rec_string + "{"
        if "byowneruser" in query[i]:
            rec_string = rec_string + "byowneruser: " + str(query[i]['byowneruser']).lower()
        else:
            rec_string = rec_string + "owner: \"" + str(query[i]['owner']).lower() + "\""

        if "created_date_range" in query[i]:
            rec_string = rec_string + ", "
            rec_string = rec_string + "created_date_range: \"" + query[i]['created_date_range'] + "\" }"
        else:
            rec_string = rec_string + "}"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ])
        }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string


def gen_query_agent_tasks_string(query):
    query_string = """
        query MyQuery {
      queryAgentTasks (qm:[
    """
    rec_string = ""
    for i in range(len(query)):
        rec_string = rec_string + "{ mid: " + str(int(query[i]['mid'])) + ", "
        rec_string = rec_string + "ticket: " + str(int(query[i]['ticket'])) + ", "
        rec_string = rec_string + "botid: " + str(int(query[i]['botid'])) + ", "
        rec_string = rec_string + "owner: \"" + query[i]['owner'] + "\", "
        rec_string = rec_string + "skills: \"" + query[i]['skills'] + "\" }"
        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ])
        }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string


def gen_get_agent_tasks_string():
    """Generate GraphQL query string for getting all tasks for current user"""
    # AppSync schema requires a selection set for queryAgentTasks and does not support legacy qb argument.
    # Query tasks without filters (server should scope by auth context), request common fields.
    query_string = '''query MyGetAgentTasksQuery {
  queryAgentTasks {
    id
    owner
    name
    description
    status
    priority
    org_id
    source
    task_type
    trigger_type
    metadata
    result
    schedule
  }
}'''
    logger.debug(query_string)
    return query_string


def gen_add_agent_tools_string(tools, test_settings={}):
    """
    Generate GraphQL mutation string for adding tools
    
    Now uses generic GraphQL builder based on Schema
    No hardcoded fields - all fields come from data and Schema mapping
    """
    settings = test_settings if test_settings else {"testmode": False}
    return build_mutation(DataType.TOOL, Operation.ADD, tools, settings)


def gen_remove_agent_tools_string(removeOrders):
    """
    Generate GraphQL mutation string for removing tools
    
    Now uses generic GraphQL builder
    """
    return build_mutation(DataType.TOOL, Operation.DELETE, removeOrders)



def gen_update_agent_tools_string(tools):
    """
    Generate GraphQL mutation string for updating tools
    
    ✅ Now uses generic GraphQL builder based on Schema
    ✅ No hardcoded fields - all fields come from data and Schema mapping
    """
    return build_mutation(DataType.TOOL, Operation.UPDATE, tools)



def gen_query_agent_tools_by_time_string(query):

    query_string = """
        query MyQuery {
      queryAgentToolRels (qm:[
    """
    rec_string = ""
    for i in range(len(query)):
        rec_string = rec_string + "{"
        if "byowneruser" in query[i]:
            rec_string = rec_string + "byowneruser: " + str(query[i]['byowneruser']).lower()
        else:
            rec_string = rec_string + "owner: \"" + str(query[i]['owner']).lower() + "\""

        if "created_date_range" in query[i]:
            rec_string = rec_string + ", "
            rec_string = rec_string + "created_date_range: \"" + query[i]['created_date_range'] + "\" }"
        else:
            rec_string = rec_string + "}"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ])
        }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string


def gen_query_agent_tools_string(query):
    query_string = """
        query MyQuery {
      queryAgentToolRels (qt:[
    """
    rec_string = ""
    for i in range(len(query)):
        rec_string = rec_string + "{ toolid: " + str(int(query[i]['toolid'])) + ", "
        rec_string = rec_string + "owner: \"" + query[i]['owner'] + "\", "
        rec_string = rec_string + "name: \"" + query[i]['name'] + "\" }"
        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ])
        }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string



def gen_get_agent_tools_string():
    """Generate GraphQL query string for getting all tools for current user"""
    # Use queryAgentTools with qb parameter (byowneruser: true to get current user's tools)
    qb = json.dumps({"byowneruser": True}, ensure_ascii=False).replace('"', '\\"')
    query_string = f'query MyGetAgentToolsQuery {{ queryAgentTools(qb: "{qb}") }}'
    logger.debug(query_string)
    return query_string




def gen_add_knowledges_string(knowledges, test_settings={}):
    query_string = """
        mutation MyAMMutation {
      addKnowledges (input:[
    """
    rec_string = ""
    for i in range(len(knowledges)):
        if isinstance(knowledges[i], dict):
            rec_string = rec_string + "{ knid:" + str(knowledges[i]["knId"]) + ", "
            rec_string = rec_string + "owner:\"" + knowledges[i]["owner"] + "\", "
            rec_string = rec_string + "name:" + knowledges[i]["name"] + ", "
            rec_string = rec_string + "description:\"" + knowledges[i]["description"] + "\", "
            rec_string = rec_string + "path:\"" + knowledges[i]["path"] + "\", "
            rec_string = rec_string + "status:\"" + knowledges[i]["status"] + "\", "
            rec_string = rec_string + "metadata:" + knowledges[i]["metadata"].replace('"', '\\"') + ", "
            rec_string = rec_string + "rag:\"" + knowledges[i]["rag"] + "\"} "
        else:
            rec_string = rec_string + "{ knid:" + str(knowledges[i].getKnid()) + ", "
            rec_string = rec_string + "owner:\"" + knowledges[i].getOwner() + "\", "
            rec_string = rec_string + "name:" + knowledges[i].getName() + ", "
            rec_string = rec_string + "description:\"" + knowledges[i].getDescription() + "\", "
            rec_string = rec_string + "path:\"" + knowledges[i].getPath() + "\", "
            rec_string = rec_string + "status:\"" + knowledges[i].getStatus() + "\", "
            rec_string = rec_string + "metadata:" + knowledges[i].getMetadata().replace('"', '\\"') + ", "
            rec_string = rec_string + "rag:\"" + knowledges[i].getRag() + "\"} "

        if i != len(knowledges) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    if len(test_settings) == 0:
        rec_string = rec_string + ", settings: \"{ \\\"testmode\\\": false}\""
    else:
        rec_string = rec_string + ", settings: \"{ \\\"testmode\\\": false}\""


    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string


def gen_remove_knowledges_string(removeOrders):
    query_string = """
        mutation MyRMMutation {
      removeKnowledges (input:[
    """
    rec_string = ""
    for i in range(len(removeOrders)):
        rec_string = rec_string + "{ oid:" + str(removeOrders[i]["id"]) + ", "
        rec_string = rec_string + "owner:\"" + removeOrders[i]["owner"] + "\", "
        rec_string = rec_string + "reason:\"" + removeOrders[i]["reason"] + "\"} "

        if i != len(removeOrders) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string



def gen_update_knowledges_string(knowledges):
    query_string = """
        mutation MyMutation {
      updateKnowledges (input:[
    """
    rec_string = ""
    for i in range(len(knowledges)):
        if isinstance(knowledges[i], dict):
            rec_string = rec_string + "{ knid:" + str(knowledges[i]["knId"]) + ", "
            rec_string = rec_string + "owner:\"" + knowledges[i]["owner"] + "\", "
            rec_string = rec_string + "name:" + knowledges[i]["name"] + ", "
            rec_string = rec_string + "description:\"" + knowledges[i]["description"] + "\", "
            rec_string = rec_string + "path:\"" + knowledges[i]["path"] + "\", "
            rec_string = rec_string + "status:\"" + knowledges[i]["status"] + "\", "
            rec_string = rec_string + "metadata:" + knowledges[i]["metadata"].replace('"', '\\"') + ", "
            rec_string = rec_string + "rag:\"" + knowledges[i]["rag"] + "\"} "
        else:
            rec_string = rec_string + "{ knid:" + str(knowledges[i].getKnid()) + ", "
            rec_string = rec_string + "owner:\"" + knowledges[i].getOwner() + "\", "
            rec_string = rec_string + "name:" + knowledges[i].getName() + ", "
            rec_string = rec_string + "description:\"" + knowledges[i].getDescription() + "\", "
            rec_string = rec_string + "path:\"" + knowledges[i].getPath() + "\", "
            rec_string = rec_string + "status:\"" + knowledges[i].getStatus() + "\", "
            rec_string = rec_string + "metadata:" + knowledges[i].getMetadata().replace('"', '\\"') + ", "
            rec_string = rec_string + "rag:\"" + knowledges[i].getRag() + "\"} "

        if i != len(knowledges) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string



def gen_query_knowledges_by_time_string(query):

    query_string = """
        query MyQuery {
      queryKnowledges (qk:[
    """
    rec_string = ""
    for i in range(len(query)):
        rec_string = rec_string + "{"
        if "byowneruser" in query[i]:
            rec_string = rec_string + "byowneruser: " + str(query[i]['byowneruser']).lower()
        else:
            rec_string = rec_string + "owner: \"" + str(query[i]['owner']).lower() + "\""

        if "created_date_range" in query[i]:
            rec_string = rec_string + ", "
            rec_string = rec_string + "created_date_range: \"" + query[i]['created_date_range'] + "\" }"
        else:
            rec_string = rec_string + "}"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ])
        }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string


def gen_query_knowledges_string(query):
    query_string = """
        query MyQuery {
      queryKnowledges (qk:[
    """
    rec_string = ""
    for i in range(len(query)):
        rec_string = rec_string + "{ knid: " + str(int(query[i]['knid'])) + ", "
        rec_string = rec_string + "owner: \"" + query[i]['owner'] + "\", "
        rec_string = rec_string + "name: \"" + query[i]['name'] + "\" }"
        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ])
        }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string




def gen_get_knowledges_string():
    query_string = 'query MyGetKnowledgesQuery { getKnowledges (ids:"'
    rec_string = "0"

    tail_string = '") }'
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string

# 	component_id: ID!
# 	name: String
# 	proj_id: ID!
# 	description: String
# 	category: String
# 	application: String
# 	metadata: AWSJSON
def gen_query_components_string(components):
    query_string = """
            query MyQuery {
          queryComponents (components:[
        """
    rec_string = ""
    for i in range(len(components)):
        rec_string = rec_string + "{ component_id: " + str(components[i]['component_id']) + ", "
        rec_string = rec_string + "name: \"" + components[i]['name'] + "\", "
        rec_string = rec_string + "proj_id: " + str(components[i]['proj_id']) + ", "
        rec_string = rec_string + "description: \"" + components[i]['description'] + "\", "
        rec_string = rec_string + "category: \"" + components[i]['category'] + "\", "
        rec_string = rec_string + "application: \"" + components[i]['application'] + "\", "
        rec_string = rec_string + "metadata: \"" + json.dumps(components[i]['metadata']).replace('"', '\\"') + "\" }"
        if i != len(components) - 1:
            rec_string = rec_string + ', '

    tail_string = """
            ])
            }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string


def gen_query_fom_string(fom_info):
    """Generates a GraphQL query string for the queryFOM mutation, ensuring correct syntax."""

    # Use json.dumps to safely format the list of strings for product_app.
    # This handles quoting and commas automatically, creating a valid JSON array string.
    logger.debug(f"fom_info: {fom_info}")
    product_app_str = json.dumps(fom_info.get('product_app', []))

    # Manually build the string for the 'params' list because GraphQL keys are not quoted.
    params_list = fom_info.get('params', [[]])[0]
    params_str_list = []
    for param in params_list:
        # Escape any double quotes within the values to prevent breaking the query string
        param_name = param.get('name', '').replace('"', '\\"')
        param_ptype = param.get('ptype', '').replace('"', '\\"')
        param_value = param.get('value', '').replace('"', '\\"')

        # Note: GraphQL keys (name, ptype, value) are not quoted in the object definition.
        param_str = f'{{name: "{param_name}", ptype: "{param_ptype}", value: "{param_value}"}}'
        params_str_list.append(param_str)

    # Join the list of parameter strings into a single string like "[{...}, {...}]"
    params_str = f"[{', '.join(params_str_list)}]"

    # Construct the final query using an f-string for clarity and correctness.
    # This is much safer than manual string concatenation.
    query_string = f"""
        query MyQuery {{
          queryFOM(params: {{
            component_name: "{fom_info.get('component_name', '')}",
            product_app: {product_app_str},
            max_product_metrics: {fom_info.get('max_product_metrics', 0)},
            max_component_metrics: {fom_info.get('max_component_metrics', 0)},
            params: {params_str}
          }})
        }}
    """

    logger.debug(f"Generated queryFOM string: {query_string}")
    return query_string




def gen_rank_results_string(rank_data_input):
    """Generate a GraphQL query string for queryRankResults using AWSJSON fields.

    The AppSync schema expects:
      input RankData { fom_form: AWSJSON!, rows: [AWSJSON!], component_info: AWSJSON! }

    Each AWSJSON value must be provided as a JSON string literal in the GraphQL query.
    We accomplish this by double-encoding the Python object: json.dumps(json.dumps(obj)).
    """

    try:
        fom_form = rank_data_input.get("fom_form", {})
        rows = rank_data_input.get("rows", []) or []
        component_info = rank_data_input.get("component_info", {})

        # Double-encode to embed JSON as a GraphQL string literal (AWSJSON)
        fom_form_literal = json.dumps(json.dumps(fom_form))          # => "\"{...}\""
        rows_literals = [json.dumps(json.dumps(r)) for r in rows]    # => ["\"{...}\"", ...]
        rows_array_literal = f"[{', '.join(rows_literals)}]"
        component_info_literal = json.dumps(json.dumps(component_info))

        query_string = f"""
        query MyQuery {{
          queryRankResults(rank_data: {{
            fom_form: {fom_form_literal}
            rows: {rows_array_literal}
            component_info: {component_info_literal}
          }})
        }}
        """


        logger.debug(f"Generated queryRankResults string: {query_string}")
        return query_string
    except Exception as e:
        logger.error(f"Error generating queryRankResults string: {e}\nrank_data_input={rank_data_input}")
        # Fallback minimal query to avoid crash; server will error with useful message
        return "query MyQuery { queryRankResults(rank_data: { fom_form: \"{}\", rows: [], component_info: \"{}\" }) }"




def gen_start_long_llm_task_string(task_input):
    """Generate a GraphQL query string for queryRankResults using AWSJSON fields.

    The AppSync schema expects:
      startLongLLMTask(task_input: AWSJSON!)
      where task_input internally looks like:
      {
        "acct_site_id": "",
        "agent_id": "",
        "work_type": "",
        "task_id": "",
        "task_data": { "fom_form": {...}, "rows": [{...}], "component_info": {...} }
      }

    For AWSJSON, the entire payload must be sent as a JSON string literal, i.e. the
    whole dictionary is double-encoded: json.dumps(json.dumps(task_input)).
    """

    try:
        # Validate and normalize structure
        if not isinstance(task_input, dict):
            raise ValueError("task_input must be a dict")

        payload = {
            "acct_site_id": task_input.get("acct_site_id", ""),
            "agent_id": task_input.get("agent_id", ""),
            "work_type": task_input.get("work_type", ""),
            "task_id": task_input.get("task_id", ""),
            "task_data": task_input.get("task_data", {}) or {}
        }

        # Double-encode so the GraphQL literal is a JSON string (AWSJSON)
        input_literal = json.dumps(json.dumps(payload))

        query_string = f"""
        mutation MyMutation {{
          startLongLLMTask(task_input: {input_literal})
        }}
        """

        logger.debug(f"Generated startLongLLMTask string: {query_string}")
        return query_string
    except Exception as e:
        logger.error(f"Error generating startLongLLMTask string: {e}\ninput={task_input}")
        # Fallback minimal mutation with empty object
        return "mutation MyMutation { startLongLLMTask(task_input: \"{}\") }"





def gen_get_nodes_prompts_string(nodes):
    query_string = """
            query MyQuery {
          getNodesPrompts (nodes:[
        """
    rec_string = ""
    for i in range(len(nodes)):
        rec_string = rec_string + "{ askid: \"" + str(nodes[i]['askid']) + "\", "
        rec_string = rec_string + "name: \"" + nodes[i]['name'] + "\", "
        rec_string = rec_string + "situation: \"" + "" + "\" }"
        if i != len(nodes) - 1:
            rec_string = rec_string + ', '

    tail_string = """
            ])
            }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string



def gen_update_agent_tasks_ex_status_string(tasksStats):
    query_string = """
            mutation updateAgentTasksExStatus {
          updateAgentTasksExStatus (input:[
        """
    rec_string = ""
    for i in range(len(tasksStats)):
        if isinstance(tasksStats[i], dict):
            rec_string = rec_string + "{ ataskid:" + str(tasksStats[i]["ataskid"]) + ", "
            rec_string = rec_string + "status:\"" + tasksStats[i]["status"] + "\"}"
        else:
            rec_string = rec_string + "{ mid:" + str(tasksStats[i].getMid()) + ", "
            rec_string = rec_string + "status:\"" + tasksStats[i].getStatus() + "\"} "


        if i != len(tasksStats) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
        ) 
        } """
    query_string = query_string + rec_string + tail_string
    logger.debug("DAILY REPORT QUERY STRING:"+query_string)
    return query_string




def send_update_agent_tasks_ex_status_to_cloud(session, tasksStats, token, endpoint):
    if len(tasksStats) > 0:
        query = gen_update_agent_tasks_ex_status_string(tasksStats)

        jresp = appsync_http_request(query, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            jresponse = jresp["errors"][0]
            error_type = jresponse.get("errorType", "Unknown")
            error_msg = jresponse.get("message", str(jresponse))
            logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
            logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
        else:
            jresponse = json.loads(jresp["data"]["updateAgentTasksExStatus"])
    else:
        logger.error("ERROR Type: EMPTY DAILY REPORTS")
        jresponse = "ERROR: EMPTY REPORTS"
    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_completion_status_to_cloud(session, taskStats, token, endpoint, full=True):
    if len(taskStats) > 0:
        query = gen_daily_update_string(taskStats, full)

        jresp = appsync_http_request(query, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            jresponse = jresp["errors"][0]
            error_type = jresponse.get("errorType", "Unknown")
            error_msg = jresponse.get("message", str(jresponse))
            logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
            logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
        else:
            jresponse = json.loads(jresp["data"]["reportTaskStatus"])
    else:
        logger.error("ERROR Type: EMPTY DAILY REPORTS")
        jresponse = "ERROR: EMPTY REPORTS"
    return jresponse


# =================================================================================================
# Helper function for safe JSON parsing
def _is_token_expired_error_message(error_message: str) -> bool:
    """True if `error_message` is a transient UNAUTHENTICATED / token-expired
    message the SessionSupervisor will refresh. Used to demote these from
    ERROR to WARNING so they don't pollute log-monitoring dashboards.
    """
    if not error_message:
        return False
    msg_lower = error_message.lower()
    return (
        'unauthenticated' in msg_lower
        or 'invalid or expired access token' in msg_lower
        or 'access token has expired' in msg_lower
        or 'expired access token' in msg_lower
        or 'token expired' in msg_lower
        or 'bearer token required' in msg_lower
    )


def safe_parse_response(jresp, operation_name, data_key):
    """
    Safely parse AppSync response
    
    Args:
        jresp: JSON response from AppSync
        operation_name: Name of the operation (for error messages)
        data_key: Key to extract from response data
        
    Returns:
        Parsed response data
        
    Raises:
        Exception: If response contains errors or returns null
    """
    # Check if data exists first (partial success case - data with errors)
    data = jresp.get("data", {})
    response_data = data.get(data_key) if data else None
    
    if "errors" in jresp:
        errors = jresp.get("errors", [])
        error_message = errors[0].get("message", "Unknown error") if errors else "Unknown error"
        
        # If we have data despite errors, log warning but return the data (partial success)
        if response_data is not None:
            logger.warning(f"⚠️ GraphQL partial success with errors: {error_message}")
            logger.debug(f"📋 Errors: {json.dumps(errors, ensure_ascii=False)[:500]}")
            # Return the data we got
            if isinstance(response_data, str):
                return json.loads(response_data)
            else:
                return response_data
        else:
            # No data and errors - this is a failure
            # Detect "Cannot return null for non-nullable type" as a known backend schema issue
            is_schema_null_error = "Cannot return null for non-nullable type" in error_message
            # UNAUTHENTICATED / token expired is a known transient — the
            # OfflineSyncManager and SessionSupervisor are on the case, so
            # logging at ERROR would only pollute log-monitoring dashboards
            # without helping anyone find a real problem.
            is_token_expired_error = _is_token_expired_error_message(error_message)
            if is_schema_null_error:
                logger.warning(f"GraphQL schema null error in '{operation_name}': {error_message} (known backend issue)")
            elif is_token_expired_error:
                logger.warning(f"🔑 GraphQL token expired in '{operation_name}': {error_message}")
                logger.debug(f"📋 Full error response: {json.dumps(jresp, ensure_ascii=False)}")
            else:
                logger.error(f"❌ GraphQL Error: {error_message}")
                logger.error(f"📋 Full error response: {json.dumps(jresp, ensure_ascii=False)}")
            # Tag the exception so OfflineSyncManager / cloud_api_service can
            # distinguish "token is dead, refresh & retry later" from a real
            # permanent failure without re-parsing the message string.
            exc = Exception(f"{operation_name} failed: {error_message}")
            if is_token_expired_error:
                exc.is_token_expired_error = True  # type: ignore[attr-defined]
            raise exc
    else:
        if response_data is not None:
            # If already parsed (list/dict from typed GraphQL response), return directly
            # If string (AWSJSON), parse it
            if isinstance(response_data, str):
                return json.loads(response_data)
            else:
                return response_data
        else:
            # Null response without errors - this is a server-side issue
            error_msg = f"{operation_name} returned null"
            logger.warning(f"⚠️ {error_msg} (server rejected the request)")
            logger.warning(f"📋 Full response: {json.dumps(jresp, ensure_ascii=False)}")
            logger.debug(f"💡 Possible causes:")
            logger.debug(f"   1. Resource not found (for UPDATE/DELETE)")
            logger.debug(f"   2. Resource already exists (for ADD)")
            logger.debug(f"   3. Data validation failed on server")
            logger.debug(f"   4. Permission denied (check IAM/Cognito)")
            logger.debug(f"   5. Backend timeout or internal error")
            return None

# =================================================================================================
# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT, Operation.ADD)
def send_add_agents_request_to_cloud(session, bots, token, endpoint):
    mutationInfo = gen_add_agents_string(bots)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "addAgents", "addAgents")



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT, Operation.UPDATE)
def send_update_agents_request_to_cloud(session, bots, token, endpoint):

    mutationInfo = gen_update_agents_string(bots)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "updateAgents", "updateAgents")



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT, Operation.DELETE)
def send_remove_agents_request_to_cloud(session, removes, token, endpoint):

    mutationInfo = gen_remove_agents_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "removeAgents", "removeAgents")




@cloud_api(DataType.AGENT, Operation.QUERY)
def send_query_agents_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_agents_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgents", "queryAgents")


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_agents_request_to_cloud(session, token, endpoint):
    """Query all agents for current user using queryAgents with byowneruser"""
    queryInfo = gen_get_agents_string()

    jresp = _appsync_http_request_with_fresh_token_backoff(
        queryInfo, session, token, endpoint,
        operation_name="queryAgents",
    )

    if "errors" in jresp:
        first_error = jresp["errors"][0] if jresp["errors"] else {}
        first_message = str(first_error.get("message", ""))
        if "Cannot return null for non-nullable type" in first_message:
            err_msg = "AppSync queryAgents schema error: resolver returned null for non-nullable field"
            logger.error(f"{err_msg}. Raw errors: {json.dumps(jresp.get('errors', []), ensure_ascii=False)}")
            raise Exception(err_msg)
        elif "GRAPHQL_VALIDATION_FAILED" in str(first_error.get("extensions", {}).get("code", "")):
            # Schema mismatch — backend SDL is missing the camelCase/snake_case
            # alias this client expected. Not a client bug, not a transient
            # network issue; log once at WARNING and return empty so the UI
            # keeps working. The proper fix is to update the backend SDL.
            logger.warning(
                f"AppSync queryAgents schema mismatch: {json.dumps(jresp.get('errors', []), ensure_ascii=False)[:500]}"
            )
            return []
        elif _is_token_expired_error_message(first_message):
            # Transient UNAUTHENTICATED — SessionSupervisor will refresh.
            logger.warning(f"🔑 AppSync queryAgents token expired: {first_message}")
            logger.debug(f"📋 Full error response: {json.dumps(jresp, ensure_ascii=False)}")
            jresponse = first_error
        else:
            logger.error("AppSync queryAgents error: " + json.dumps(jresp))
            jresponse = first_error
    else:
        try:
            agents_data = jresp["data"]["queryAgents"]
            if agents_data is None:
                logger.info("queryAgents returned null - user has no agents data")
                jresponse = []
            else:
                # Return type is now [Agent!]! - already a list of dicts, no json.loads needed
                jresponse = agents_data
        except (KeyError, TypeError) as e:
            logger.error(f"Failed to parse queryAgents response: {e}")
            jresponse = []

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT_SKILL, Operation.ADD)
def send_add_agent_skill_relations_request_to_cloud(session, relations, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_SKILL, Operation.ADD, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "addAgentSkillRels", "addAgentSkillRels")


@cloud_api(DataType.AGENT_SKILL, Operation.UPDATE)
def send_update_agent_skill_relations_request_to_cloud(session, relations, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_SKILL, Operation.UPDATE, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "updateAgentSkillRels", "updateAgentSkillRels")


@cloud_api(DataType.AGENT_SKILL, Operation.DELETE)
def send_remove_agent_skill_relations_request_to_cloud(session, removes, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_SKILL, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "removeAgentSkillRels", "removeAgentSkillRels")


@cloud_api(DataType.AGENT_SKILL, Operation.QUERY)
def send_query_agent_skill_relations_request_to_cloud(session, token, q_settings, endpoint):
    queryInfo = gen_query_agent_skills_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentSkillRels", "queryAgentSkillRels")


# ============================================================================
# Direct Lambda mutation wrappers for skill subscription
# These call the Lambda GraphQL mutations (subscribeToSkill / unsubscribeFromSkill)
# which operate on the agent_skill_rels table in Aurora.
# ============================================================================

@cloud_api(DataType.AGENT_SKILL, Operation.SUBSCRIBE)
def send_subscribe_to_skill_request(session, token, endpoint, skill_id: str, owner: str, timeout=60):
    """Call Lambda subscribeToSkill mutation to create agent_skill_rels record."""
    mutation = """
    mutation {
      subscribeToSkill(skillId: "%s", owner: "%s") {
        id
        success
        error
      }
    }
    """ % (skill_id, owner)
    jresp = appsync_http_request(mutation, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "subscribeToSkill", "subscribeToSkill")


@cloud_api(DataType.AGENT_SKILL, Operation.UNSUBSCRIBE)
def send_unsubscribe_from_skill_request(session, token, endpoint, skill_id: str, owner: str, timeout=60):
    """Call Lambda unsubscribeFromSkill mutation to remove agent_skill_rels record."""
    mutation = """
    mutation {
      unsubscribeFromSkill(skillId: "%s", owner: "%s") {
        id
        success
        error
      }
    }
    """ % (skill_id, owner)
    jresp = appsync_http_request(mutation, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "unsubscribeFromSkill", "unsubscribeFromSkill")


# ============================================================================
# Skill Marketplace / Statistics Operations (via Lambda GraphQL)
# ============================================================================

def _cloud_graphql_query(query_str: str, session, token, endpoint: str, timeout: int = 60):
    """Internal: Execute a GraphQL query/mutation via AppSync and return parsed data."""
    jresp = appsync_http_request(query_str, session, token, endpoint, timeout)
    return jresp


def cloud_get_skill_marketplace_stats(skill_id: str, session, token, endpoint: str, timeout: int = 60):
    """Query skill marketplace statistics (downloads, favorites, subscribers, rating, reviews, trending).

    Lambda GraphQL query: query { getSkillMarketplaceStats(skillId: "...") { ... } }
    """
    query = """
    query {
      getSkillMarketplaceStats(skillId: "%s") {
        downloadCount
        favoriteCount
        subscriberCount
        rating
        reviewCount
        trendingScore
      }
    }
    """ % skill_id
    jresp = _cloud_graphql_query(query, session, token, endpoint, timeout)
    if isinstance(jresp, dict) and "data" in jresp:
        return (jresp["data"].get("getSkillMarketplaceStats") or {})
    return {}


def cloud_toggle_skill_favorite(skill_id: str, owner: str, session, token, endpoint: str, timeout: int = 60):
    """Toggle skill favorite status.

    Lambda GraphQL mutation: mutation { toggleSkillFavorite(skillId: "...", owner: "...") { favorited success error } }
    """
    mutation = """
    mutation {
      toggleSkillFavorite(skillId: "%s", owner: "%s") {
        favorited
        success
        error
      }
    }
    """ % (skill_id, owner)
    jresp = _cloud_graphql_query(mutation, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "toggleSkillFavorite", "toggleSkillFavorite")


def cloud_get_skill_reviews(skill_id: str, session, token, endpoint: str, limit: int = 20, timeout: int = 60):
    """Query skill reviews.

    Lambda GraphQL query: query { getSkillReviews(skillId: "...", limit: N) { ... } }
    """
    query = """
    query {
      getSkillReviews(skillId: "%s", limit: %d) {
        reviews {
          id
          owner
          rating
          comment
          helpfulCount
          createdAt
        }
        totalCount
      }
    }
    """ % (skill_id, limit)
    jresp = _cloud_graphql_query(query, session, token, endpoint, timeout)
    if isinstance(jresp, dict) and "data" in jresp:
        return (jresp["data"].get("getSkillReviews") or {})
    return {}


def cloud_upsert_skill_review(skill_id: str, owner: str, rating: int, comment: str,
                              session, token, endpoint: str, timeout: int = 60):
    """Add or update a skill review.

    Lambda GraphQL mutation: mutation { upsertSkillReview(skillId: "...", owner: "...", rating: N, comment: "...") { ... } }
    """
    escaped_comment = comment.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    mutation = """
    mutation {
      upsertSkillReview(skillId: "%s", owner: "%s", rating: %d, comment: "%s") {
        id
        success
        error
      }
    }
    """ % (skill_id, owner, rating, escaped_comment)
    jresp = _cloud_graphql_query(mutation, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "upsertSkillReview", "upsertSkillReview")


def cloud_increment_skill_download(skill_id: str, amount: int, session, token, endpoint: str, timeout: int = 60):
    """Increment skill download count.

    Lambda GraphQL mutation: mutation { incrementSkillDownload(skillId: "...", amount: N) { success error } }
    """
    mutation = """
    mutation {
      incrementSkillDownload(skillId: "%s", amount: %d) {
        success
        error
      }
    }
    """ % (skill_id, amount)
    jresp = _cloud_graphql_query(mutation, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "incrementSkillDownload", "incrementSkillDownload")


def cloud_get_skill_changelog(skill_id: str, session, token, endpoint: str, timeout: int = 60):
    """Query skill changelog entries.

    Lambda GraphQL query: query { getSkillChangelog(skillId: "...") { entries { version date notes } } }
    """
    query = """
    query {
      getSkillChangelog(skillId: "%s") {
        entries {
          version
          date
          notes
        }
      }
    }
    """ % skill_id
    jresp = _cloud_graphql_query(query, session, token, endpoint, timeout)
    if isinstance(jresp, dict) and "data" in jresp:
        return (jresp["data"].get("getSkillChangelog") or {})
    return {}


def cloud_append_skill_changelog(skill_id: str, version: str, notes: str,
                                  session, token, endpoint: str, timeout: int = 60):
    """Append a new changelog entry to a skill.

    Lambda GraphQL mutation: mutation { appendSkillChangelog(skillId: "...", version: "...", notes: "...") { success error } }
    """
    escaped_notes = notes.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    mutation = """
    mutation {
      appendSkillChangelog(skillId: "%s", version: "%s", notes: "%s") {
        success
        error
      }
    }
    """ % (skill_id, version, escaped_notes)
    jresp = _cloud_graphql_query(mutation, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "appendSkillChangelog", "appendSkillChangelog")


def cloud_list_similar_skills(skill_id: str, limit: int, session, token, endpoint: str, timeout: int = 60):
    """Query similar skills.

    Lambda GraphQL query: query { listSimilarSkills(skillId: "...", limit: N) { skills { ... } } }
    """
    query = """
    query {
      listSimilarSkills(skillId: "%s", limit: %d) {
        skills {
          id
          name
          description
          version
          rating
          downloadCount
          owner
          tags
          level
        }
      }
    }
    """ % (skill_id, limit)
    jresp = _cloud_graphql_query(query, session, token, endpoint, timeout)
    if isinstance(jresp, dict) and "data" in jresp:
        return (jresp["data"].get("listSimilarSkills") or {})
    return {}


def cloud_list_skills_by_owner(owner: str, exclude_id: str, limit: int,
                                session, token, endpoint: str, timeout: int = 60):
    """Query skills by owner.

    Lambda GraphQL query: query { listSkillsByOwner(owner: "...", excludeId: "...", limit: N) { skills { ... } } }
    """
    query = """
    query {
      listSkillsByOwner(owner: "%s", excludeId: "%s", limit: %d) {
        skills {
          id
          name
          description
          version
          downloadCount
          owner
          tags
          level
        }
      }
    }
    """ % (owner, exclude_id, limit)
    jresp = _cloud_graphql_query(query, session, token, endpoint, timeout)
    if isinstance(jresp, dict) and "data" in jresp:
        return (jresp["data"].get("listSkillsByOwner") or {})
    return {}


def cloud_report_skill(skill_id: str, reporter: str, reason: str, note: str,
                       session, token, endpoint: str, timeout: int = 60):
    """Report a skill for abuse.

    Lambda GraphQL mutation: mutation { reportSkill(skillId: "...", reporter: "...", reason: "...", note: "...") { success error } }
    """
    escaped_reason = reason.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    escaped_note = note.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    mutation = """
    mutation {
      reportSkill(skillId: "%s", reporter: "%s", reason: "%s", note: "%s") {
        success
        error
      }
    }
    """ % (skill_id, reporter, escaped_reason, escaped_note)
    jresp = _cloud_graphql_query(mutation, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "reportSkill", "reportSkill")


def cloud_get_public_skills(session, token, endpoint: str, timeout: int = 120):
    """Query all public skills from cloud.

    Lambda GraphQL query: query { getPublicSkills { skills { ... } } }
    """
    query = """
    query {
      getPublicSkills {
        skills {
          id
          askid
          name
          description
          version
          owner
          public
          source
          level
          tags
          rating
          downloadCount
          favoriteCount
          subscriberCount
          trendingScore
          changelog
          updatedAt
          createdAt
        }
      }
    }
    """
    jresp = _cloud_graphql_query(query, session, token, endpoint, timeout)
    if isinstance(jresp, dict) and "data" in jresp:
        raw = jresp["data"].get("getPublicSkills")
        # Lambda can return { skills: [...] } or a bare [...] array
        if isinstance(raw, list):
            return {"skills": raw}
        if isinstance(raw, dict):
            return raw if "skills" in raw else {"skills": []}
    return {"skills": []}


# ============================================================================
# Skill Entity Operations
# ============================================================================

@cloud_api(DataType.SKILL, Operation.ADD)
def send_add_skills_request_to_cloud(session, skills, token, endpoint, timeout=180):
    """Add Skill entities (skill data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    
    logger.info(f"[Skill ADD] Sending addAgentSkills mutation for {len(skills)} skill(s)")
    mutationInfo = build_mutation(DataType.SKILL, Operation.ADD, skills)
    logger.debug(f"[Skill ADD] Mutation: {mutationInfo[:500]}...")
    
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    logger.info(f"[Skill ADD] Received response from server")
    logger.debug(f"[Skill ADD] Raw response: {json.dumps(jresp, default=str)[:1500]}")
    
    results = safe_parse_response(jresp, "addAgentSkills", "addAgentSkills")
    
    # Log upload_urls if present
    if isinstance(results, list):
        logger.info(f"[Skill ADD] Parsed {len(results)} result(s)")
        for i, result in enumerate(results):
            skill_id = result.get('id', 'unknown')
            success = result.get('success', False)
            upload_urls = result.get('upload_urls')
            logger.info(f"[Skill ADD] Result[{i}]: id={skill_id}, success={success}, has_upload_urls={bool(upload_urls)}")
            if upload_urls:
                # Parse if string
                if isinstance(upload_urls, str):
                    try:
                        upload_urls = json.loads(upload_urls)
                    except:
                        pass
                logger.info(f"[Skill ADD] upload_urls structure: {json.dumps(upload_urls, default=str)[:800]}")
    
    return results


@cloud_api(DataType.SKILL, Operation.UPDATE)
def send_update_skills_request_to_cloud(session, skills, token, endpoint):
    """Update Skill entities (skill data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    
    logger.info(f"[Skill UPDATE] Sending updateAgentSkills mutation for {len(skills)} skill(s)")
    mutationInfo = build_mutation(DataType.SKILL, Operation.UPDATE, skills)
    logger.debug(f"[Skill UPDATE] Mutation: {mutationInfo[:500]}...")
    
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    logger.info(f"[Skill UPDATE] Received response from server")
    logger.debug(f"[Skill UPDATE] Raw response: {json.dumps(jresp, default=str)[:1500]}")
    
    results = safe_parse_response(jresp, "updateAgentSkills", "updateAgentSkills")
    
    # Log upload_urls if present
    if isinstance(results, list):
        logger.info(f"[Skill UPDATE] Parsed {len(results)} result(s)")
        for i, result in enumerate(results):
            skill_id = result.get('id', 'unknown')
            success = result.get('success', False)
            upload_urls = result.get('upload_urls')
            logger.info(f"[Skill UPDATE] Result[{i}]: id={skill_id}, success={success}, has_upload_urls={bool(upload_urls)}")
            if upload_urls:
                if isinstance(upload_urls, str):
                    try:
                        upload_urls = json.loads(upload_urls)
                    except:
                        pass
                logger.info(f"[Skill UPDATE] upload_urls structure: {json.dumps(upload_urls, default=str)[:800]}")
    
    return results


@cloud_api(DataType.SKILL, Operation.DELETE)
def send_remove_skills_request_to_cloud(session, removes, token, endpoint):
    """Remove Skill entities (skill data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.SKILL, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "removeAgentSkills", "removeAgentSkills")


# ============================================================================
# Skill File Upload Utilities
# ============================================================================

def collect_skill_files(skill_directory: str) -> list:
    """
    Recursively collect all files under the skill directory.
    
    Args:
        skill_directory: Absolute path to the skill directory
        
    Returns:
        List of relative file paths (relative to skill_directory)
    """
    import glob
    
    if not os.path.isdir(skill_directory):
        logger.warning(f"[SkillFiles] Skill directory not found: {skill_directory}")
        return []
    
    all_files = []
    for root, dirs, files in os.walk(skill_directory):
        for file in files:
            abs_path = os.path.join(root, file)
            rel_path = os.path.relpath(abs_path, skill_directory)
            # Normalize path separators to forward slashes
            rel_path = rel_path.replace("\\", "/")
            all_files.append(rel_path)
    
    logger.debug(f"[SkillFiles] Collected {len(all_files)} files from {skill_directory}")
    return all_files


def build_skill_source_string(file_paths: list) -> str:
    """
    Build comma-separated source string from file paths.

    IMPORTANT: This 'source' is a Python-side convenience field used for file upload
    tracking (comma-separated code filenames like "a.py,b.py,c.py"). It is NOT the
    SkillSource enum ('ui' | 'code' | 'subscribed' | 'external') used in the database
    and GraphQL schema. See SkillSource in constants.py for the authoritative enum.

    Args:
        file_paths: List of relative file paths
        
    Returns:
        Comma-separated string of file paths
    """
    return ",".join(file_paths)


def prepare_skill_with_source(skill_data: dict, skill_directory: str = None) -> dict:
    """
    Prepare skill data with source attribute containing CODE file paths only.

    IMPORTANT: The 'source' attribute set here is a Python-side field used for
    file upload tracking (comma-separated code filenames like "a.py,b.py,c.py").
    It is NOT the SkillSource enum ('ui' | 'code' | 'subscribed' | 'external')
    used in the database and GraphQL schema. These are two completely different
    uses of the same field name:
      - Python-side (this function): source = "a.py,b.py"   → used for upload tracking
      - Database/GraphQL:            source = 'ui'|'code'|... → skill origin classification
    See SkillSource in constants.py for the authoritative enum definition.

    The 'source' field should only contain code files (e.g., .py files).
    Diagram JSON, bundle, and data_mapping files are handled separately via upload_urls.
    
    Args:
        skill_data: Original skill data dictionary
            - If 'source' is already set (comma-separated code filenames), use it
            - Otherwise, auto-detect .py files in skill_directory
        skill_directory: Path to skill directory (if None, uses skill_data['path'])
        
    Returns:
        Skill data with 'source' attribute populated (code files only)
    """
    skill = skill_data.copy()
    
    # If source is already provided (comma-separated code filenames), use it as-is
    existing_source = skill.get('source', '')
    if existing_source:
        logger.info(f"[SkillFiles] Using provided source: {existing_source}")
        return skill
    
    # Determine skill directory
    if skill_directory is None:
        skill_directory = skill.get('path', '')
    
    # Auto-detect code files (.py) only - NOT diagram or data_mapping files
    if skill_directory and os.path.isdir(skill_directory):
        # Only collect .py files at the root level (not in subdirectories)
        code_files = [f for f in os.listdir(skill_directory) 
                      if f.endswith('.py') and os.path.isfile(os.path.join(skill_directory, f))]
        if code_files:
            skill['source'] = ','.join(code_files)
            logger.info(f"[SkillFiles] Auto-detected {len(code_files)} code files: {skill['source']}")
        else:
            skill['source'] = ''
            logger.info(f"[SkillFiles] No code files found in {skill_directory}")
    else:
        skill['source'] = ''
        logger.debug(f"[SkillFiles] No valid skill directory for code file detection")
    
    return skill


def upload_skill_files_with_presigned_urls(
    session, 
    skill_directory: str, 
    presigned_urls: list, 
    file_paths: list
) -> dict:
    """
    Upload skill files using presigned URLs returned from cloud.
    
    Args:
        session: Requests session
        skill_directory: Absolute path to skill directory
        presigned_urls: List of presigned URL objects from cloud response
        file_paths: List of relative file paths (matching order with presigned_urls)
        
    Returns:
        Dict with upload results: {'success': [...], 'failed': [...]}
    """
    results = {'success': [], 'failed': []}
    
    if len(presigned_urls) != len(file_paths):
        logger.warning(f"[SkillUpload] Mismatch: {len(presigned_urls)} URLs vs {len(file_paths)} files")
    
    for i, (url_info, rel_path) in enumerate(zip(presigned_urls, file_paths)):
        abs_path = os.path.join(skill_directory, rel_path)
        
        if not os.path.isfile(abs_path):
            logger.warning(f"[SkillUpload] File not found: {abs_path}")
            results['failed'].append({'path': rel_path, 'error': 'File not found'})
            continue
        
        try:
            # Upload using presigned URL
            resp = send_file_with_presigned_url(abs_path, url_info)
            results['success'].append({'path': rel_path, 'response': resp})
            logger.debug(f"[SkillUpload] Uploaded {rel_path}")
        except Exception as e:
            logger.error(f"[SkillUpload] Failed to upload {rel_path}: {e}")
            results['failed'].append({'path': rel_path, 'error': str(e)})
    
    logger.info(f"[SkillUpload] Upload complete: {len(results['success'])} success, {len(results['failed'])} failed")
    return results


def upload_skill_files_with_upload_urls(
    skill_directory: str,
    upload_urls: dict,
    skill_name: str = '',
    diagram_subdir: str = 'diagram_dir',
    source_files: str = ''
) -> dict:
    """
    Upload skill files using the new upload_urls format from SkillMutationResult.
    
    The upload_urls structure from cloud:
    {
        "diagram": {
            "json": { "key": "...", "url": "..." },
            "bundle": { "key": "...", "url": "..." }
        },
        "code": [],  # Array of { "key": "...", "url": "..." } for code files
        "data_mapping": { "key": "...", "url": "..." }
    }
    
    File structure:
        {skill_directory}/
            - data_mapping.json (if exists)
            - {diagram_subdir}/{skill_name}.json (diagram JSON)
            - {diagram_subdir}/{skill_name}_bundle.json (diagram bundle)
            - {source_files} (comma-separated code file names, e.g., "a.py,b.py,c.py")
    
    Args:
        skill_directory: Absolute path to skill directory (e.g., my_skills/skill_name/)
        upload_urls: The upload_urls dict from SkillMutationResult
        skill_name: Name of the skill (used to find diagram files)
        diagram_subdir: Subdirectory containing diagram files (default: 'diagram_dir')
        source_files: Comma-separated list of code file names to upload
        
    Returns:
        Dict with upload results for each file type
    """
    results = {
        'diagram_json': None,
        'diagram_bundle': None,
        'data_mapping': None,
        'code': [],
        'errors': []
    }
    
    if not upload_urls:
        logger.warning("[SkillUpload] No upload_urls provided")
        return results
    
    # Parse upload_urls if it's a string (AWSJSON)
    if isinstance(upload_urls, str):
        try:
            upload_urls = json.loads(upload_urls)
        except json.JSONDecodeError as e:
            logger.error(f"[SkillUpload] Failed to parse upload_urls JSON: {e}")
            results['errors'].append(f"Failed to parse upload_urls: {e}")
            return results
    
    logger.info(f"[SkillUpload] Processing upload_urls for skill: {skill_name}")
    logger.info(f"[SkillUpload] skill_directory={skill_directory}, diagram_subdir={diagram_subdir}, source_files={source_files}")
    logger.debug(f"[SkillUpload] upload_urls structure: {json.dumps(upload_urls, default=str)[:500]}")
    
    # Build diagram directory path
    diagram_dir = os.path.join(skill_directory, diagram_subdir)
    logger.info(f"[SkillUpload] Diagram directory: {diagram_dir} (exists={os.path.isdir(diagram_dir)})")
    
    # 1. Upload diagram JSON: {diagram_subdir}/{skill_name}.json
    diagram_urls = upload_urls.get('diagram', {})
    if diagram_urls.get('json'):
        json_url_info = diagram_urls['json']
        presigned_url = json_url_info.get('url')
        if presigned_url:
            # Use skill_name to find the exact file: {skill_name}.json
            json_filename = f"{skill_name}.json" if skill_name else None
            json_path = os.path.join(diagram_dir, json_filename) if json_filename else None
            
            # Fallback: search for *_skill.json if exact file not found
            if not json_path or not os.path.isfile(json_path):
                json_files = [f for f in os.listdir(diagram_dir) if f.endswith('.json')] if os.path.isdir(diagram_dir) else []
                if json_files:
                    json_path = os.path.join(diagram_dir, json_files[0])
                    logger.info(f"[SkillUpload] Using fallback diagram JSON: {json_files[0]}")
            
            if json_path and os.path.isfile(json_path):
                logger.info(f"[SkillUpload] 📤 Uploading diagram JSON: {json_path}")
                result = upload_file_to_presigned_url(json_path, presigned_url, 'application/json')
                results['diagram_json'] = result
                logger.info(f"[SkillUpload] Diagram JSON upload result: {result}")
            else:
                logger.warning(f"[SkillUpload] Diagram JSON file not found: {json_path}")
                results['errors'].append(f"Diagram JSON file not found: {json_filename}")
    
    # 2. Upload diagram bundle: {diagram_subdir}/{skill_name}_bundle.json
    if diagram_urls.get('bundle'):
        bundle_url_info = diagram_urls['bundle']
        presigned_url = bundle_url_info.get('url')
        if presigned_url:
            # Use skill_name to find the exact file: {skill_name}_bundle.json
            bundle_filename = f"{skill_name}_bundle.json" if skill_name else None
            bundle_path = os.path.join(diagram_dir, bundle_filename) if bundle_filename else None
            
            # Fallback: search for *_bundle.json if exact file not found
            if not bundle_path or not os.path.isfile(bundle_path):
                bundle_files = [f for f in os.listdir(diagram_dir) if f.endswith('_bundle.json')] if os.path.isdir(diagram_dir) else []
                if bundle_files:
                    bundle_path = os.path.join(diagram_dir, bundle_files[0])
                    logger.info(f"[SkillUpload] Using fallback diagram bundle: {bundle_files[0]}")
            
            if bundle_path and os.path.isfile(bundle_path):
                logger.info(f"[SkillUpload] 📤 Uploading diagram bundle: {bundle_path}")
                result = upload_file_to_presigned_url(bundle_path, presigned_url, 'application/octet-stream')
                results['diagram_bundle'] = result
                logger.info(f"[SkillUpload] Diagram bundle upload result: {result}")
            else:
                logger.warning(f"[SkillUpload] Diagram bundle file not found: {bundle_path}")
                results['errors'].append(f"Diagram bundle file not found: {bundle_filename}")
    
    # 3. Upload data_mapping.json (at skill root directory)
    data_mapping_url_info = upload_urls.get('data_mapping', {})
    if data_mapping_url_info.get('url'):
        presigned_url = data_mapping_url_info['url']
        data_mapping_path = os.path.join(skill_directory, 'data_mapping.json')
        if os.path.isfile(data_mapping_path):
            logger.info(f"[SkillUpload] 📤 Uploading data_mapping.json: {data_mapping_path}")
            result = upload_file_to_presigned_url(data_mapping_path, presigned_url, 'application/json')
            results['data_mapping'] = result
            logger.info(f"[SkillUpload] Data mapping upload result: {result}")
        else:
            logger.info(f"[SkillUpload] data_mapping.json not found at {data_mapping_path} (optional)")
    
    # 4. Upload code files (from source_files parameter - comma-separated filenames)
    # Code files are in code_dir/ subdirectory
    code_urls = upload_urls.get('code', [])
    if code_urls and isinstance(code_urls, list):
        # Parse source_files: comma-separated list of filenames (e.g., "a.py,b.py,c.py")
        code_file_list = [f.strip() for f in source_files.split(',') if f.strip()] if source_files else []
        code_dir = os.path.join(skill_directory, 'code_dir')
        logger.info(f"[SkillUpload] Code directory: {code_dir} (exists={os.path.isdir(code_dir)})")
        logger.info(f"[SkillUpload] Code files to upload: {code_file_list}")
        
        for i, code_url_info in enumerate(code_urls):
            if i < len(code_file_list):
                presigned_url = code_url_info.get('url')
                code_filename = code_file_list[i]
                if presigned_url and code_filename:
                    # Look for code file in code_dir/ subdirectory
                    code_path = os.path.join(code_dir, code_filename)
                    # Fallback to skill root if not in code_dir
                    if not os.path.isfile(code_path):
                        code_path = os.path.join(skill_directory, code_filename)
                    
                    if os.path.isfile(code_path):
                        logger.info(f"[SkillUpload] 📤 Uploading code file: {code_path}")
                        result = upload_file_to_presigned_url(code_path, presigned_url, 'text/x-python')
                        results['code'].append({'file': code_filename, 'result': result})
                        logger.info(f"[SkillUpload] Code file upload result: {result}")
                    else:
                        logger.warning(f"[SkillUpload] Code file not found: {code_path}")
                        results['errors'].append(f"Code file not found: {code_filename}")
    
    # Summary
    success_count = sum([
        1 if results['diagram_json'] and results['diagram_json'].get('success') else 0,
        1 if results['diagram_bundle'] and results['diagram_bundle'].get('success') else 0,
        1 if results['data_mapping'] and results['data_mapping'].get('success') else 0,
        sum(1 for c in results['code'] if c.get('result', {}).get('success'))
    ])
    logger.info(f"[SkillUpload] Upload complete: {success_count} files uploaded successfully")
    
    return results


def send_add_skills_with_files_to_cloud(
    session, 
    skills: list, 
    token: str, 
    endpoint: str, 
    timeout: int = 180,
    upload_files: bool = True
) -> dict:
    """
    Add skills to cloud with file upload support.
    
    This function:
    1. Prepares each skill with source attribute (comma-separated file paths)
    2. Sends add request to cloud
    3. Parses upload_urls from response (new SkillMutationResult format)
    4. Uploads files using presigned URLs
    
    Args:
        session: Requests session
        skills: List of skill data dicts (each should have 'path' pointing to skill directory)
        token: Auth token
        endpoint: AppSync endpoint
        timeout: Request timeout
        upload_files: If True, automatically upload files using presigned URLs
        
    Returns:
        Dict with cloud response and file upload results
    """
    from agent.cloud_api.graphql_builder import build_mutation
    
    logger.info(f"[Skill ADD] Sending addAgentSkills mutation for {len(skills)} skill(s)")
    
    # Step 1: Prepare skills with source attribute
    prepared_skills = []
    skill_file_map = {}  # Map skill ID to directory info for later upload
    
    for skill in skills:
        # Derive skill directory from diagram field or path
        # diagram: {"dir": "diagram_dir", "local_dir": "my_skills/"} 
        # Skill files are at: {local_dir}/{skill_name}/
        #   - data_mapping.json (if exists)
        #   - {diagram_dir}/{skill_name}.json
        #   - {diagram_dir}/{skill_name}_bundle.json
        # Code files from "source" attribute (comma-separated filenames)
        
        skill_name = skill.get('name', '')
        diagram = skill.get('diagram', {})
        source = skill.get('source', '')  # comma-separated code file names
        
        # Build skill directory path
        skill_dir = skill.get('path', '')
        if not skill_dir and diagram:
            local_dir = diagram.get('local_dir', 'my_skills/')
            if skill_name:
                skill_dir = os.path.join(local_dir, skill_name)
                # Convert relative path to absolute if needed
                if not os.path.isabs(skill_dir):
                    skill_dir = os.path.abspath(skill_dir)
                logger.info(f"[Skill ADD] Derived skill_dir from diagram: {skill_dir}")
        
        prepared_skill = prepare_skill_with_source(skill, skill_dir)
        prepared_skills.append(prepared_skill)
        
        # Store directory info for upload
        skill_id = prepared_skill.get('askid') or prepared_skill.get('id', '')
        if skill_dir and os.path.isdir(skill_dir):
            diagram_subdir = diagram.get('dir', 'diagram_dir') if diagram else 'diagram_dir'
            skill_file_map[skill_id] = {
                'dir': skill_dir,
                'name': skill_name,
                'diagram_subdir': diagram_subdir,
                'source': source  # comma-separated code file names
            }
            logger.info(f"[Skill ADD] Mapped skill {skill_id} to directory: {skill_dir} (diagram_subdir={diagram_subdir})")
        else:
            logger.warning(f"[Skill ADD] Skill directory not found: {skill_dir}")
    
    # Step 2: Send add request to cloud
    mutationInfo = build_mutation(DataType.SKILL, Operation.ADD, prepared_skills)
    logger.debug(f"[Skill ADD] Mutation: {mutationInfo[:500]}...")
    
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    logger.info(f"[Skill ADD] Received response from server")
    logger.debug(f"[Skill ADD] Raw response: {json.dumps(jresp, default=str)[:1000]}")
    
    cloud_response = safe_parse_response(jresp, "addAgentSkills", "addAgentSkills")
    logger.info(f"[Skill ADD] Parsed {len(cloud_response) if isinstance(cloud_response, list) else 1} result(s)")
    
    # Step 3: Parse upload_urls and upload files (new SkillMutationResult format)
    upload_results = {}
    
    if upload_files and isinstance(cloud_response, list):
        logger.info(f"[Skill ADD] Processing upload_urls from response")
        logger.info(f"[Skill ADD] skill_file_map keys: {list(skill_file_map.keys())}")
        
        for i, result in enumerate(cloud_response):
            skill_id = result.get('id', '')
            success = result.get('success', False)
            upload_urls_raw = result.get('upload_urls')
            
            # Parse upload_urls if it's a JSON string (AWSJSON comes as string)
            upload_urls = None
            if upload_urls_raw:
                if isinstance(upload_urls_raw, str):
                    try:
                        upload_urls = json.loads(upload_urls_raw)
                        logger.info(f"[Skill ADD] Parsed upload_urls from JSON string")
                    except json.JSONDecodeError as e:
                        logger.error(f"[Skill ADD] Failed to parse upload_urls JSON: {e}")
                        upload_urls = None
                elif isinstance(upload_urls_raw, dict):
                    upload_urls = upload_urls_raw
            
            logger.info(f"[Skill ADD] Result[{i}]: id={skill_id}, success={success}, has_upload_urls={bool(upload_urls)}")
            logger.info(f"[Skill ADD] skill_id '{skill_id}' in skill_file_map: {skill_id in skill_file_map}")
            
            if success and upload_urls and skill_id in skill_file_map:
                skill_info = skill_file_map[skill_id]
                skill_dir = skill_info['dir']
                skill_name = skill_info['name']
                diagram_subdir = skill_info['diagram_subdir']
                source_files = skill_info['source']
                logger.info(f"[Skill ADD] 📤 Uploading files for skill {skill_id} from {skill_dir}")
                logger.info(f"[Skill ADD] skill_name={skill_name}, diagram_subdir={diagram_subdir}, source={source_files}")
                upload_result = upload_skill_files_with_upload_urls(
                    skill_dir, upload_urls, skill_name, diagram_subdir, source_files
                )
                upload_results[skill_id] = upload_result
                result['file_upload_results'] = upload_result
            elif upload_urls:
                logger.warning(f"[Skill ADD] Skipping upload: success={success}, skill_id_in_map={skill_id in skill_file_map}")
                logger.debug(f"[Skill ADD] upload_urls content: {json.dumps(upload_urls, default=str)[:500]}")
    
    # Legacy format handling (for backwards compatibility)
    elif isinstance(cloud_response, dict):
        if 'presigned_urls' in cloud_response:
            for skill_id, url_list in cloud_response.get('presigned_urls', {}).items():
                if skill_id in skill_file_map:
                    skill_dir = skill_file_map[skill_id]
                    files = collect_skill_files(skill_dir)
                    upload_result = upload_skill_files_with_presigned_urls(
                        session, skill_dir, url_list, files
                    )
                    upload_results[skill_id] = upload_result
    
    logger.info(f"[Skill ADD] Completed with {len(upload_results)} skill(s) uploaded")
    
    return {
        'cloud_response': cloud_response,
        'upload_results': upload_results,
        'skills_processed': len(prepared_skills)
    }


def send_update_skills_with_files_to_cloud(
    session, 
    skills: list, 
    token: str, 
    endpoint: str, 
    timeout: int = 180,
    upload_files: bool = True
) -> dict:
    """
    Update skills in cloud with file upload support.
    
    Similar to send_add_skills_with_files_to_cloud but for updates.
    
    Args:
        session: Requests session
        skills: List of skill data dicts
        token: Auth token
        endpoint: AppSync endpoint
        timeout: Request timeout
        upload_files: If True, automatically upload files using presigned URLs
        
    Returns:
        Dict with cloud response and file upload results
    """
    from agent.cloud_api.graphql_builder import build_mutation
    
    logger.info(f"[Skill UPDATE] Sending updateAgentSkills mutation for {len(skills)} skill(s)")
    
    # Step 1: Prepare skills with source attribute
    prepared_skills = []
    skill_file_map = {}  # Map skill ID to directory info for later upload
    
    for skill in skills:
        # Derive skill directory from diagram field or path
        # diagram: {"dir": "diagram_dir", "local_dir": "my_skills/"} 
        # Skill files are at: {local_dir}/{skill_name}/
        skill_name = skill.get('name', '')
        diagram = skill.get('diagram', {})
        source = skill.get('source', '')  # comma-separated code file names
        
        # Build skill directory path
        skill_dir = skill.get('path', '')
        if not skill_dir and diagram:
            local_dir = diagram.get('local_dir', 'my_skills/')
            if skill_name:
                skill_dir = os.path.join(local_dir, skill_name)
                # Convert relative path to absolute if needed
                if not os.path.isabs(skill_dir):
                    skill_dir = os.path.abspath(skill_dir)
                logger.info(f"[Skill UPDATE] Derived skill_dir from diagram: {skill_dir}")
        
        prepared_skill = prepare_skill_with_source(skill, skill_dir)
        prepared_skills.append(prepared_skill)
        
        skill_id = prepared_skill.get('askid') or prepared_skill.get('id', '')
        if skill_dir and os.path.isdir(skill_dir):
            diagram_subdir = diagram.get('dir', 'diagram_dir') if diagram else 'diagram_dir'
            skill_file_map[skill_id] = {
                'dir': skill_dir,
                'name': skill_name,
                'diagram_subdir': diagram_subdir,
                'source': source
            }
            logger.info(f"[Skill UPDATE] Mapped skill {skill_id} to directory: {skill_dir} (diagram_subdir={diagram_subdir})")
        else:
            logger.warning(f"[Skill UPDATE] Skill directory not found: {skill_dir}")
    
    # Step 2: Send update request to cloud
    mutationInfo = build_mutation(DataType.SKILL, Operation.UPDATE, prepared_skills)
    logger.debug(f"[Skill UPDATE] Mutation: {mutationInfo[:500]}...")
    
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    logger.info(f"[Skill UPDATE] Received response from server")
    logger.debug(f"[Skill UPDATE] Raw response: {json.dumps(jresp, default=str)[:1000]}")
    
    cloud_response = safe_parse_response(jresp, "updateAgentSkills", "updateAgentSkills")
    logger.info(f"[Skill UPDATE] Parsed {len(cloud_response) if isinstance(cloud_response, list) else 1} result(s)")
    
    # Step 3: Parse upload_urls and upload files (new SkillMutationResult format)
    upload_results = {}
    
    if upload_files and isinstance(cloud_response, list):
        logger.info(f"[Skill UPDATE] Processing upload_urls from response")
        logger.info(f"[Skill UPDATE] skill_file_map keys: {list(skill_file_map.keys())}")
        
        for i, result in enumerate(cloud_response):
            skill_id = result.get('id', '')
            success = result.get('success', False)
            upload_urls_raw = result.get('upload_urls')
            
            # Parse upload_urls if it's a JSON string (AWSJSON comes as string)
            upload_urls = None
            if upload_urls_raw:
                if isinstance(upload_urls_raw, str):
                    try:
                        upload_urls = json.loads(upload_urls_raw)
                        logger.info(f"[Skill UPDATE] Parsed upload_urls from JSON string")
                    except json.JSONDecodeError as e:
                        logger.error(f"[Skill UPDATE] Failed to parse upload_urls JSON: {e}")
                        upload_urls = None
                elif isinstance(upload_urls_raw, dict):
                    upload_urls = upload_urls_raw
            
            logger.info(f"[Skill UPDATE] Result[{i}]: id={skill_id}, success={success}, has_upload_urls={bool(upload_urls)}")
            logger.info(f"[Skill UPDATE] skill_id '{skill_id}' in skill_file_map: {skill_id in skill_file_map}")
            
            if success and upload_urls and skill_id in skill_file_map:
                skill_info = skill_file_map[skill_id]
                skill_dir = skill_info['dir']
                skill_name = skill_info['name']
                diagram_subdir = skill_info['diagram_subdir']
                source_files = skill_info['source']
                logger.info(f"[Skill UPDATE] 📤 Uploading files for skill {skill_id} from {skill_dir}")
                logger.info(f"[Skill UPDATE] skill_name={skill_name}, diagram_subdir={diagram_subdir}, source={source_files}")
                upload_result = upload_skill_files_with_upload_urls(
                    skill_dir, upload_urls, skill_name, diagram_subdir, source_files
                )
                upload_results[skill_id] = upload_result
                result['file_upload_results'] = upload_result
            elif upload_urls:
                logger.warning(f"[Skill UPDATE] Skipping upload: success={success}, skill_id_in_map={skill_id in skill_file_map}")
                logger.debug(f"[Skill UPDATE] upload_urls content: {json.dumps(upload_urls, default=str)[:500]}")
    
    # Legacy format handling (for backwards compatibility)
    elif isinstance(cloud_response, dict):
        if 'presigned_urls' in cloud_response:
            for skill_id, url_list in cloud_response.get('presigned_urls', {}).items():
                if skill_id in skill_file_map:
                    skill_dir = skill_file_map[skill_id]
                    files = collect_skill_files(skill_dir)
                    upload_result = upload_skill_files_with_presigned_urls(
                        session, skill_dir, url_list, files
                    )
                    upload_results[skill_id] = upload_result
    
    logger.info(f"[Skill UPDATE] Completed with {len(upload_results)} skill(s) uploaded")
    
    return {
        'cloud_response': cloud_response,
        'upload_results': upload_results,
        'skills_processed': len(prepared_skills)
    }


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_agent_skills_request_to_cloud(session, token, endpoint, public_catalog: bool = False):
    """Query skills using queryAgentSkills.

    Server returns [AgentSkill!]! - an array of skill objects (not AWSJSON).
    With ``public_catalog=True`` the PUBLIC skill catalog is requested
    (CN/TCB ``input: {isPublic: true}`` mode) instead of the caller's own
    skills — see gen_get_agent_skills_string for backend caveats.
    """
    queryInfo = gen_get_agent_skills_string(public_catalog=public_catalog)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        first_error = jresp["errors"][0] if jresp["errors"] else {}
        first_message = str(first_error.get("message", ""))
        if "Cannot return null for non-nullable type" in first_message:
            # Real schema bug (backend resolver returned null) — keep at ERROR.
            err_msg = "AppSync queryAgentSkills schema error: resolver returned null for non-nullable field"
            logger.error(f"{err_msg}. Raw errors: {json.dumps(jresp.get('errors', []), ensure_ascii=False)}")
            raise Exception(err_msg)
        # Token-expired / UNAUTHENTICATED is a known transient — the
        # SessionSupervisor will refresh; logging at ERROR would only pollute
        # log-monitoring dashboards without helping anyone find a real bug.
        if _is_token_expired_error_message(first_message):
            logger.warning(f"🔑 AppSync queryAgentSkills token expired: {first_message}")
            logger.debug(f"📋 Full error response: {json.dumps(jresp, ensure_ascii=False)}")
        else:
            logger.error("AppSync queryAgentSkills error: " + json.dumps(jresp))
        jresponse = first_error
    else:
        # Response is already parsed as array of objects (not AWSJSON string)
        skills_data = jresp.get("data", {}).get("queryAgentSkills")
        if skills_data is None:
            logger.info("queryAgentSkills returned null - user has no agent skills data")
            jresponse = []
        else:
            # skills_data is already a list of dicts, no json.loads needed
            jresponse = skills_data

    return jresponse


def gen_query_skill_by_id_string(skill_id: str) -> str:
    """Generate GraphQL query string for querying a specific skill by id.

    Server schema: queryAgentSkills(input: SkillQueryInput): [AgentSkill!]!
    SkillQueryInput: { id: ID, name: String, description: String }

    Args:
        skill_id: Skill id to query (globally unique)

    Returns:
        GraphQL query string
    """
    filter_input = {"id": skill_id}
    # AWS schema uses snake_case: price_model, public (see scripts/appsync_schema_latest.graphql)
    query_string = f'''query MyQueryAgentSkillById {{
        queryAgentSkills(input: {json.dumps(filter_input)}) {{
            id
            askid
            owner
            name
            description
            version
            level
            config
            diagram
            tags
            examples
            inputModes
            outputModes
            apps
            limitations
            path
            source
            price
            price_model
            public
            rentable
        }}
    }}'''
    return query_string


def send_query_skill_by_id_request_to_cloud(token: str, skill_id: str, endpoint: str = None) -> list:
    """Query cloud for a specific skill by id.

    Args:
        token: Auth token
        skill_id: Skill id (globally unique)
        endpoint: Optional endpoint override (uses default if not provided)

    Returns:
        List of matching skills (usually 0 or 1), or empty list on error
    """
    import requests
    from agent.cloud_api.cloud_api_service import get_appsync_endpoint, get_authenticated_session

    if not endpoint:
        endpoint = get_appsync_endpoint()

    session = get_authenticated_session(token)
    query_info = gen_query_skill_by_id_string(skill_id)

    try:
        jresp = appsync_http_request(query_info, session, token, endpoint)

        if "errors" in jresp:
            logger.warning(f"[send_query_skill_by_id] AppSync query error: {json.dumps(jresp.get('errors', []))}")
            return []

        skills_data = jresp.get("data", {}).get("queryAgentSkills")
        if skills_data is None:
            return []

        return skills_data if isinstance(skills_data, list) else [skills_data]
    except Exception as e:
        logger.warning(f"[send_query_skill_by_id] Failed to query cloud for skill id '{skill_id}': {e}")
        return []


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT_TASK, Operation.ADD)
def send_add_agent_task_relations_request_to_cloud(session, relations, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_TASK, Operation.ADD, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "addAgentTaskRels", "addAgentTaskRels")


@cloud_api(DataType.AGENT_TASK, Operation.UPDATE)
def send_update_agent_task_relations_request_to_cloud(session, relations, token, endpoint):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_TASK, Operation.UPDATE, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "updateAgentTaskRels", "updateAgentTaskRels")


@cloud_api(DataType.AGENT_TASK, Operation.DELETE)
def send_remove_agent_task_relations_request_to_cloud(session, removes, token, endpoint):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_TASK, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "removeAgentTaskRels", "removeAgentTaskRels")


@cloud_api(DataType.AGENT_TASK, Operation.QUERY)
def send_query_agent_task_relations_request_to_cloud(session, token, q_settings, endpoint):
    queryInfo = gen_query_agent_tasks_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentTaskRels", "queryAgentTaskRels")


# ============================================================================
# Task Entity Operations
# ============================================================================

@cloud_api(DataType.TASK, Operation.ADD)
def send_add_tasks_request_to_cloud(session, tasks, token, endpoint, timeout=180):
    """Add Task entities (task data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.TASK, Operation.ADD, tasks)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "addAgentTasks", "addAgentTasks")


@cloud_api(DataType.TASK, Operation.UPDATE)
def send_update_tasks_request_to_cloud(session, tasks, token, endpoint):
    """Update Task entities (task data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.TASK, Operation.UPDATE, tasks)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "updateAgentTasks", "updateAgentTasks")


@cloud_api(DataType.TASK, Operation.DELETE)
def send_remove_tasks_request_to_cloud(session, removes, token, endpoint):
    """Remove Task entities (task data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.TASK, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "removeAgentTasks", "removeAgentTasks")


def send_query_agent_tasks_by_time_request_to_cloud(session, token, q_settings, endpoint):
    try:
        queryInfo = gen_query_agent_tasks_by_time_string(q_settings)

        jresp = appsync_http_request(queryInfo, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            error = jresp["errors"][0] if jresp["errors"] else {}
            error_type = error.get("errorType", "Unknown")
            error_msg = error.get("message", str(error))
            logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
            logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
            jresponse = error
        else:
            jresponse = json.loads(jresp["data"]["queryAgentTaskRels"])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorQueryAgentTasksByTime:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorQueryAgentTasksByTime traceback information not available:" + str(e)
        logger.error(ex_stat)
        jresponse = {}

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_agent_tasks_request_to_cloud(session, token, endpoint):
    """Query all tasks for current user using queryAgentTasks with byowneruser"""
    queryInfo = gen_get_agent_tasks_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        first_error = jresp["errors"][0] if jresp["errors"] else {}
        first_message = str(first_error.get("message", ""))
        if "Cannot return null for non-nullable type" in first_message:
            logger.warning("AppSync queryAgentTasks: no data for user - returning empty dict")
            jresponse = {}
        elif _is_token_expired_error_message(first_message):
            logger.warning(f"🔑 AppSync queryAgentTasks token expired: {first_message}")
            logger.debug(f"📋 Full error response: {json.dumps(jresp, ensure_ascii=False)}")
            jresponse = first_error
        else:
            logger.error("AppSync queryAgentTasks error: " + json.dumps(jresp))
            jresponse = first_error
    else:
        try:
            tasks_data = jresp["data"]["queryAgentTasks"]
            if tasks_data is None:
                logger.info("queryAgentTasks returned null - user has no agent tasks data")
                jresponse = {}
            elif isinstance(tasks_data, str):
                # Backward compatible: some old schema returned JSON string.
                jresponse = json.loads(tasks_data)
            else:
                # New schema: returns list/dict directly.
                jresponse = tasks_data
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.error(f"Failed to parse queryAgentTasks response: {e}")
            jresponse = {}

    return jresponse



@cloud_api(DataType.AGENT_TOOL, Operation.ADD)
def send_add_agent_tool_relations_request_to_cloud(session, relations, token, endpoint, timeout=180):
    """Legacy: Agent-Tool direct relationship is not in new AppSync schema. Kept for backward compat."""
    from agent.cloud_api.graphql_builder import build_mutation
    logger.warning("[AGENT_TOOL] Agent-Tool direct relationship is deprecated in new schema. Tools link via Skill-Tool.")
    return {"success": False, "error": "Agent-Tool direct relationship not supported in new schema"}


@cloud_api(DataType.AGENT_TOOL, Operation.UPDATE)
def send_update_agent_tool_relations_request_to_cloud(session, relations, token, endpoint):
    """Legacy: Agent-Tool direct relationship is not in new AppSync schema."""
    logger.warning("[AGENT_TOOL] Agent-Tool direct relationship is deprecated in new schema.")
    return {"success": False, "error": "Agent-Tool direct relationship not supported in new schema"}


@cloud_api(DataType.AGENT_TOOL, Operation.DELETE)
def send_remove_agent_tool_relations_request_to_cloud(session, removes, token, endpoint):
    """Legacy: Agent-Tool direct relationship is not in new AppSync schema."""
    logger.warning("[AGENT_TOOL] Agent-Tool direct relationship is deprecated in new schema.")
    return {"success": False, "error": "Agent-Tool direct relationship not supported in new schema"}


@cloud_api(DataType.AGENT_TOOL, Operation.QUERY)
def send_query_agent_tool_relations_request_to_cloud(session, token, q_settings, endpoint):
    """Legacy: Agent-Tool direct relationship is not in new AppSync schema."""
    logger.warning("[AGENT_TOOL] Agent-Tool direct relationship is deprecated in new schema.")
    return []


# ============================================================================
# Agent-Org Relationship Operations
# ============================================================================

@cloud_api(DataType.AGENT_ORG, Operation.ADD)
def send_add_agent_org_rels_to_cloud(session, relations, token, endpoint, timeout=180):
    """Legacy: Agent-Org direct relationship mutations are not supported in current cloud schema."""
    logger.warning("[AGENT_ORG] Agent-Org direct relationship ADD is not supported in current schema. Using agent.org_id as source of truth.")
    return {
        "skipped": True,
        "success": True,
        "operation": "agent_org.add",
        "reason": "Agent-Org direct relationship mutation is undefined in current server schema",
    }


@cloud_api(DataType.AGENT_ORG, Operation.UPDATE)
def send_update_agent_org_rels_to_cloud(session, relations, token, endpoint, timeout=180):
    """Legacy: Agent-Org direct relationship mutations are not supported in current cloud schema."""
    logger.warning("[AGENT_ORG] Agent-Org direct relationship UPDATE is not supported in current schema. Using agent.org_id as source of truth.")
    return {
        "skipped": True,
        "success": True,
        "operation": "agent_org.update",
        "reason": "Agent-Org direct relationship mutation is undefined in current server schema",
    }


@cloud_api(DataType.AGENT_ORG, Operation.DELETE)
def send_remove_agent_org_rels_to_cloud(session, removes, token, endpoint, timeout=180):
    """Legacy: Agent-Org direct relationship mutations are not supported in current cloud schema."""
    logger.warning("[AGENT_ORG] Agent-Org direct relationship DELETE is not supported in current schema. Using agent.org_id as source of truth.")
    return {
        "skipped": True,
        "success": True,
        "operation": "agent_org.delete",
        "reason": "Agent-Org direct relationship mutation is undefined in current server schema",
    }


# ============================================================================
# Skill-Tool Relationship Operations
# ============================================================================

@cloud_api(DataType.SKILL_TOOL, Operation.ADD)
def send_add_skill_tool_rels_to_cloud(session, relations, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_TOOL, Operation.ADD, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "addAgentSkillToolRels", "addAgentSkillToolRels")


@cloud_api(DataType.SKILL_TOOL, Operation.UPDATE)
def send_update_skill_tool_rels_to_cloud(session, relations, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_TOOL, Operation.UPDATE, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "updateAgentSkillToolRels", "updateAgentSkillToolRels")


@cloud_api(DataType.SKILL_TOOL, Operation.DELETE)
def send_remove_skill_tool_rels_to_cloud(session, removes, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_TOOL, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "removeAgentSkillToolRels", "removeAgentSkillToolRels")


# ============================================================================
# Skill-Knowledge Relationship Operations
# ============================================================================

@cloud_api(DataType.SKILL_KNOWLEDGE, Operation.ADD)
def send_add_skill_knowledge_rels_to_cloud(session, relations, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_KNOWLEDGE, Operation.ADD, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "addAgentSkillKnowledgeRels", "addAgentSkillKnowledgeRels")


@cloud_api(DataType.SKILL_KNOWLEDGE, Operation.UPDATE)
def send_update_skill_knowledge_rels_to_cloud(session, relations, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_KNOWLEDGE, Operation.UPDATE, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "updateAgentSkillKnowledgeRels", "updateAgentSkillKnowledgeRels")


@cloud_api(DataType.SKILL_KNOWLEDGE, Operation.DELETE)
def send_remove_skill_knowledge_rels_to_cloud(session, removes, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_KNOWLEDGE, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "removeAgentSkillKnowledgeRels", "removeAgentSkillKnowledgeRels")


# ============================================================================
# Task-Skill Relationship Operations
# ============================================================================

@cloud_api(DataType.TASK_SKILL, Operation.ADD)
def send_add_task_skill_rels_to_cloud(session, relations, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.TASK_SKILL, Operation.ADD, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "addAgentTaskSkillRels", "addAgentTaskSkillRels")


@cloud_api(DataType.TASK_SKILL, Operation.UPDATE)
def send_update_task_skill_rels_to_cloud(session, relations, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.TASK_SKILL, Operation.UPDATE, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "updateAgentTaskSkillRels", "updateAgentTaskSkillRels")


@cloud_api(DataType.TASK_SKILL, Operation.DELETE)
def send_remove_task_skill_rels_to_cloud(session, removes, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.TASK_SKILL, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "removeAgentTaskSkillRels", "removeAgentTaskSkillRels")


# ============================================================================
# Tool Entity Operations
# ============================================================================

@cloud_api(DataType.TOOL, Operation.ADD)
def send_add_tools_request_to_cloud(session, tools, token, endpoint, timeout=180):
    """Add Tool entities (tool data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.TOOL, Operation.ADD, tools)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "addAgentTools", "addAgentTools")


@cloud_api(DataType.TOOL, Operation.UPDATE)
def send_update_tools_request_to_cloud(session, tools, token, endpoint):
    """Update Tool entities (tool data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.TOOL, Operation.UPDATE, tools)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "updateAgentTools", "updateAgentTools")


@cloud_api(DataType.TOOL, Operation.DELETE)
def send_remove_tools_request_to_cloud(session, removes, token, endpoint):
    """Remove Tool entities (tool data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.TOOL, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "removeAgentTools", "removeAgentTools")


def send_query_agent_tools_by_time_request_to_cloud(session, token, q_settings, endpoint):
    try:
        queryInfo = gen_query_agent_tools_by_time_string(q_settings)

        jresp = appsync_http_request(queryInfo, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            error = jresp["errors"][0] if jresp["errors"] else {}
            error_type = error.get("errorType", "Unknown")
            error_msg = error.get("message", str(error))
            logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
            logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
            jresponse = error
        else:
            jresponse = json.loads(jresp["data"]["queryAgentToolRels"])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorQueryAgentToolsByTime:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorQueryAgentToolsByTime traceback information not available:" + str(e)
        logger.error(ex_stat)
        jresponse = {}

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_agent_tools_request_to_cloud(session, token, endpoint):
    """Query all tools for current user using queryAgentTools with byowneruser"""
    queryInfo = gen_get_agent_tools_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        first_error = jresp["errors"][0] if jresp["errors"] else {}
        first_message = str(first_error.get("message", ""))
        if "Cannot return null for non-nullable type" in first_message:
            logger.warning("AppSync queryAgentTools: no data for user - returning empty dict")
            jresponse = {}
        elif _is_token_expired_error_message(first_message):
            logger.warning(f"🔑 AppSync queryAgentTools token expired: {first_message}")
            logger.debug(f"📋 Full error response: {json.dumps(jresp, ensure_ascii=False)}")
            jresponse = first_error
        else:
            logger.error("AppSync queryAgentTools error: " + json.dumps(jresp))
            jresponse = first_error
    else:
        try:
            tools_data = jresp["data"]["queryAgentTools"]
            if tools_data is None:
                logger.info("queryAgentTools returned null - user has no agent tools data")
                jresponse = {}
            else:
                jresponse = json.loads(tools_data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to parse queryAgentTools response: {e}")
            jresponse = {}

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_knowledges_request_to_cloud(session, tasks, token, endpoint):
    mutationInfo = gen_add_knowledges_string(tasks)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "addKnowledges", "addKnowledges")


def send_update_knowledges_request_to_cloud(session, vehicles, token, endpoint):
    mutationInfo = gen_update_knowledges_string(vehicles)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "updateknowledges", "updateknowledges")



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_knowledges_request_to_cloud(session, removes, token, endpoint):
    mutationInfo = gen_remove_knowledges_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "removeKnowledges", "removeKnowledges")


def send_query_knowledges_request_to_cloud(session, token, q_settings, endpoint):
    queryInfo = gen_query_knowledges_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryKnowledges", "queryKnowledges")



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_knowledges_request_to_cloud(session, token, endpoint):

    queryInfo = gen_get_knowledges_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        first_error = jresp["errors"][0] if jresp["errors"] else {}
        first_message = str(first_error.get("message", ""))
        if "Cannot return null for non-nullable type" in first_message:
            logger.info("No knowledges data found for user - returning empty dict")
            jresponse = {}
        elif _is_token_expired_error_message(first_message):
            logger.warning(f"🔑 AppSync getKnowledges token expired: {first_message}")
            logger.debug(f"📋 Full error response: {json.dumps(jresp, ensure_ascii=False)}")
            jresponse = first_error
        else:
            logger.error("AppSync getKnowledges error: " + json.dumps(jresp))
            jresponse = first_error
    else:
        try:
            knowledges_data = jresp["data"]["getKnowledges"]
            if knowledges_data is None:
                logger.info("getKnowledges returned null - user has no knowledges data")
                jresponse = {}
            else:
                jresponse = json.loads(knowledges_data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to parse getKnowledges response: {e}")
            jresponse = {}

    return jresponse


def send_query_components_request_to_cloud(session, token, components, endpoint):

    queryInfo = gen_query_components_string(components)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    logger.debug("send_query_components_request_to_cloud, response:", jresp)
    if "errors" in jresp:
        screen_error = True
        error = jresp["errors"][0] if jresp["errors"] else {}
        error_type = error.get("errorType", "Unknown")
        error_msg = error.get("message", str(error))
        logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
        logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
        jresponse = error
    else:
        jresponse = json.loads(jresp["data"]["queryComponents"])

    return jresponse



def send_sms_to_cloud(session, token, sms_input, endpoint=None):
    """Call AppSync sendSms mutation. Returns dict with {success, messageId, error}.

    sms_input: dict with keys phoneNumber (E.164), message
    """
    mutation = (
        "mutation SendSms($input: SendSmsInput!) { "
        "sendSms(input: $input) { success messageId error } "
        "}"
    )
    variables = {"input": {
        "phoneNumber": sms_input.get("phoneNumber") or sms_input.get("phone_number") or "",
        "message": sms_input.get("message") or "",
    }}
    try:
        jresp = appsync_http_request(mutation, session, token, endpoint, variables=variables)
        if "errors" in jresp:
            err = (jresp["errors"][0] if jresp["errors"] else {}) or {}
            return {"success": False, "error": err.get("message", str(err))}
        data = jresp.get("data") or {}
        return data.get("sendSms") or {"success": False, "error": "Empty response"}
    except Exception as e:
        return {"success": False, "error": get_traceback(e, "ErrorSendSmsToCloud")}


def send_email_to_cloud(session, token, email_input, endpoint=None):
    """Call AppSync sendEmail mutation. Returns dict with {success, messageId, error}.

    email_input: dict with keys to, subject, bodyText, bodyHtml (optional), replyTo (optional)
    """
    mutation = (
        "mutation SendEmail($input: SendEmailInput!) { "
        "sendEmail(input: $input) { success messageId error } "
        "}"
    )
    payload = {
        "to": email_input.get("to") or "",
        "subject": email_input.get("subject") or "",
    }
    if email_input.get("bodyText") is not None or email_input.get("body_text") is not None:
        payload["bodyText"] = email_input.get("bodyText") or email_input.get("body_text")
    if email_input.get("bodyHtml") is not None or email_input.get("body_html") is not None:
        payload["bodyHtml"] = email_input.get("bodyHtml") or email_input.get("body_html")
    if email_input.get("replyTo") or email_input.get("reply_to"):
        payload["replyTo"] = email_input.get("replyTo") or email_input.get("reply_to")
    variables = {"input": payload}
    try:
        jresp = appsync_http_request(mutation, session, token, endpoint, variables=variables)
        if "errors" in jresp:
            err = (jresp["errors"][0] if jresp["errors"] else {}) or {}
            return {"success": False, "error": err.get("message", str(err))}
        data = jresp.get("data") or {}
        return data.get("sendEmail") or {"success": False, "error": "Empty response"}
    except Exception as e:
        return {"success": False, "error": get_traceback(e, "ErrorSendEmailToCloud")}


def send_query_fom_request_to_cloud(session, token, fom_info, endpoint):
    try:
        queryInfo = gen_query_fom_string(fom_info)

        jresp = appsync_http_request(queryInfo, session, token, endpoint)
        logger.debug("send_query_fom_request_to_cloud, response:", jresp)
        if "errors" in jresp:
            screen_error = True
            error = jresp["errors"][0] if jresp["errors"] else {}
            error_type = error.get("errorType", "Unknown")
            error_msg = error.get("message", str(error))
            logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
            logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
            jresponse = error
        else:
            jresponse = json.loads(jresp["data"]["queryFOM"])
        logger.debug(f"{jresponse}")
    except Exception as e:
        err_msg = get_traceback(e, "ErrorSendQueryFOMRequestToCloud")
        logger.error(f"{err_msg}")
        jresponse = err_msg

    return jresponse



def send_rank_results_request_to_cloud(session, token, rank_data_inut, endpoint):

    queryInfo = gen_rank_results_string(rank_data_inut)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    logger.debug("send_query_rank_results_request_to_cloud, response:", jresp)
    if "errors" in jresp:
        screen_error = True
        error = jresp["errors"][0] if jresp["errors"] else {}
        error_type = error.get("errorType", "Unknown")
        error_msg = error.get("message", str(error))
        logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
        logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
        jresponse = error
    else:
        jresponse = json.loads(jresp["data"]["queryRankResults"])

    return jresponse


def send_get_nodes_prompts_request_to_cloud(session, token, nodes, endpoint):

    queryInfo = gen_get_nodes_prompts_string(nodes)
    logger.debug("send_get_nodes_prompts_request_to_cloud sending: ", queryInfo)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    logger.debug("send_get_nodes_prompts_request_to_cloud jresp: ", jresp)
    if "errors" in jresp:
        error = jresp['errors'][0] if jresp.get('errors') else {}
        error_msg = error.get('message', 'Unknown error')
        if "FieldUndefined" in error_msg or "getNodesPrompts" in error_msg and "undefined" in error_msg:
            logger.warning(
                "[getNodesPrompts] Cloud schema missing 'getNodesPrompts' query; "
                "caller should degrade gracefully"
            )
        else:
            error_type = error.get('errorType', 'GraphQLError')
            logger.error(f"ERROR Type: {error_type} ERROR Info: {error_msg}")
        return {"errors": jresp["errors"], "body": None}
    else:
        try:
            jresponse = json.loads(jresp["data"]["getNodesPrompts"])
            return {"body": json.dumps({"data": jresponse})}
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing response: {e}")
            return {"errors": [{"errorType": "ParseError", "message": str(e)}], "body": None}


def send_start_long_llm_task_to_cloud(session, token, rank_data_inut, endpoint):

    queryInfo = gen_start_long_llm_task_string(rank_data_inut)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    logger.debug("send_start_long_llm_task_to_cloud, response:", jresp)
    if "errors" in jresp:
        screen_error = True
        error = jresp["errors"][0] if jresp["errors"] else {}
        error_type = error.get("errorType", "Unknown")
        error_msg = error.get("message", str(error))
        logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
        logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
        jresponse = error
    else:
        jresponse = json.loads(jresp["data"]["startLongLLMTask"])

    return jresponse


def gen_init_req_scene_string(req_scene_input: dict) -> str:
    """Generate GraphQL mutation string for initReqScene.
    
    GraphQL schema:
        initReqScene(input: ReqSceneInput!): ReqSceneResponse!
        
    ReqSceneInput:
        acctSiteID: String!
        agent_id: String!
        context: AWSJSON
        description: String
        duration_hint_ms: Int
        emotion: String
        mind_state: String
        output_format: OutputFormat
        output_resolution: [Int]
        style: SceneStyle
        refs: [AWSJSON!]
    """
    try:
        acct_site_id = req_scene_input.get("acctSiteID", "")
        agent_id = req_scene_input.get("agent_id", "")
        description = req_scene_input.get("description", "")
        duration_hint_ms = req_scene_input.get("duration_hint_ms")
        emotion = req_scene_input.get("emotion")
        mind_state = req_scene_input.get("mind_state")
        output_format = req_scene_input.get("output_format")  # IMAGE or VIDEO
        output_resolution = req_scene_input.get("output_resolution", [])
        style = req_scene_input.get("style")
        refs = req_scene_input.get("refs", [])
        context = req_scene_input.get("context", {})
        
        # Build input fields
        input_parts = [
            f'acctSiteID: "{acct_site_id}"',
            f'agent_id: "{agent_id}"',
        ]
        
        if description:
            # Escape quotes and newlines in description
            escaped_desc = description.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            input_parts.append(f'description: "{escaped_desc}"')
        
        if duration_hint_ms is not None:
            input_parts.append(f'duration_hint_ms: {duration_hint_ms}')
        
        if emotion:
            escaped_emotion = emotion.replace('"', '\\"')
            input_parts.append(f'emotion: "{escaped_emotion}"')
        
        if mind_state:
            escaped_mind = mind_state.replace('"', '\\"')
            input_parts.append(f'mind_state: "{escaped_mind}"')
        
        if output_format:
            input_parts.append(f'output_format: {output_format}')  # Enum, no quotes
        
        if output_resolution:
            res_str = "[" + ", ".join(str(r) for r in output_resolution) + "]"
            input_parts.append(f'output_resolution: {res_str}')
        
        if style:
            input_parts.append(f'style: {style}')  # Enum, no quotes
        
        # context is AWSJSON - needs to be double-encoded
        if context:
            context_json = json.dumps(json.dumps(context))
            input_parts.append(f'context: {context_json}')
        
        # refs is [AWSJSON!] - each element needs to be double-encoded
        if refs:
            refs_encoded = []
            for ref in refs:
                if isinstance(ref, dict):
                    refs_encoded.append(json.dumps(json.dumps(ref)))
                elif isinstance(ref, str):
                    refs_encoded.append(json.dumps(ref))
            refs_str = "[" + ", ".join(refs_encoded) + "]"
            input_parts.append(f'refs: {refs_str}')
        
        input_str = ", ".join(input_parts)
        
        query_string = f"""
        mutation InitReqScene {{
          initReqScene(input: {{ {input_str} }}) {{
            request_id
            status
            message
            estimated_time_ms
            ref_ul_links
          }}
        }}
        """
        
        logger.debug(f"Generated initReqScene mutation: {query_string}")
        return query_string
    except Exception as e:
        logger.error(f"Error generating initReqScene string: {e}")
        raise


def gen_ready_req_scene_string(ready_input: dict) -> str:
    """Generate GraphQL mutation string for readyReqScene.
    
    GraphQL schema:
        readyReqScene(input: ReadyReqSceneInput!): ReqSceneResponse!
        
    ReadyReqSceneInput:
        acctSiteID: String!
        request_id: ID!
        status: String
    """
    try:
        acct_site_id = ready_input.get("acctSiteID", "")
        request_id = ready_input.get("request_id", "")
        status = ready_input.get("status", "Completed")
        
        query_string = f"""
        mutation ReadyReqScene {{
          readyReqScene(input: {{ acctSiteID: "{acct_site_id}", request_id: "{request_id}", status: "{status}" }}) {{
            request_id
            status
            message
            estimated_time_ms
            ref_ul_links
          }}
        }}
        """
        
        logger.debug(f"Generated readyReqScene mutation: {query_string}")
        return query_string
    except Exception as e:
        logger.error(f"Error generating readyReqScene string: {e}")
        raise


def send_init_req_scene_to_cloud(session, token, req_scene_input: dict, endpoint: str) -> dict:
    """Send initReqScene mutation to cloud.
    
    Args:
        session: HTTP session
        token: Auth token
        req_scene_input: ReqSceneInput dict
        endpoint: GraphQL endpoint
        
    Returns:
        ReqSceneResponse dict with request_id, status, message, estimated_time_ms, ref_ul_links
    """
    logger.info(f"[CloudAPI] send_init_req_scene_to_cloud - endpoint: {endpoint}")
    logger.debug(f"[CloudAPI] initReqScene input: {req_scene_input}")
    
    query_string = gen_init_req_scene_string(req_scene_input)
    logger.debug(f"[CloudAPI] initReqScene query string generated, length: {len(query_string)}")
    
    logger.info("[CloudAPI] Sending initReqScene HTTP request to AppSync...")
    jresp = appsync_http_request(query_string, session, token, endpoint)
    logger.info(f"[CloudAPI] initReqScene raw response received, keys: {list(jresp.keys()) if isinstance(jresp, dict) else 'N/A'}")
    logger.debug(f"[CloudAPI] initReqScene full response: {jresp}")
    
    if "errors" in jresp:
        error = jresp["errors"][0] if jresp["errors"] else {}
        error_type = error.get("errorType", "Unknown")
        error_msg = error.get("message", str(error))
        logger.error(f"[CloudAPI] initReqScene ERROR Type: {error_type}")
        logger.error(f"[CloudAPI] initReqScene ERROR Info: {error_msg}")
        logger.error(f"[CloudAPI] initReqScene Full errors: {jresp['errors']}")
        return {"errors": jresp["errors"], "request_id": "", "status": "Error", "message": error_msg}
    
    result = jresp.get("data", {}).get("initReqScene", {})
    logger.info(f"[CloudAPI] initReqScene SUCCESS - request_id: {result.get('request_id', 'N/A')}, status: {result.get('status', 'N/A')}")
    return result


def send_ready_req_scene_to_cloud(session, token, ready_input: dict, endpoint: str) -> dict:
    """Send readyReqScene mutation to cloud.
    
    Args:
        session: HTTP session
        token: Auth token
        ready_input: ReadyReqSceneInput dict with acctSiteID, request_id, status
        endpoint: GraphQL endpoint
        
    Returns:
        ReqSceneResponse dict
    """
    logger.info(f"[CloudAPI] send_ready_req_scene_to_cloud - endpoint: {endpoint}")
    logger.info(f"[CloudAPI] readyReqScene input: {ready_input}")
    
    query_string = gen_ready_req_scene_string(ready_input)
    logger.debug(f"[CloudAPI] readyReqScene query string generated, length: {len(query_string)}")
    
    logger.info("[CloudAPI] Sending readyReqScene HTTP request to AppSync...")
    jresp = appsync_http_request(query_string, session, token, endpoint)
    logger.info(f"[CloudAPI] readyReqScene raw response received, keys: {list(jresp.keys()) if isinstance(jresp, dict) else 'N/A'}")
    logger.debug(f"[CloudAPI] readyReqScene full response: {jresp}")
    
    if "errors" in jresp:
        error = jresp["errors"][0] if jresp["errors"] else {}
        error_type = error.get("errorType", "Unknown")
        error_msg = error.get("message", str(error))
        logger.error(f"[CloudAPI] readyReqScene ERROR Type: {error_type}")
        logger.error(f"[CloudAPI] readyReqScene ERROR Info: {error_msg}")
        logger.error(f"[CloudAPI] readyReqScene Full errors: {jresp['errors']}")
        return {"errors": jresp["errors"], "request_id": "", "status": "Error", "message": error_msg}
    
    result = jresp.get("data", {}).get("readyReqScene", {})
    logger.info(f"[CloudAPI] readyReqScene SUCCESS - request_id: {result.get('request_id', 'N/A')}, status: {result.get('status', 'N/A')}")
    return result


def convert_cloud_result_to_task_send_params(result_obj: dict, work_type: str) -> dict:
    """
    Convert cloud API result object to TaskSendParams-compatible format for _build_resume_payload().
    
    Args:
        result_obj: The result object from cloud API containing taskID, results, etc.
        work_type: The type of work being performed (e.g., "rerank_search_results")
        
    Returns:
        dict: A dictionary in TaskSendParams format that can be consumed by _build_resume_payload()
    """
    try:
        # Extract key fields from result_obj
        task_id = result_obj.get("taskID", "")
        results = result_obj.get("results", {})
        
        # Create the message structure compatible with TaskSendParams
        # For now, message is None as requested
        message = None
        
        # Create metadata with required fields
        metadata = {
            "i_tag": task_id,  # Use taskID as the interrupt tag
            "notification_to_agent": results  # Use results as notification data
        }
        
        # Handle different work types
        if work_type == "rerank_search_results":
            # For rerank_search_results, we may need additional processing
            # but for now we'll use the basic structure
            pass
        # Add more work_type handling here as needed
        
        # Create the TaskSendParams-like structure with params wrapper
        # The _build_resume_payload expects msg to have either direct fields or params.field structure
        task_send_params = {
            "id": task_id,
            "params": {
                "id": task_id,
                "message": message,
                "metadata": metadata
            },
            "message": message,
            "metadata": metadata
        }
        
        logger.debug(f"Converted cloud result to TaskSendParams format: {json.dumps(task_send_params, indent=2)}")
        return task_send_params
        
    except Exception as e:
        logger.error(f"Error converting cloud result to TaskSendParams: {e}")
        # Return minimal structure on error with params wrapper
        task_id = result_obj.get("taskID", "")
        metadata = {
            "i_tag": task_id,
            "notification_to_agent": {}
        }
        return {
            "id": task_id,
            "params": {
                "id": task_id,
                "message": None,
                "metadata": metadata
            },
            "message": None,
            "metadata": metadata
        }


# ============================================================================
# SCENE GENERATION API FUNCTIONS
# ============================================================================

def gen_req_scene_mutation_string(scene_input: dict) -> str:
    """
    Generate GraphQL mutation string for requesting scene generation.
    
    Args:
        scene_input: Dict with keys: acctSiteID, agent_id, emotion, mind_state, 
                     description, style, output_format, duration_hint_ms, context
    """
    # Escape strings for GraphQL
    def escape_str(s):
        if s is None:
            return "null"
        return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'
    
    acct_site_id = escape_str(scene_input.get("acctSiteID"))
    agent_id = escape_str(scene_input.get("agent_id"))
    emotion = escape_str(scene_input.get("emotion"))
    mind_state = escape_str(scene_input.get("mind_state"))
    description = escape_str(scene_input.get("description"))
    style = scene_input.get("style", "ANIME")  # Enum, no quotes
    output_format = scene_input.get("output_format", "WEBM")  # Enum, no quotes
    duration_hint_ms = scene_input.get("duration_hint_ms")
    context = scene_input.get("context")
    
    # Build context JSON string if provided
    context_str = "null"
    if context:
        context_str = '"' + json.dumps(context).replace('\\', '\\\\').replace('"', '\\"') + '"'
    
    duration_str = str(duration_hint_ms) if duration_hint_ms else "null"
    
    mutation_string = f"""
        mutation ReqScene {{
          reqScene(input: {{
            acctSiteID: {acct_site_id}
            agent_id: {agent_id}
            emotion: {emotion}
            mind_state: {mind_state}
            description: {description}
            style: {style}
            output_format: {output_format}
            duration_hint_ms: {duration_str}
            context: {context_str}
          }}) {{
            request_id
            status
            message
            estimated_time_ms
          }}
        }}
    """
    logger_helper.debug(f"[Scene] Generated reqScene mutation: {mutation_string}")
    return mutation_string


def gen_query_scene_string(scene_id: str) -> str:
    """Generate GraphQL query string for getting a scene by ID."""
    query_string = f"""
        query GetScene {{
          getScene(id: "{scene_id}") {{
            id
            acctSiteID
            scene_id
            agent_ids
            label
            clip
            n_repeat
            priority
            captions
            trigger_events
            description
            dialogs
            actions
            duration_ms
            timestamp
            status
          }}
        }}
    """
    return query_string


def gen_query_scenes_string(query_input: dict) -> str:
    """
    Generate GraphQL query string for querying scenes with filters.
    
    Args:
        query_input: Dict with keys: acctSiteID, agent_id, label, emotion, status, limit, nextToken
    """
    def escape_str(s):
        if s is None:
            return "null"
        return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'
    
    acct_site_id = escape_str(query_input.get("acctSiteID"))
    agent_id = escape_str(query_input.get("agent_id")) if query_input.get("agent_id") else "null"
    label = escape_str(query_input.get("label")) if query_input.get("label") else "null"
    emotion = escape_str(query_input.get("emotion")) if query_input.get("emotion") else "null"
    status = query_input.get("status") if query_input.get("status") else "null"  # Enum
    limit = query_input.get("limit", 20)
    next_token = escape_str(query_input.get("nextToken")) if query_input.get("nextToken") else "null"
    
    query_string = f"""
        query QueryScenes {{
          queryScenes(input: {{
            acctSiteID: {acct_site_id}
            agent_id: {agent_id}
            label: {label}
            emotion: {emotion}
            status: {status}
            limit: {limit}
            nextToken: {next_token}
          }}) {{
            items {{
              id
              acctSiteID
              scene_id
              agent_ids
              label
              clip
              n_repeat
              priority
              captions
              description
              timestamp
              status
            }}
            nextToken
          }}
        }}
    """
    return query_string


def gen_start_soap_mutation_string(soap_input: dict) -> str:
    """
    Generate GraphQL mutation string for starting a soap opera.
    
    Args:
        soap_input: Dict with keys: acctSiteID, agent_ids, theme, mood, settings
    """
    def escape_str(s):
        if s is None:
            return "null"
        return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'
    
    acct_site_id = escape_str(soap_input.get("acctSiteID"))
    agent_ids = soap_input.get("agent_ids", [])
    agent_ids_str = "[" + ", ".join([f'"{aid}"' for aid in agent_ids]) + "]"
    theme = escape_str(soap_input.get("theme"))
    mood = escape_str(soap_input.get("mood"))
    settings = soap_input.get("settings")
    settings_str = "null"
    if settings:
        settings_str = '"' + json.dumps(settings).replace('\\', '\\\\').replace('"', '\\"') + '"'
    
    mutation_string = f"""
        mutation StartSoap {{
          startSoap(input: {{
            acctSiteID: {acct_site_id}
            agent_ids: {agent_ids_str}
            theme: {theme}
            mood: {mood}
            settings: {settings_str}
          }}) {{
            soap_id
            status
            message
          }}
        }}
    """
    return mutation_string


def send_req_scene_to_cloud(session, scene_input: dict, token: str, endpoint: str) -> dict:
    """
    Send a scene generation request to the cloud.
    
    Args:
        session: HTTP session
        scene_input: Scene generation parameters
        token: Auth token
        endpoint: API endpoint
        
    Returns:
        dict with request_id, status, message, estimated_time_ms or error info
    """
    mutation_string = gen_req_scene_mutation_string(scene_input)
    
    jresp = appsync_http_request(mutation_string, session, token, endpoint)
    
    logger_helper.debug(f"[Scene] reqScene response: {json.dumps(jresp)}")
    if "errors" in jresp:
        error_obj = jresp["errors"][0]
        error_type = error_obj.get("errorType", error_obj.get("type", "Unknown"))
        error_msg = error_obj.get("message", str(error_obj))
        logger_helper.error(f"[Scene] ERROR Type: {error_type} ERROR Info: {error_msg}")
        return {"errorType": error_type, "message": error_msg}
    else:
        return jresp.get("data", {}).get("reqScene", {})


def send_get_scene_to_cloud(session, scene_id: str, token: str, endpoint: str) -> dict:
    """
    Get a scene by ID from the cloud.
    
    Args:
        session: HTTP session
        scene_id: Scene ID to retrieve
        token: Auth token
        endpoint: API endpoint
        
    Returns:
        Scene object or error info
    """
    query_string = gen_query_scene_string(scene_id)
    
    jresp = appsync_http_request(query_string, session, token, endpoint)
    
    logger_helper.debug(f"[Scene] getScene response: {json.dumps(jresp)}")
    if "errors" in jresp:
        error_obj = jresp["errors"][0]
        error_type = error_obj.get("errorType", error_obj.get("type", "Unknown"))
        error_msg = error_obj.get("message", str(error_obj))
        logger_helper.error(f"[Scene] ERROR Type: {error_type} ERROR Info: {error_msg}")
        return {"errorType": error_type, "message": error_msg}
    else:
        return jresp.get("data", {}).get("getScene", {})


def send_query_scenes_to_cloud(session, query_input: dict, token: str, endpoint: str) -> dict:
    """
    Query scenes with filters from the cloud.
    
    Args:
        session: HTTP session
        query_input: Query parameters (acctSiteID, agent_id, label, etc.)
        token: Auth token
        endpoint: API endpoint
        
    Returns:
        dict with items list and nextToken, or error info
    """
    query_string = gen_query_scenes_string(query_input)
    
    jresp = appsync_http_request(query_string, session, token, endpoint)
    
    logger_helper.debug(f"[Scene] queryScenes response: {json.dumps(jresp)}")
    if "errors" in jresp:
        error_obj = jresp["errors"][0]
        error_type = error_obj.get("errorType", error_obj.get("type", "Unknown"))
        error_msg = error_obj.get("message", str(error_obj))
        logger_helper.error(f"[Scene] ERROR Type: {error_type} ERROR Info: {error_msg}")
        return {"errorType": error_type, "message": error_msg}
    else:
        return jresp.get("data", {}).get("queryScenes", {})


def send_start_soap_to_cloud(session, soap_input: dict, token: str, endpoint: str) -> dict:
    """
    Start a soap opera (continuous story generation) on the cloud.
    
    Args:
        session: HTTP session
        soap_input: Soap parameters (acctSiteID, agent_ids, theme, mood, settings)
        token: Auth token
        endpoint: API endpoint
        
    Returns:
        dict with soap_id, status, message or error info
    """
    mutation_string = gen_start_soap_mutation_string(soap_input)
    
    jresp = appsync_http_request(mutation_string, session, token, endpoint)
    
    logger_helper.debug(f"[Scene] startSoap response: {json.dumps(jresp)}")
    if "errors" in jresp:
        error_obj = jresp["errors"][0]
        error_type = error_obj.get("errorType", error_obj.get("type", "Unknown"))
        error_msg = error_obj.get("message", str(error_obj))
        logger_helper.error(f"[Scene] ERROR Type: {error_type} ERROR Info: {error_msg}")
        return {"errorType": error_type, "message": error_msg}
    else:
        return jresp.get("data", {}).get("startSoap", {})


def send_stop_soap_to_cloud(session, soap_id: str, token: str, endpoint: str) -> bool:
    """
    Stop a running soap opera.
    
    Args:
        session: HTTP session
        soap_id: Soap ID to stop
        token: Auth token
        endpoint: API endpoint
        
    Returns:
        True if successful, False otherwise
    """
    mutation_string = f"""
        mutation StopSoap {{
          stopSoap(soap_id: "{soap_id}")
        }}
    """
    
    jresp = appsync_http_request(mutation_string, session, token, endpoint)
    
    logger_helper.debug(f"[Scene] stopSoap response: {json.dumps(jresp)}")
    if "errors" in jresp:
        error_obj = jresp["errors"][0]
        error_type = error_obj.get("errorType", error_obj.get("type", "Unknown"))
        error_msg = error_obj.get("message", str(error_obj))
        logger_helper.error(f"[Scene] ERROR Type: {error_type} ERROR Info: {error_msg}")
        return False
    else:
        return jresp.get("data", {}).get("stopSoap", False)


# ============================================================================
# WebSocket Subscription Helpers (auto-reconnect with fresh tokens)
# ============================================================================

def _get_fresh_auth_token(fallback_token: str) -> Optional[str]:
    """Get a live Cognito auth token from AppContext.

    Resolution order:
        1. Ask the live session for a fresh token. ``get_auth_token`` calls
           ``AuthManager.ensure_valid_tokens`` which already:
             - refreshes with RefreshToken when available,
             - clears credentials and sets ``signed_in=False`` when no
               RefreshToken (CN WeChat) and the token is expiring/expired.
        2. If we still have no token, examine ``signed_in``:
             - ``False`` means AuthManager has explicitly invalidated the
               session. Kick the user back to the login window exactly once
               and return None so the WS loop stops.
             - ``True`` (or N/A) means a transient backend blip; fall back to
               the provided token so the loop can keep trying.
    """
    from typing import Optional as _Opt

    token: _Opt[str] = None
    signed_in = None
    try:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if main_window and hasattr(main_window, 'get_auth_token'):
            token = main_window.get_auth_token()
        if main_window is not None and hasattr(main_window, 'auth_manager'):
            am = main_window.auth_manager
            if am is not None and hasattr(am, 'signed_in'):
                signed_in = bool(am.signed_in)
    except Exception as e:
        logger.debug(f"[_get_fresh_auth_token] Could not query AppContext: {e}")

    if token:
        return token

    if signed_in is False:
        # AuthManager has cleared the credentials (e.g. CN WeChat token
        # expired and no RefreshToken). Surface the session loss to the UI
        # exactly once per process and stop the WS reconnect loop instead
        # of hammering AppSync with a dead token.
        global _session_invalidated
        if not _session_invalidated:
            _session_invalidated = True
            try:
                login = AppContext.get_login()
                if login is not None and hasattr(login, 'handleLogout'):
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, login.handleLogout)
                    logger.info(
                        f"[CloudLLMTask] Session invalidated by AuthManager; "
                        "scheduling logout. WS reconnect will stop."
                    )
            except Exception as e:
                logger.warning(f"[_get_fresh_auth_token] Could not schedule logout: {e}")
        return None

    # Transient: keep the loop alive with the fallback (live or stale).
    return fallback_token


# Guard so a flapping WS triggers handleLogout at most once per process.
_session_invalidated = False

# Process-global event set when any WS subscription observes an auth failure
# (401 / 403 / token rejected). Subscribers read this and stop reconnecting
# instead of hammering the backend with a dead token.
_auth_failure_event = threading.Event()

# Hard cap on consecutive reconnect attempts regardless of error class. Once
# exceeded, the loop exits even if the error never reached the `except` branch
# (e.g. websocket-client raises handshake 401 via on_error/on_close, not as
# an exception — so the existing `max_retries` check never fires for it).
_WS_HARD_FAILURE_LIMIT = 10

# Idempotency latch: ``SessionSupervisor.on_session_refreshed`` accumulates
# callbacks, so we must register exactly once per process.
_session_recovery_hook_installed = False

# Tracks the currently-active WebSocketApp per subscription label so a
# SessionSupervisor refresh event can proactively close them and force the
# reconnect loop to pick up the new token on the next iteration. Keyed by
# ``label`` (e.g. "CloudLLMTask") and guarded by ``_active_ws_lock``.
_active_ws_by_label: dict = {}
_active_ws_lock = threading.Lock()

# Latch for the "close all active ws on refresh" hook. Separate from
# ``_session_recovery_hook_installed`` so the two callbacks can evolve
# independently and either can be re-armed for testing.
_proactive_close_hook_installed = False


def is_session_invalidated() -> bool:
    """Whether any WS subscription has flagged the session as unrecoverable.

    Callers (e.g. MainGUI restart logic) can poll this to decide whether to
    reload the token from AuthManager before relaunching subscriptions.
    """
    return _auth_failure_event.is_set()


def clear_session_invalidated() -> None:
    """Reset the process-global auth-failure latch.

    Intended to be called by AuthManager after a successful login or token
    refresh so a previously-invalidated session can resume subscriptions.
    """
    global _session_invalidated
    _session_invalidated = False
    _auth_failure_event.clear()


def _flag_auth_failure(label: str, status_or_error: str) -> None:
    """Mark the session as auth-failed and surface to UI at most once.

    Called from on_error / on_close when a 401/403 / unauthorized response is
    observed. Idempotent — only the first call triggers handleLogout; later
    calls just keep the latch set so other subscribers see it.
    """
    global _session_invalidated
    if _auth_failure_event.is_set():
        return

    _auth_failure_event.set()

    if not _session_invalidated:
        _session_invalidated = True
        try:
            from app_context import AppContext
            login = AppContext.get_login()
            if login is not None and hasattr(login, 'handleLogout'):
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, login.handleLogout)
                logger.info(
                    f"[{label}] Auth failure detected ({status_or_error}); "
                    "scheduling logout. WS reconnect will stop."
                )
        except Exception as e:
            logger.warning(f"[{label}] Could not schedule logout: {e}")


def _install_session_recovery_hook() -> bool:
    """Subscribe to ``SessionSupervisor.on_session_refreshed`` so a successful
    token refresh (or re-login) clears the auth-failure latch.

    Once ``_auth_failure_event`` is set, all WS reconnect loops bail out at
    the top of their next iteration — which is correct behaviour while the
    session is broken, but leaves us stuck forever after the user re-logs in
    unless somebody clears the latch.  ``SessionSupervisor`` already fires
    ``on_session_refreshed`` whenever ``AuthManager`` installs a new token
    (login, silent refresh, restore), so we hook into that and call
    ``clear_session_invalidated()``.

    Safe to call from any thread; the underlying ``on_session_refreshed``
    uses an internal lock and we guard against double-registration with
    ``_session_recovery_hook_installed``.

    Returns ``True`` if the hook is now installed (including if it was
    already installed by a previous call), ``False`` if it could not be
    installed because the supervisor is unavailable.
    """
    global _session_recovery_hook_installed
    if _session_recovery_hook_installed:
        return True

    try:
        from auth.session_supervisor import get_session_supervisor
    except Exception as e:
        logger.debug(f"[SessionRecovery] SessionSupervisor not importable: {e}")
        return False

    supervisor = get_session_supervisor()
    if supervisor is None:
        # Supervisor hasn't been installed yet (e.g. user hasn't logged in).
        # No retry: the next subscribe_* call will try again, and once the
        # user logs in the supervisor singleton will exist.
        return False

    def _on_session_refreshed(_info):
        # ``info`` from the supervisor is unused here — we only care that
        # *some* fresh token just landed.
        try:
            clear_session_invalidated()
            logger.info(
                "[SessionRecovery] New token detected — cleared auth-failure "
                "latch; WS subscriptions can resume on next launch."
            )
        except Exception as e:
            logger.warning(f"[SessionRecovery] clear_session_invalidated failed: {e}")

    try:
        supervisor.on_session_refreshed(_on_session_refreshed)
    except Exception as e:
        logger.warning(f"[SessionRecovery] Could not register callback: {e}")
        return False

    _session_recovery_hook_installed = True
    logger.info("[SessionRecovery] Hook installed; auth-failure latch will "
                "reset automatically on next token refresh / re-login.")
    return True


def register_active_ws(label: str, ws) -> None:
    """Record the current ``WebSocketApp`` for ``label`` so a SessionSupervisor
    refresh can proactively close it. Called by the reconnect loop right after
    ``build_ws_fn`` returns."""
    with _active_ws_lock:
        _active_ws_by_label[label] = ws


def unregister_active_ws(label: str, ws=None) -> None:
    """Forget the current ``WebSocketApp`` for ``label`` (e.g. after the loop
    exits, or before we replace it with a fresh one).  When ``ws`` is provided,
    only remove if the registered ws still matches — avoids dropping a newer
    registration that the supervisor might already have closed."""
    with _active_ws_lock:
        if label not in _active_ws_by_label:
            return
        if ws is None or _active_ws_by_label[label] is ws:
            _active_ws_by_label.pop(label, None)


def _close_all_active_ws() -> int:
    """Snapshot and clear ``_active_ws_by_label``, then close each ws.  Returns
    the number of ws we attempted to close.  Idempotent: callers can invoke
    multiple times and only fresh entries will be closed."""
    with _active_ws_lock:
        if not _active_ws_by_label:
            return 0
        items = list(_active_ws_by_label.items())
        _active_ws_by_label.clear()
    for label, ws in items:
        try:
            ws.close()
            logger.info(
                f"[{label}] Proactive close after token refresh; "
                "reconnect loop will pick up the new token."
            )
        except Exception as e:
            logger.debug(f"[{label}] ws.close() during proactive refresh failed: {e}")
    return len(items)


def _install_proactive_close_hook() -> bool:
    """Subscribe to ``SessionSupervisor.on_session_refreshed`` so a token
    refresh actively closes every active WS — letting the reconnect loops
    immediately rebuild their signed URLs with the new token instead of
    waiting for the server to drop the old (stale) connection.

    Why this exists: the AppSync-style signed URL embeds the bearer token
    in ``?header=...&payload=...`` at upgrade time.  After a refresh, the
    server may still accept the old connection for a while, but eventually
    starts rejecting reads with ``401 Unauthorized`` — by which point the
    reconnect storm has already started.  Proactively closing the moment
    AuthManager finishes installing the new token avoids that gap.

    Idempotent: a separate latch (``_proactive_close_hook_installed``) keeps
    us from registering duplicate callbacks even though
    ``on_session_refreshed`` would happily accumulate them.
    """
    global _proactive_close_hook_installed
    if _proactive_close_hook_installed:
        return True

    try:
        from auth.session_supervisor import get_session_supervisor
    except Exception as e:
        logger.debug(f"[ProactiveClose] SessionSupervisor not importable: {e}")
        return False

    supervisor = get_session_supervisor()
    if supervisor is None:
        return False

    def _on_refreshed_close_all(_info):
        try:
            n = _close_all_active_ws()
            if n:
                logger.info(
                    f"[ProactiveClose] Closed {n} active WS connection(s) "
                    "after token refresh."
                )
        except Exception as e:
            logger.warning(f"[ProactiveClose] close sweep failed: {e}")

    try:
        supervisor.on_session_refreshed(_on_refreshed_close_all)
    except Exception as e:
        logger.warning(f"[ProactiveClose] Could not register callback: {e}")
        return False

    _proactive_close_hook_installed = True
    logger.info("[ProactiveClose] Hook installed; token refresh will "
                "proactively close all active WS connections.")
    return True


def _resolve_appsync_ws_url(ws_url: Optional[str], label: str) -> str:
    """Resolve and normalize an AppSync WebSocket URL to the realtime endpoint."""
    if not ws_url:
        ws_url = os.getenv("ECAN_WS_URL", "")
    if not ws_url:
        raise ValueError(f"[{label}] WebSocket URL not provided and ECAN_WS_URL is not set")
    
    # CN TCB: return as-is (SSE endpoint)
    if ".service.tcloudbase.com" in ws_url:
        logger.info(f"[{label}] Using CN TCB endpoint: {ws_url}")
        return ws_url
    
    # Intl AppSync: convert to realtime endpoint
    if ws_url.startswith("https://") and "appsync-api" in ws_url:
        prefix = "https://"
        rest = ws_url[len(prefix):]
        rest = rest.replace("appsync-api", "appsync-realtime-api", 1)
        ws_url = "wss://" + rest
        logger.info(f"[{label}] Converted to realtime endpoint: {ws_url}")
    return ws_url


def _build_appsync_signed_url(ws_url: str, token: str) -> tuple:
    """Build AppSync signed WebSocket URL. Returns (signed_url, api_host)."""
    parsed = urlparse(ws_url)
    api_host = parsed.netloc.replace("appsync-realtime-api", "appsync-api")
    header_obj = {"host": api_host, "Authorization": token}
    header_b64 = base64.b64encode(json.dumps(header_obj).encode("utf-8")).decode("utf-8")
    payload_b64 = base64.b64encode(json.dumps({}).encode("utf-8")).decode("utf-8")
    query = dict(parse_qsl(parsed.query))
    query.update({"header": header_b64, "payload": payload_b64})
    signed_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path,
                              parsed.params, urlencode(query), parsed.fragment))
    return signed_url, api_host


def _appsync_ws_reconnect_loop(label: str, ws_url: str, initial_token: str,
                                build_ws_fn, max_retries: int = 5,
                                base_backoff: float = 1.0):
    """Run an AppSync WebSocket subscription with bounded retry and jitter.

    Intended as a threading.Thread target.

    Retry semantics (per error class):
        - AuthError (401 / 403):  stop immediately — token is invalid, retrying
                                  with the same or fallback token is wasted.
        - TransientError (network, timeout, 5xx): backoff with ±20% jitter up to
                                                  MAX_BACKOFF seconds.
        - ExhaustiveError (max_retries exceeded OR consecutive failures across
                           callback path): stop, let the caller decide.

    Note: websocket-client surfaces HTTP-handshake failures (e.g. 401 returned
    during the upgrade) via ``on_error``/``on_close`` rather than as Python
    exceptions, so the legacy ``except`` branch never sees them. To avoid an
    infinite reconnect loop in that case we monkey-patch ``on_error`` and
    ``on_close`` after each ``build_ws_fn`` call to detect 401/403 and stop the
    loop, and we also count consecutive failures across the callback path
    against ``_WS_HARD_FAILURE_LIMIT``.

    Args:
        label: Log prefix (e.g. "CloudLLMTask")
        ws_url: Resolved AppSync realtime WebSocket URL (wss://...)
        initial_token: Initial auth token (used on first attempt only)
        build_ws_fn: Callable(token, api_host, signed_url) -> WebSocketApp
        max_retries: Maximum consecutive reconnect attempts after a transient error.
                     401/403 never counts as a retry — it exits immediately.
        base_backoff: Base seconds for exponential backoff (jitter applied on top).
    """
    import random
    import ssl
    import time

    MAX_BACKOFF = 30.0  # seconds — never exceed this regardless of retry count

    def _backoff(attempt: int) -> float:
        """Exponential backoff with ±20% uniform jitter."""
        raw = base_backoff * (2 ** attempt)
        capped = min(raw, MAX_BACKOFF)
        jitter = capped * random.uniform(-0.2, 0.2)
        return max(0.1, capped + jitter)

    def _is_auth_failure_payload(value) -> bool:
        """Match 401/403-ish payloads anywhere in a string or exception args."""
        if value is None:
            return False
        s = str(value).lower()
        return (
            "401" in s or "403" in s
            or "unauthorized" in s or "forbidden" in s
        )

    def _install_ws_hooks(ws, user_on_error, user_on_close):
        """Wrap user callbacks so 401/403 stop the loop and trigger logout once.

        ``websocket-client`` runs ``run_forever`` in a background thread; the
        callbacks fire on that same thread, so writes to ``auth_failed`` and
        ``consecutive_failures`` are already serialized by the GIL — no extra
        lock needed.
        """
        def _on_error(ws_local, error):
            if _is_auth_failure_payload(error):
                auth_failed.set()
                _flag_auth_failure(label, f"on_error={error!r}")
            consecutive_failures[0] += 1
            if user_on_error is not None:
                try:
                    user_on_error(ws_local, error)
                except Exception:
                    pass

        def _on_close(ws_local, status_code, msg):
            if _is_auth_failure_payload(status_code) or _is_auth_failure_payload(msg):
                auth_failed.set()
                _flag_auth_failure(label, f"on_close={status_code} {msg!r}")
            consecutive_failures[0] += 1
            if user_on_close is not None:
                try:
                    user_on_close(ws_local, status_code, msg)
                except Exception:
                    pass

        ws.on_error = _on_error
        ws.on_close = _on_close

    auth_failed = threading.Event()
    consecutive_failures = [0]  # mutable cell — shared between callbacks and loop
    retry_count = 0

    # Make sure both SessionSupervisor hooks are installed: one clears the
    # auth-failure latch on refresh, the other proactively closes any active
    # ws so the reconnect loop rebuilds the signed URL with the new token.
    # Both are idempotent and lazy — first call only.
    _install_session_recovery_hook()
    _install_proactive_close_hook()

    while True:
        # Bail early if any peer subscription already detected an auth failure
        # — there is no point burning a TCP upgrade on a dead token.
        if _auth_failure_event.is_set() or auth_failed.is_set():
            logger.warning(
                f"[{label}] Session already flagged as auth-failed by another "
                "subscription; stopping without retrying."
            )
            return

        # First attempt always uses the initial token; subsequent attempts
        # always ask AuthManager for a live token.
        token = initial_token if retry_count == 0 else _get_fresh_auth_token(initial_token)
        if token is None:
            # AuthManager has cleared the session (e.g. CN WeChat token expired
            # and no RefreshToken). The UI has already been notified; stop here.
            logger.warning(
                f"[{label}] No usable token (session invalidated); stopping subscription."
            )
            return

        signed_url, api_host = _build_appsync_signed_url(ws_url, token)

        try:
            ws = build_ws_fn(token, api_host, signed_url)
            # Capture the user-supplied callbacks (may be None) before we
            # overwrite them so we can still invoke them from our wrapper.
            user_on_error = ws.on_error
            user_on_close = ws.on_close
            _install_ws_hooks(ws, user_on_error, user_on_close)
            # Publish the new ws so a SessionSupervisor refresh event can
            # close it. Old registration for this label (if any) is cleared
            # implicitly — ``register_active_ws`` overwrites.
            register_active_ws(label, ws)

            logger.info(f"[{label}] WebSocket connecting (attempt {retry_count + 1})")
            # Keep the TCP stream alive so upstream LBs/NATs (≈60s idle
            # timeout observed in production) don't FIN the socket.
            ws.run_forever(
                sslopt={"cert_reqs": ssl.CERT_NONE},
                ping_interval=30,  # 30s to stay under server's ~60s idle timeout
                ping_timeout=15,
            )

            # Drop the registration before we check exit conditions. If
            # ``_close_all_active_ws`` already ran (token-refresh path) the
            # dict won't contain ``ws`` and the unregister is a no-op.
            unregister_active_ws(label, ws)

            # Every run_forever return counts as one tick against the hard
            # limit, even if no callback fired. Without this, a backend that
            # closes the socket cleanly without invoking on_error/on_close
            # (or a token-refresh close where our wrapper hasn't already
            # incremented the counter) would loop forever here.
            consecutive_failures[0] += 1

            if auth_failed.is_set():
                logger.warning(
                    f"[{label}] Auth failure detected during this iteration; "
                    "stopping subscription without retry."
                )
                return

            # Hard ceiling on consecutive failures across both paths (callback
            # and exception). Without this, a backend that returns 1006 every
            # time would loop forever because it never matches the 401/403
            # branch and never raises an exception either.
            if consecutive_failures[0] >= _WS_HARD_FAILURE_LIMIT:
                logger.error(
                    f"[{label}] Reached hard failure limit "
                    f"({consecutive_failures[0]} consecutive); giving up."
                )
                return

            logger.warning(f"[{label}] WebSocket run_forever exited, will reconnect")
        except Exception as e:
            err_str = str(e).lower()

            # ---- Auth errors: bail immediately, do not retry -----------------
            if _is_auth_failure_payload(err_str):
                logger.error(
                    f"[{label}] Auth error (401/403): {e!r}. "
                    "Session may be expired; stopping subscription."
                )
                _flag_auth_failure(label, f"exception={e!r}")
                return

            # ---- Transient errors: back off and retry -----------------------
            if retry_count + 1 >= max_retries:
                logger.error(
                    f"[{label}] Transient error after {retry_count + 1} attempts: {e!r}. "
                    f"Max retries ({max_retries}) reached; giving up."
                )
                return

            wait = _backoff(retry_count)
            retry_count += 1
            logger.warning(
                f"[{label}] Transient error: {e!r}. "
                f"Retrying in {wait:.1f}s (attempt {retry_count}/{max_retries})."
            )
            time.sleep(wait)
            continue


# related to websocket sub/push to get long running task results
def subscribe_cloud_llm_task(acctSiteID: str, id_token: str, ws_url: Optional[str] = None) -> Tuple[websocket.WebSocketApp, threading.Thread]:
    from agent.agent_service import get_agent_by_id
    """Subscribe to long-running LLM task updates over WebSocket.

    Parameters:
        acctSiteID: Account/site identifier used by the subscription filter.
        id_token: Cognito/AppSync ID token (Authorization header).
        ws_url: Optional AppSync GraphQL endpoint; if https, auto-converted to realtime wss.
    """

    resolved_ws_url = _resolve_appsync_ws_url(ws_url, "CloudLLMTask")

    def build_ws(token, api_host, signed_url):
        """Build a WebSocketApp with fresh token baked into closures."""

        def on_message(ws, message):
            try:
                data = json.loads(message)
            except Exception:
                data = {"raw": message}
            msg_type = data.get("type")
            # AppSync protocol layer: auth errors are fatal — raise so run_forever
            # exits and the reconnect loop handles them immediately (no backoff).
            if msg_type == "error" and isinstance(data.get("payload"), dict):
                payload = data.get("payload", {})
                # Try structured errors array first (AppSync standard).
                errors = payload.get("errors", [])
                auth_err = None
                for err in errors:
                    err_msg = str(err.get("message", "")).lower()
                    if any(kw in err_msg for kw in ("401", "403", "authorized", "forbidden", "expired")):
                        auth_err = err.get("message", "")
                        break
                # Fallback: some AppSync variants embed the error text directly
                # in payload.message (no errors[] array).
                if auth_err is None:
                    msg_str = str(payload.get("message", "")).lower()
                    if any(kw in msg_str for kw in ("401", "403", "authorized", "forbidden", "expired")):
                        auth_err = payload.get("message", "")
                if auth_err is not None:
                    logger.warning(f"[{label}] AppSync auth error: {auth_err!r}")
                    raise WebSocketException(f"AppSync auth error: {auth_err}")
            if msg_type in ("ka", "keepalive"):
                return
            logger.debug("[CloudLLMTask] Received WebSocket message type=%s", msg_type)
            logger.trace("[CloudLLMTask] Subscription update: %s", json.dumps(data, ensure_ascii=False)[:2000])

            if msg_type == "connection_ack":
                try:
                    subscription = (
                        """
                        subscription OnComplete($acctSiteID: String!) {
                          onLongLLMTaskComplete(acctSiteID: $acctSiteID) {
                            id
                            acctSiteID
                            agentID
                            workType
                            taskID
                            status
                            results
                            timestamp
                          }
                        }
                        """
                    )
                    data_obj = {
                        "query": subscription,
                        "operationName": "OnComplete",
                        "variables": {"acctSiteID": acctSiteID},
                    }
                    start_payload = {
                        "id": "LongLLM1",
                        "type": "start",
                        "payload": {
                            "data": json.dumps(data_obj),
                            "extensions": {
                                "authorization": {
                                    "host": api_host,
                                    "Authorization": token,
                                }
                            },
                        },
                    }
                    logger.info("[CloudLLMTask] connection_ack received, sending start subscription", start_payload)
                    ws.send(json.dumps(start_payload))
                except Exception as e:
                    logger.error(f"[CloudLLMTask] Failed to send start payload: {e}")

            elif msg_type == "data" and isinstance(data.get("payload"), dict) and data.get("id") == "LongLLM1":
                payload_data = data.get("payload", {}).get("data", {})
                result_obj = None
                if isinstance(payload_data, dict):
                    result_obj = payload_data.get("onLongLLMTaskComplete")
                    logger.debug(f"Received long LLM Task subscription result:{json.dumps(result_obj, indent=2, ensure_ascii=False)}")
                    if try_resolve_long_llm_task_waiter(result_obj):
                        return
                    agent_id = result_obj["agentID"]
                    work_type = result_obj["workType"]
                    handler_agent = get_agent_by_id(agent_id)
                    converted_result = convert_cloud_result_to_task_send_params(result_obj, work_type)
                    event_response = handler_agent.runner.sync_task_wait_in_line(work_type, converted_result, source="cloud_websocket")

        def on_error(ws, error):
            logger.error(f"[CloudLLMTask] WebSocket error: {error}")

        def on_close(ws, status_code, msg):
            logger.warning(f"[CloudLLMTask] WebSocket closed: code={status_code}, msg={msg}")

        def on_open(ws):
            logger_helper.debug("CloudLLMTask web socket opened.......")
            try:
                logger_helper.debug("CloudLLMTask sending connection_init ...")
                ws.send(json.dumps({"type": "connection_init", "payload": {}}))
            except Exception as e:
                logger.error(f"[CloudLLMTask] Failed to send connection_init: {e}")

        return websocket.WebSocketApp(
            signed_url, header=[], on_message=on_message, on_error=on_error,
            on_close=on_close, on_open=on_open, subprotocols=["graphql-ws"],
        )

    # Build initial ws for the return value (backward compat)
    initial_signed_url, initial_api_host = _build_appsync_signed_url(resolved_ws_url, id_token)
    ws = build_ws(id_token, initial_api_host, initial_signed_url)

    logger.info("[CloudLLMTask] Launching web socket thread with auto-reconnect")
    t = threading.Thread(
        target=_appsync_ws_reconnect_loop,
        args=("CloudLLMTask", resolved_ws_url, id_token, build_ws),
        daemon=True,
        name=f"CloudLLMTask-ws-{id(token) % 10000}",  # Named for leak debugging
    )
    _track_appsync_ws_thread(t)
    t.start()
    logger.info("[CloudLLMTask] Web socket thread launched")
    return ws, t


# ============================================================================
# Account Notification Subscription (WebSocket)
# ============================================================================

def subscribe_account_notifications(owner: str, id_token: str, ws_url: Optional[str] = None,
                                     on_notification_callback=None) -> Tuple[websocket.WebSocketApp, threading.Thread]:
    """Subscribe to account notifications over WebSocket.

    Parameters:
        owner: Owner email/identifier for the subscription filter.
        id_token: Cognito/AppSync ID token (Authorization header).
        ws_url: Optional AppSync GraphQL endpoint; if https, auto-converted to realtime wss.
        on_notification_callback: Optional callback function(notification_data) to handle received notifications.
    """

    resolved_ws_url = _resolve_appsync_ws_url(ws_url, "AccountNotification")

    def build_ws(token, api_host, signed_url):
        def on_message(ws, message):
            try:
                data = json.loads(message)
            except Exception:
                data = {"raw": message}
            msg_type = data.get("type")
            # AppSync protocol layer: auth errors are fatal — raise so run_forever
            # exits and the reconnect loop handles them immediately (no backoff).
            if msg_type == "error" and isinstance(data.get("payload"), dict):
                payload = data.get("payload", {})
                # Try structured errors array first (AppSync standard).
                errors = payload.get("errors", [])
                auth_err = None
                for err in errors:
                    err_msg = str(err.get("message", "")).lower()
                    if any(kw in err_msg for kw in ("401", "403", "authorized", "forbidden", "expired")):
                        auth_err = err.get("message", "")
                        break
                # Fallback: some AppSync variants embed the error text directly
                # in payload.message (no errors[] array).
                if auth_err is None:
                    msg_str = str(payload.get("message", "")).lower()
                    if any(kw in msg_str for kw in ("401", "403", "authorized", "forbidden", "expired")):
                        auth_err = payload.get("message", "")
                if auth_err is not None:
                    logger.warning(f"[{label}] AppSync auth error: {auth_err!r}")
                    raise WebSocketException(f"AppSync auth error: {auth_err}")
            if msg_type in ("ka", "keepalive"):
                return
            logger.debug("[AccountNotification] Received WebSocket message type=%s", msg_type)
            logger.trace("[AccountNotification] Subscription update: %s", json.dumps(data, ensure_ascii=False)[:2000])

            if msg_type == "connection_ack":
                try:
                    subscription = (
                        """
                        subscription OnAccountNotification($owner: String!) {
                          onAccountNotification(owner: $owner) {
                            id
                            ntype
                            title
                            message
                            payload
                            cta_url
                            created_at
                          }
                        }
                        """
                    )
                    data_obj = {
                        "query": subscription,
                        "operationName": "OnAccountNotification",
                        "variables": {"owner": owner},
                    }
                    start_payload = {
                        "id": "AccountNotification1",
                        "type": "start",
                        "payload": {
                            "data": json.dumps(data_obj),
                            "extensions": {
                                "authorization": {
                                    "host": api_host,
                                    "Authorization": token,
                                }
                            },
                        },
                    }
                    logger.info("[AccountNotification] connection_ack received, sending start subscription")
                    ws.send(json.dumps(start_payload))
                except Exception as e:
                    logger.error(f"[AccountNotification] Failed to send start payload: {e}")

            elif msg_type == "data" and isinstance(data.get("payload"), dict) and data.get("id") == "AccountNotification1":
                payload_data = data.get("payload", {}).get("data", {})
                notification = None
                if isinstance(payload_data, dict):
                    notification = payload_data.get("onAccountNotification")
                    logger.info(f"[AccountNotification] Received notification: {json.dumps(notification, indent=2, ensure_ascii=False)}")
                    if on_notification_callback and notification:
                        try:
                            on_notification_callback(notification)
                        except Exception as cb_err:
                            logger.error(f"[AccountNotification] Callback error: {cb_err}")

        def on_error(ws, error):
            logger.error(f"[AccountNotification] WebSocket error: {error}")

        def on_close(ws, status_code, msg):
            logger.warning(f"[AccountNotification] WebSocket closed: code={status_code}, msg={msg}")

        def on_open(ws):
            logger_helper.debug("[AccountNotification] WebSocket opened")
            try:
                logger_helper.debug("[AccountNotification] Sending connection_init...")
                ws.send(json.dumps({"type": "connection_init", "payload": {}}))
            except Exception as e:
                logger.error(f"[AccountNotification] Failed to send connection_init: {e}")

        return websocket.WebSocketApp(
            signed_url, header=[], on_message=on_message, on_error=on_error,
            on_close=on_close, on_open=on_open, subprotocols=["graphql-ws"],
        )

    initial_signed_url, initial_api_host = _build_appsync_signed_url(resolved_ws_url, id_token)
    ws = build_ws(id_token, initial_api_host, initial_signed_url)

    logger.info("[AccountNotification] Launching WebSocket thread with auto-reconnect")
    t = threading.Thread(
        target=_appsync_ws_reconnect_loop,
        args=("AccountNotification", resolved_ws_url, id_token, build_ws),
        daemon=True,
        name=f"AccountNotification-ws-{id(token) % 10000}",
    )
    _track_appsync_ws_thread(t)
    t.start()
    logger.info("[AccountNotification] WebSocket thread launched")
    return ws, t


def handle_account_notification(notification: dict):
    """
    Default handler for account notifications.
    Links notifications to ad banner and notification popup.
    
    Args:
        notification: Dict with keys: id, ntype, title, message, payload, cta_url, created_at
    """
    try:
        from gui.ipc.w2p_handlers.ad_handler import push_ad_to_frontend
        
        notification_type = notification.get("ntype", "")
        title = notification.get("title", "")
        message = notification.get("message", "")
        payload = notification.get("payload", {})
        cta_url = notification.get("cta_url", "")
        
        # Parse payload if it's a string
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except:
                payload = {}
        
        logger.info(f"[AccountNotification] Handling notification: type={notification_type}, title={title}")
        
        # Build banner text
        banner_text = f"📢 {title}" if title else f"📢 {message[:50]}..."
        
        # Build popup HTML
        popup_html = f"""
        <div style="padding: 20px; font-family: Arial, sans-serif;">
            <h2 style="margin-top: 0; color: #333;">{title}</h2>
            <p style="color: #666; line-height: 1.6;">{message}</p>
        """
        
        # Add payload info if present
        if payload:
            popup_html += '<div style="background: #f5f5f5; padding: 10px; border-radius: 5px; margin: 10px 0;">'
            for key, value in payload.items():
                popup_html += f'<p style="margin: 5px 0;"><strong>{key}:</strong> {value}</p>'
            popup_html += '</div>'
        
        # Add CTA button if URL provided
        if cta_url:
            popup_html += f"""
            <a href="{cta_url}" target="_blank" 
               style="display: inline-block; background: #007bff; color: white; 
                      padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 10px;">
                Learn More
            </a>
            """
        
        popup_html += "</div>"
        
        # Determine duration based on notification type
        duration_ms = 60000  # Default 1 minute
        if notification_type in ("urgent", "alert", "critical"):
            duration_ms = 120000  # 2 minutes for urgent
        elif notification_type in ("info", "tip"):
            duration_ms = 30000  # 30 seconds for info
        
        # Push to frontend
        push_ad_to_frontend(
            banner_text=banner_text,
            popup_html=popup_html,
            duration_ms=duration_ms
        )
        
        logger.info(f"[AccountNotification] Pushed notification to frontend: {title}")
        
    except Exception as e:
        logger.error(f"[AccountNotification] Error handling notification: {e}")
        import traceback
        logger.error(traceback.format_exc())


# ============================================================================
# Scene & Story Subscriptions (WebSocket)
# ============================================================================

def subscribe_agent_scene_events(acct_site_id: str, id_token: str, ws_url: Optional[str] = None,
                                  on_scene_callback=None, agent_id_filter: str = None) -> Tuple[websocket.WebSocketApp, threading.Thread]:
    """Subscribe to agent scene events over WebSocket.

    GraphQL: onAgentSceneEvent(acctSiteID: String!): Scene

    Parameters:
        acct_site_id: Account site ID for the subscription filter.
        id_token: Cognito/AppSync ID token (Authorization header).
        ws_url: Optional AppSync GraphQL endpoint; if https, auto-converted to realtime wss.
        on_scene_callback: Optional callback function(scene_data) to handle received scene events.
        agent_id_filter: Optional agent ID to filter events client-side (not sent to AppSync).
    """

    resolved_ws_url = _resolve_appsync_ws_url(ws_url, "AgentSceneEvent")

    def build_ws(token, api_host, signed_url):
        def on_message(ws, message):
            try:
                data = json.loads(message)
            except Exception:
                data = {"raw": message}
            msg_type = data.get("type")
            # AppSync protocol layer: auth errors are fatal — raise so run_forever
            # exits and the reconnect loop handles them immediately (no backoff).
            if msg_type == "error" and isinstance(data.get("payload"), dict):
                payload = data.get("payload", {})
                # Try structured errors array first (AppSync standard).
                errors = payload.get("errors", [])
                auth_err = None
                for err in errors:
                    err_msg = str(err.get("message", "")).lower()
                    if any(kw in err_msg for kw in ("401", "403", "authorized", "forbidden", "expired")):
                        auth_err = err.get("message", "")
                        break
                # Fallback: some AppSync variants embed the error text directly
                # in payload.message (no errors[] array).
                if auth_err is None:
                    msg_str = str(payload.get("message", "")).lower()
                    if any(kw in msg_str for kw in ("401", "403", "authorized", "forbidden", "expired")):
                        auth_err = payload.get("message", "")
                if auth_err is not None:
                    logger.warning(f"[{label}] AppSync auth error: {auth_err!r}")
                    raise WebSocketException(f"AppSync auth error: {auth_err}")
            if msg_type in ("ka", "keepalive"):
                return
            logger.debug(f"[AgentSceneEvent] Message type: {msg_type}")
            logger.trace(f"[AgentSceneEvent] full data: {json.dumps(data, ensure_ascii=False)[:2000]}")

            if msg_type == "connection_ack":
                try:
                    subscription = """
                        subscription OnAgentSceneEvent($acctSiteID: String!) {
                          onAgentSceneEvent(acctSiteID: $acctSiteID) {
                            id
                            scene_id
                            acctSiteID
                            agent_ids
                            label
                            description
                            clip
                            duration_ms
                            status
                            priority
                            n_repeat
                            actions
                            dialogs
                            captions
                            trigger_events
                            images
                            video
                            thumbnails
                            timestamp
                          }
                        }
                    """
                    data_obj = {
                        "query": subscription,
                        "operationName": "OnAgentSceneEvent",
                        "variables": {"acctSiteID": acct_site_id},
                    }
                    start_payload = {
                        "id": "AgentSceneEvent1",
                        "type": "start",
                        "payload": {
                            "data": json.dumps(data_obj),
                            "extensions": {
                                "authorization": {
                                    "host": api_host,
                                    "Authorization": token,
                                }
                            },
                        },
                    }
                    logger.debug(f"[AgentSceneEvent] connection_ack received, sending start subscription with acctSiteID='{acct_site_id}'")
                    ws.send(json.dumps(start_payload))
                except Exception as e:
                    logger.error(f"[AgentSceneEvent] Failed to send start payload: {e}")

            elif msg_type == "start_ack":
                logger.debug(f"[AgentSceneEvent] Subscription started successfully (start_ack received)")
                return
            elif msg_type == "error":
                logger.error(f"[AgentSceneEvent] Subscription error: {json.dumps(data, indent=2)}")
                return
            elif msg_type == "data" and isinstance(data.get("payload"), dict) and data.get("id") == "AgentSceneEvent1":
                payload_data = data.get("payload", {}).get("data", {})
                scene = None
                if isinstance(payload_data, dict):
                    scene = payload_data.get("onAgentSceneEvent")
                    logger.debug(
                        "[AgentSceneEvent] Received scene event: id=%s scene_id=%s status=%s",
                        scene.get("id") if scene else None,
                        scene.get("scene_id") if scene else None,
                        scene.get("status") if scene else None,
                    )
                    logger.trace("[AgentSceneEvent] scene detail: %s", json.dumps(scene, ensure_ascii=False)[:2000] if scene else "")
                    if agent_id_filter and scene:
                        scene_agent_ids = scene.get("agent_ids", [])
                        if agent_id_filter not in scene_agent_ids:
                            logger.debug(f"[AgentSceneEvent] Skipping scene - agent_id_filter '{agent_id_filter}' not in {scene_agent_ids}")
                            return
                    if on_scene_callback and scene:
                        try:
                            on_scene_callback(scene)
                        except Exception as cb_err:
                            logger.error(f"[AgentSceneEvent] Callback error: {cb_err}")

        def on_error(ws, error):
            logger.error(f"[AgentSceneEvent] WebSocket error: {error}")

        def on_close(ws, status_code, msg):
            logger.warning(f"[AgentSceneEvent] WebSocket closed: code={status_code}, msg={msg}")

        def on_open(ws):
            logger.debug("[AgentSceneEvent] WebSocket opened")
            try:
                ws.send(json.dumps({"type": "connection_init", "payload": {}}))
            except Exception as e:
                logger.error(f"[AgentSceneEvent] Failed to send connection_init: {e}")

        return websocket.WebSocketApp(
            signed_url, header=[], on_message=on_message, on_error=on_error,
            on_close=on_close, on_open=on_open, subprotocols=["graphql-ws"],
        )

    initial_signed_url, initial_api_host = _build_appsync_signed_url(resolved_ws_url, id_token)
    ws = build_ws(id_token, initial_api_host, initial_signed_url)

    logger.info("[AgentSceneEvent] Launching WebSocket thread with auto-reconnect")
    t = threading.Thread(
        target=_appsync_ws_reconnect_loop,
        args=("AgentSceneEvent", resolved_ws_url, id_token, build_ws),
        daemon=True,
        name=f"AgentSceneEvent-ws-{id(token) % 10000}",
    )
    _track_appsync_ws_thread(t)
    t.start()
    logger.info("[AgentSceneEvent] WebSocket thread launched")
    return ws, t


def handle_agent_scene_event(scene: dict):
    """Placeholder handler for agent scene events."""
    logger.info(f"[AgentSceneEvent] Handler called with scene: {scene.get('scene_id', 'unknown')}")
    # TODO: Wire up actual scene handling logic


def subscribe_puzzle_results(id_token: str, ws_url: Optional[str] = None,
                              on_puzzle_callback=None) -> Tuple[websocket.WebSocketApp, threading.Thread]:
    """Subscribe to puzzle results over WebSocket.

    GraphQL: onPuzzleResultReceived: PuzzleResult

    Parameters:
        id_token: Cognito/AppSync ID token (Authorization header).
        ws_url: Optional AppSync GraphQL endpoint.
        on_puzzle_callback: Optional callback function(puzzle_result) to handle received puzzle results.
    """

    resolved_ws_url = _resolve_appsync_ws_url(ws_url, "PuzzleResult")

    def build_ws(token, api_host, signed_url):
        def on_message(ws, message):
            try:
                data = json.loads(message)
            except Exception:
                data = {"raw": message}
            msg_type = data.get("type")
            # AppSync protocol layer: auth errors are fatal — raise so run_forever
            # exits and the reconnect loop handles them immediately (no backoff).
            if msg_type == "error" and isinstance(data.get("payload"), dict):
                payload = data.get("payload", {})
                # Try structured errors array first (AppSync standard).
                errors = payload.get("errors", [])
                auth_err = None
                for err in errors:
                    err_msg = str(err.get("message", "")).lower()
                    if any(kw in err_msg for kw in ("401", "403", "authorized", "forbidden", "expired")):
                        auth_err = err.get("message", "")
                        break
                # Fallback: some AppSync variants embed the error text directly
                # in payload.message (no errors[] array).
                if auth_err is None:
                    msg_str = str(payload.get("message", "")).lower()
                    if any(kw in msg_str for kw in ("401", "403", "authorized", "forbidden", "expired")):
                        auth_err = payload.get("message", "")
                if auth_err is not None:
                    logger.warning(f"[{label}] AppSync auth error: {auth_err!r}")
                    raise WebSocketException(f"AppSync auth error: {auth_err}")
            if msg_type in ("ka", "keepalive"):
                return
            logger.debug("[PuzzleResult] Received WebSocket message type=%s", msg_type)
            logger.trace("[PuzzleResult] Subscription update: %s", json.dumps(data, ensure_ascii=False)[:2000])

            if msg_type == "connection_ack":
                try:
                    subscription = """
                        subscription OnPuzzleResultReceived {
                          onPuzzleResultReceived {
                            id
                            request_id
                            solver_id
                            solution
                            timestamp
                          }
                        }
                    """
                    data_obj = {
                        "query": subscription,
                        "operationName": "OnPuzzleResultReceived",
                        "variables": {},
                    }
                    start_payload = {
                        "id": "PuzzleResult1",
                        "type": "start",
                        "payload": {
                            "data": json.dumps(data_obj),
                            "extensions": {
                                "authorization": {
                                    "host": api_host,
                                    "Authorization": token,
                                }
                            },
                        },
                    }
                    logger.info("[PuzzleResult] connection_ack received, sending start subscription")
                    ws.send(json.dumps(start_payload))
                except Exception as e:
                    logger.error(f"[PuzzleResult] Failed to send start payload: {e}")

            elif msg_type == "data" and isinstance(data.get("payload"), dict) and data.get("id") == "PuzzleResult1":
                payload_data = data.get("payload", {}).get("data", {})
                puzzle_result = None
                if isinstance(payload_data, dict):
                    puzzle_result = payload_data.get("onPuzzleResultReceived")
                    logger.info(f"[PuzzleResult] Received puzzle result: {json.dumps(puzzle_result, indent=2, ensure_ascii=False)}")
                    if on_puzzle_callback and puzzle_result:
                        try:
                            on_puzzle_callback(puzzle_result)
                        except Exception as cb_err:
                            logger.error(f"[PuzzleResult] Callback error: {cb_err}")

        def on_error(ws, error):
            logger.error(f"[PuzzleResult] WebSocket error: {error}")

        def on_close(ws, status_code, msg):
            logger.warning(f"[PuzzleResult] WebSocket closed: code={status_code}, msg={msg}")

        def on_open(ws):
            logger.debug("[PuzzleResult] WebSocket opened")
            try:
                ws.send(json.dumps({"type": "connection_init", "payload": {}}))
            except Exception as e:
                logger.error(f"[PuzzleResult] Failed to send connection_init: {e}")

        return websocket.WebSocketApp(
            signed_url, header=[], on_message=on_message, on_error=on_error,
            on_close=on_close, on_open=on_open, subprotocols=["graphql-ws"],
        )

    initial_signed_url, initial_api_host = _build_appsync_signed_url(resolved_ws_url, id_token)
    ws = build_ws(id_token, initial_api_host, initial_signed_url)

    logger.info("[PuzzleResult] Launching WebSocket thread with auto-reconnect")
    t = threading.Thread(
        target=_appsync_ws_reconnect_loop,
        args=("PuzzleResult", resolved_ws_url, id_token, build_ws),
        daemon=True,
        name=f"PuzzleResult-ws-{id(token) % 10000}",
    )
    _track_appsync_ws_thread(t)
    t.start()
    logger.info("[PuzzleResult] WebSocket thread launched")
    return ws, t


def handle_puzzle_result(puzzle_result: dict):
    """Placeholder handler for puzzle results (PuzzleSolution type)."""
    logger.info(f"[PuzzleResult] Handler called with request_id: {puzzle_result.get('request_id', 'unknown')}, solver_id: {puzzle_result.get('solver_id', 'unknown')}")
    # TODO: Wire up actual puzzle solution handling logic


def subscribe_scene_complete(acct_site_id: str, id_token: str, ws_url: Optional[str] = None,
                              on_scene_complete_callback=None) -> Tuple[websocket.WebSocketApp, threading.Thread]:
    """Subscribe to scene completion events over WebSocket.

    GraphQL: onSceneComplete(acctSiteID: String!): SceneResult

    Parameters:
        acct_site_id: Account site ID for the subscription filter.
        id_token: Cognito/AppSync ID token (Authorization header).
        ws_url: Optional AppSync GraphQL endpoint.
        on_scene_complete_callback: Optional callback function(scene_result) to handle scene completion.
    """

    resolved_ws_url = _resolve_appsync_ws_url(ws_url, "SceneComplete")

    def build_ws(token, api_host, signed_url):
        def on_message(ws, message):
            try:
                data = json.loads(message)
            except Exception:
                data = {"raw": message}
            msg_type = data.get("type")
            # AppSync protocol layer: auth errors are fatal — raise so run_forever
            # exits and the reconnect loop handles them immediately (no backoff).
            if msg_type == "error" and isinstance(data.get("payload"), dict):
                payload = data.get("payload", {})
                # Try structured errors array first (AppSync standard).
                errors = payload.get("errors", [])
                auth_err = None
                for err in errors:
                    err_msg = str(err.get("message", "")).lower()
                    if any(kw in err_msg for kw in ("401", "403", "authorized", "forbidden", "expired")):
                        auth_err = err.get("message", "")
                        break
                # Fallback: some AppSync variants embed the error text directly
                # in payload.message (no errors[] array).
                if auth_err is None:
                    msg_str = str(payload.get("message", "")).lower()
                    if any(kw in msg_str for kw in ("401", "403", "authorized", "forbidden", "expired")):
                        auth_err = payload.get("message", "")
                if auth_err is not None:
                    logger.warning(f"[{label}] AppSync auth error: {auth_err!r}")
                    raise WebSocketException(f"AppSync auth error: {auth_err}")
            if msg_type in ("ka", "keepalive"):
                return
            logger.debug("[SceneComplete] Received WebSocket message type=%s", msg_type)
            logger.trace("[SceneComplete] Subscription update: %s", json.dumps(data, ensure_ascii=False)[:2000])

            if msg_type == "connection_ack":
                try:
                    subscription = """
                        subscription OnSceneComplete($acctSiteID: String!) {
                          onSceneComplete(acctSiteID: $acctSiteID) {
                            id
                            request_id
                            scene_id
                            acctSiteID
                            agent_ids
                            description
                            status
                            duration_ms
                            video
                            thumbnail
                            emotion
                            mind_state
                            actions
                            dialogs
                            error
                            timestamp
                          }
                        }
                    """
                    data_obj = {
                        "query": subscription,
                        "operationName": "OnSceneComplete",
                        "variables": {"acctSiteID": acct_site_id},
                    }
                    start_payload = {
                        "id": "SceneComplete1",
                        "type": "start",
                        "payload": {
                            "data": json.dumps(data_obj),
                            "extensions": {
                                "authorization": {
                                    "host": api_host,
                                    "Authorization": token,
                                }
                            },
                        },
                    }
                    logger.info("[SceneComplete] connection_ack received, sending start subscription")
                    ws.send(json.dumps(start_payload))
                except Exception as e:
                    logger.error(f"[SceneComplete] Failed to send start payload: {e}")

            elif msg_type == "data" and isinstance(data.get("payload"), dict) and data.get("id") == "SceneComplete1":
                payload_data = data.get("payload", {}).get("data", {})
                scene_result = None
                if isinstance(payload_data, dict):
                    scene_result = payload_data.get("onSceneComplete")
                    logger.info(f"[SceneComplete] Received scene result: {json.dumps(scene_result, indent=2, ensure_ascii=False)}")
                    if on_scene_complete_callback and scene_result:
                        try:
                            on_scene_complete_callback(scene_result)
                        except Exception as cb_err:
                            logger.error(f"[SceneComplete] Callback error: {cb_err}")

        def on_error(ws, error):
            logger.error(f"[SceneComplete] WebSocket error: {error}")

        def on_close(ws, status_code, msg):
            logger.warning(f"[SceneComplete] WebSocket closed: code={status_code}, msg={msg}")

        def on_open(ws):
            logger.debug("[SceneComplete] WebSocket opened")
            try:
                ws.send(json.dumps({"type": "connection_init", "payload": {}}))
            except Exception as e:
                logger.error(f"[SceneComplete] Failed to send connection_init: {e}")

        return websocket.WebSocketApp(
            signed_url, header=[], on_message=on_message, on_error=on_error,
            on_close=on_close, on_open=on_open, subprotocols=["graphql-ws"],
        )

    initial_signed_url, initial_api_host = _build_appsync_signed_url(resolved_ws_url, id_token)
    ws = build_ws(id_token, initial_api_host, initial_signed_url)

    logger.info("[SceneComplete] Launching WebSocket thread with auto-reconnect")
    t = threading.Thread(
        target=_appsync_ws_reconnect_loop,
        args=("SceneComplete", resolved_ws_url, id_token, build_ws),
        daemon=True,
        name=f"SceneComplete-ws-{id(token) % 10000}",
    )
    _track_appsync_ws_thread(t)
    t.start()
    logger.info("[SceneComplete] WebSocket thread launched")
    return ws, t


def handle_scene_complete(scene_result: dict, download_dir: str = "generated_medias"):
    """Handle scene completion events by downloading generated media.
    
    Downloads the generated media from presigned S3 URLs to local directory.
    
    Args:
        scene_result: Scene completion result dict containing:
            - id/request_id: Unique identifier for the scene request
            - status: COMPLETED, FAILED, etc.
            - downloadUrl: Presigned S3 URL for the generated media
            - video: URL for video output (if applicable)
            - thumbnail: URL for thumbnail (if applicable)
            - outputS3Uri: S3 URI of the output file
            - payload: Additional job details
        download_dir: Local directory to save downloaded files (default: "generated_medias")
        
    Returns:
        dict: Result with downloaded file paths and status
    """
    import requests
    from urllib.parse import urlparse, unquote
    
    logger.info("=" * 60)
    logger.info("[SceneComplete] Handler called")
    logger.info(f"[SceneComplete] Scene result: {json.dumps(scene_result, indent=2, default=str)}")
    
    result = {
        "success": False,
        "request_id": "",
        "downloaded_files": [],
        "errors": []
    }
    
    try:
        # Extract identifiers
        request_id = scene_result.get("request_id") or scene_result.get("id") or "unknown"
        result["request_id"] = request_id
        
        status = scene_result.get("status", "")
        logger.info(f"[SceneComplete] Request ID: {request_id}, Status: {status}")
        
        # Check if generation was successful
        if status.upper() not in ["COMPLETED", "SUCCESS"]:
            error_msg = scene_result.get("error", f"Scene generation failed with status: {status}")
            logger.error(f"[SceneComplete] Generation failed: {error_msg}")
            result["errors"].append(error_msg)
            return result
        
        # Create download directory if it doesn't exist
        os.makedirs(download_dir, exist_ok=True)
        logger.info(f"[SceneComplete] Download directory: {os.path.abspath(download_dir)}")
        
        # Collect all download URLs
        download_urls = []
        
        # Primary download URL (can be string or list)
        download_url = scene_result.get("downloadUrl")
        if download_url:
            if isinstance(download_url, list):
                for i, url in enumerate(download_url):
                    download_urls.append((f"output_{i}" if len(download_url) > 1 else "output", url))
            else:
                download_urls.append(("output", download_url))
        
        # Video URL (can be string or list)
        video_url = scene_result.get("video")
        if video_url:
            if isinstance(video_url, list):
                for i, url in enumerate(video_url):
                    download_urls.append((f"video_{i}" if len(video_url) > 1 else "video", url))
            else:
                download_urls.append(("video", video_url))
        
        # Thumbnail URL (can be string or list)
        thumbnail_url = scene_result.get("thumbnail")
        if thumbnail_url:
            if isinstance(thumbnail_url, list):
                for i, url in enumerate(thumbnail_url):
                    download_urls.append((f"thumbnail_{i}" if len(thumbnail_url) > 1 else "thumbnail", url))
            else:
                download_urls.append(("thumbnail", thumbnail_url))
        
        if not download_urls:
            logger.warning("[SceneComplete] No download URLs found in scene result")
            result["errors"].append("No download URLs found in scene result")
            return result
        
        logger.info(f"[SceneComplete] Found {len(download_urls)} file(s) to download")
        
        # Download each file
        for file_type, url in download_urls:
            try:
                logger.info(f"[SceneComplete] Downloading {file_type}: {url[:100]}...")
                
                # Extract filename from URL or generate one
                parsed_url = urlparse(url)
                url_path = unquote(parsed_url.path)
                original_filename = os.path.basename(url_path)
                
                # Generate a unique filename with request_id prefix
                if original_filename:
                    # Keep original extension
                    _, ext = os.path.splitext(original_filename)
                    if not ext:
                        # Try to guess extension from content-type later
                        ext = ".bin"
                    filename = f"{request_id}_{file_type}{ext}"
                else:
                    filename = f"{request_id}_{file_type}.bin"
                
                local_path = os.path.join(download_dir, filename)
                
                # Download the file with retry mechanism
                max_retries = 3
                download_success = False
                last_error = None
                
                for retry in range(max_retries):
                    try:
                        # Use streaming download with dynamic timeout
                        # Estimate file size from Content-Length if available, otherwise use conservative timeout
                        response = requests.get(url, stream=True, timeout=60)  # Initial connection timeout
                        response.raise_for_status()
                        
                        # Get file size from Content-Length header
                        content_length = response.headers.get('Content-Length')
                        if content_length:
                            file_size = int(content_length)
                            file_size_mb = file_size / (1024 * 1024)
                            # Calculate read timeout based on file size (min 30s, max 600s)
                            read_timeout = _calculate_upload_timeout(file_size, min_speed_kbps=100)  # Assume faster download
                            logger.info(f"[Download] File size: {file_size_mb:.2f} MB, timeout: {read_timeout}s")
                        else:
                            read_timeout = 300  # Default 5 minutes if size unknown
                            logger.info(f"[Download] File size unknown, using default timeout: {read_timeout}s")
                        
                        download_success = True
                        break
                        
                    except requests.Timeout:
                        last_error = f"Timeout during download"
                        if retry < max_retries - 1:
                            wait_time = 2 ** retry
                            logger.warning(f"⏱️  Download timeout, retrying in {wait_time}s...")
                            import time
                            time.sleep(wait_time)
                        else:
                            logger.error(f"❌ Download failed after {max_retries} retries")
                    except Exception as e:
                        last_error = str(e)
                        logger.error(f"❌ Download error: {e}")
                        if retry < max_retries - 1:
                            wait_time = 2 ** retry
                            import time
                            time.sleep(wait_time)
                        else:
                            raise
                
                if not download_success:
                    logger.error(f"Failed to download {file_type}: {last_error}")
                    continue
                
                # Get content type to determine extension if needed
                content_type = response.headers.get("Content-Type", "")
                if filename.endswith(".bin"):
                    # Update extension based on content type
                    ext_map = {
                        "image/png": ".png",
                        "image/jpeg": ".jpg",
                        "image/gif": ".gif",
                        "image/webp": ".webp",
                        "video/mp4": ".mp4",
                        "video/webm": ".webm",
                        "audio/mpeg": ".mp3",
                        "audio/wav": ".wav",
                    }
                    for ct, ext in ext_map.items():
                        if ct in content_type:
                            filename = filename.replace(".bin", ext)
                            local_path = os.path.join(download_dir, filename)
                            break
                
                # Write to file
                total_size = 0
                with open(local_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            total_size += len(chunk)
                
                logger.info(f"[SceneComplete] ✅ Downloaded {file_type}: {local_path} ({total_size} bytes)")
                result["downloaded_files"].append({
                    "type": file_type,
                    "path": local_path,
                    "size": total_size,
                    "content_type": content_type
                })
                
            except requests.exceptions.RequestException as e:
                error_msg = f"Failed to download {file_type}: {str(e)}"
                logger.error(f"[SceneComplete] ❌ {error_msg}")
                result["errors"].append(error_msg)
            except Exception as e:
                error_msg = f"Error processing {file_type}: {str(e)}"
                logger.error(f"[SceneComplete] ❌ {error_msg}")
                result["errors"].append(error_msg)
        
        # Mark success if at least one file was downloaded
        if result["downloaded_files"]:
            result["success"] = True
            logger.info(f"[SceneComplete] ✅ Successfully downloaded {len(result['downloaded_files'])} file(s)")
        else:
            logger.error("[SceneComplete] ❌ No files were downloaded")
        
    except Exception as e:
        error_msg = f"handle_scene_complete error: {str(e)}"
        logger.error(f"[SceneComplete] ❌ {error_msg}")
        import traceback
        logger.error(traceback.format_exc())
        result["errors"].append(error_msg)
    
    logger.info(f"[SceneComplete] Final result: {json.dumps(result, indent=2, default=str)}")
    logger.info("=" * 60)
    
    return result


def subscribe_story_updates(acct_site_id: str, id_token: str, ws_url: Optional[str] = None,
                             on_story_callback=None) -> Tuple[websocket.WebSocketApp, threading.Thread]:
    """Subscribe to story updates over WebSocket.

    GraphQL: onStoryUpdate(acctSiteID: String!): Story

    Parameters:
        acct_site_id: Account site ID for the subscription filter.
        id_token: Cognito/AppSync ID token (Authorization header).
        ws_url: Optional AppSync GraphQL endpoint.
        on_story_callback: Optional callback function(story_data) to handle story updates.
    """

    resolved_ws_url = _resolve_appsync_ws_url(ws_url, "StoryUpdate")

    def build_ws(token, api_host, signed_url):
        def on_message(ws, message):
            try:
                data = json.loads(message)
            except Exception:
                data = {"raw": message}
            msg_type = data.get("type")
            # AppSync protocol layer: auth errors are fatal — raise so run_forever
            # exits and the reconnect loop handles them immediately (no backoff).
            if msg_type == "error" and isinstance(data.get("payload"), dict):
                payload = data.get("payload", {})
                # Try structured errors array first (AppSync standard).
                errors = payload.get("errors", [])
                auth_err = None
                for err in errors:
                    err_msg = str(err.get("message", "")).lower()
                    if any(kw in err_msg for kw in ("401", "403", "authorized", "forbidden", "expired")):
                        auth_err = err.get("message", "")
                        break
                # Fallback: some AppSync variants embed the error text directly
                # in payload.message (no errors[] array).
                if auth_err is None:
                    msg_str = str(payload.get("message", "")).lower()
                    if any(kw in msg_str for kw in ("401", "403", "authorized", "forbidden", "expired")):
                        auth_err = payload.get("message", "")
                if auth_err is not None:
                    logger.warning(f"[{label}] AppSync auth error: {auth_err!r}")
                    raise WebSocketException(f"AppSync auth error: {auth_err}")
            if msg_type in ("ka", "keepalive"):
                return
            logger.debug("[StoryUpdate] Received WebSocket message type=%s", msg_type)
            logger.trace("[StoryUpdate] Subscription update: %s", json.dumps(data, ensure_ascii=False)[:2000])

            if msg_type == "connection_ack":
                try:
                    subscription = """
                        subscription OnStoryUpdate($acctSiteID: String!) {
                          onStoryUpdate(acctSiteID: $acctSiteID) {
                            id
                            acctSiteID
                            title
                            description
                            agent_ids
                            status
                            current_scene_index
                            scenes {
                              id
                              scene_id
                              label
                              status
                            }
                            created_at
                            updated_at
                          }
                        }
                    """
                    data_obj = {
                        "query": subscription,
                        "operationName": "OnStoryUpdate",
                        "variables": {"acctSiteID": acct_site_id},
                    }
                    start_payload = {
                        "id": "StoryUpdate1",
                        "type": "start",
                        "payload": {
                            "data": json.dumps(data_obj),
                            "extensions": {
                                "authorization": {
                                    "host": api_host,
                                    "Authorization": token,
                                }
                            },
                        },
                    }
                    logger.info("[StoryUpdate] connection_ack received, sending start subscription")
                    ws.send(json.dumps(start_payload))
                except Exception as e:
                    logger.error(f"[StoryUpdate] Failed to send start payload: {e}")

            elif msg_type == "data" and isinstance(data.get("payload"), dict) and data.get("id") == "StoryUpdate1":
                payload_data = data.get("payload", {}).get("data", {})
                story = None
                if isinstance(payload_data, dict):
                    story = payload_data.get("onStoryUpdate")
                    logger.info(f"[StoryUpdate] Received story update: {json.dumps(story, indent=2, ensure_ascii=False)}")
                    if on_story_callback and story:
                        try:
                            on_story_callback(story)
                        except Exception as cb_err:
                            logger.error(f"[StoryUpdate] Callback error: {cb_err}")

        def on_error(ws, error):
            logger.error(f"[StoryUpdate] WebSocket error: {error}")

        def on_close(ws, status_code, msg):
            logger.warning(f"[StoryUpdate] WebSocket closed: code={status_code}, msg={msg}")

        def on_open(ws):
            logger.debug("[StoryUpdate] WebSocket opened")
            try:
                ws.send(json.dumps({"type": "connection_init", "payload": {}}))
            except Exception as e:
                logger.error(f"[StoryUpdate] Failed to send connection_init: {e}")

        return websocket.WebSocketApp(
            signed_url, header=[], on_message=on_message, on_error=on_error,
            on_close=on_close, on_open=on_open, subprotocols=["graphql-ws"],
        )

    initial_signed_url, initial_api_host = _build_appsync_signed_url(resolved_ws_url, id_token)
    ws = build_ws(id_token, initial_api_host, initial_signed_url)

    logger.info("[StoryUpdate] Launching WebSocket thread with auto-reconnect")
    t = threading.Thread(
        target=_appsync_ws_reconnect_loop,
        args=("StoryUpdate", resolved_ws_url, id_token, build_ws),
        daemon=True,
        name=f"StoryUpdate-ws-{id(token) % 10000}",
    )
    _track_appsync_ws_thread(t)
    t.start()
    logger.info("[StoryUpdate] WebSocket thread launched")
    return ws, t


def handle_story_update(story: dict):
    """Placeholder handler for story updates."""
    logger.info(f"[StoryUpdate] Handler called with story: {story.get('id', 'unknown')}")
    # TODO: Wire up actual story update handling logic


# ============================================================================
# Vehicle Operations (with decorator registration)
# ============================================================================

@cloud_api(DataType.VEHICLE, Operation.ADD)
def send_add_vehicles_request_to_cloud(session, vehicles, token, endpoint, timeout=180):
    """Add vehicles to cloud using new schema"""
    mutationInfo = gen_add_vehicles_string(vehicles)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addVehicles", "addVehicles")


@cloud_api(DataType.VEHICLE, Operation.UPDATE)
def send_update_vehicles_decorated_to_cloud(session, vehicles, token, endpoint, timeout=180):
    """Update vehicles in cloud using new schema"""
    mutationInfo = gen_update_vehicles_new_string(vehicles)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updateVehicles", "updateVehicles")


# ============================================================================
# Knowledge Operations (with decorator registration)
# ============================================================================

@cloud_api(DataType.KNOWLEDGE, Operation.ADD)
def send_add_knowledges_decorated_to_cloud(session, knowledges, token, endpoint, timeout=180):
    """Add Knowledge entities to cloud"""
    mutationInfo = gen_add_knowledges_string(knowledges)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addKnowledges", "addKnowledges")


@cloud_api(DataType.KNOWLEDGE, Operation.UPDATE)
def send_update_knowledges_decorated_to_cloud(session, knowledges, token, endpoint, timeout=180):
    """Update Knowledge entities in cloud"""
    mutationInfo = gen_update_knowledges_string(knowledges)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updateKnowledges", "updateKnowledges")


@cloud_api(DataType.KNOWLEDGE, Operation.DELETE)
def send_remove_knowledges_decorated_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Knowledge entities from cloud"""
    mutationInfo = gen_remove_knowledges_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeKnowledges", "removeKnowledges")


@cloud_api(DataType.KNOWLEDGE, Operation.QUERY)
def send_query_knowledges_decorated_to_cloud(session, token, q_settings, endpoint):
    """Query Knowledge entities from cloud"""
    queryInfo = gen_query_knowledges_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryKnowledges", "queryKnowledges")


# ============================================================================
# Agent Knowledge Operations (New Schema)
# ============================================================================

def gen_add_agent_knowledges_string(knowledges):
    """Generate GraphQL mutation string for adding agent knowledges
    
    New schema: addAgentKnowledges(input: [KnowledgeInput!]!): [KnowledgeMutationResult!]!
    KnowledgeInput has: name (required), id, description, knowledge_type, status, etc.
    """
    query_string = """
        mutation MyMutation {
      addAgentKnowledges (input:[
    """
    rec_string = ""
    for i, k in enumerate(knowledges):
        rec_string += "{ "
        if k.get("id"):
            rec_string += f'id: "{k.get("id")}", '
        rec_string += f'name: "{k.get("name", "")}"'
        if k.get("description"):
            description = k.get("description", "").replace('"', '\\"').replace('\n', '\\n')
            rec_string += f', description: "{description}"'
        if k.get("knowledge_type"):
            rec_string += f', knowledge_type: "{k.get("knowledge_type")}"'
        if k.get("status"):
            rec_string += f', status: "{k.get("status")}"'
        if k.get("path"):
            rec_string += f', path: "{k.get("path")}"'
        if k.get("content"):
            content = k.get("content", "").replace('"', '\\"').replace('\n', '\\n')
            rec_string += f', content: "{content}"'
        if k.get("version"):
            rec_string += f', version: "{k.get("version")}"'
        if k.get("level") is not None:
            rec_string += f', level: {k.get("level")}'
        if k.get("public") is not None:
            rec_string += f', public: {"true" if k.get("public") else "false"}'
        if k.get("rentable") is not None:
            rec_string += f', rentable: {"true" if k.get("rentable") else "false"}'
        if k.get("price") is not None:
            rec_string += f', price: {k.get("price")}'
        if k.get("price_model"):
            rec_string += f', price_model: "{k.get("price_model")}"'
        if k.get("tags"):
            tags = k.get("tags", [])
            if isinstance(tags, (list, dict)):
                tags = json.dumps(tags, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', tags: "{tags}"'
        if k.get("categories"):
            categories = k.get("categories", [])
            if isinstance(categories, (list, dict)):
                categories = json.dumps(categories, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', categories: "{categories}"'
        if k.get("config"):
            config = k.get("config", {})
            if isinstance(config, dict):
                config = json.dumps(config, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', config: "{config}"'
        if k.get("settings"):
            settings = k.get("settings", {})
            if isinstance(settings, dict):
                settings = json.dumps(settings, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', settings: "{settings}"'
        rec_string += " }"
        if i != len(knowledges) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        ) { id success error }
    }
    """
    return query_string


def gen_update_agent_knowledges_string(knowledges):
    """Generate GraphQL mutation string for updating agent knowledges
    
    New schema: updateAgentKnowledges(input: [KnowledgeUpdateInput!]!): [KnowledgeMutationResult!]!
    KnowledgeUpdateInput has: id (required), and many optional fields
    """
    query_string = """
        mutation MyMutation {
      updateAgentKnowledges (input:[
    """
    rec_string = ""
    for i, k in enumerate(knowledges):
        rec_string += "{ "
        rec_string += f'id: "{k.get("id", "")}"'
        if "name" in k:
            rec_string += f', name: "{k.get("name", "")}"'
        if "description" in k:
            description = k.get("description", "").replace('"', '\\"').replace('\n', '\\n')
            rec_string += f', description: "{description}"'
        if "knowledge_type" in k:
            rec_string += f', knowledge_type: "{k.get("knowledge_type", "")}"'
        if "status" in k:
            rec_string += f', status: "{k.get("status", "")}"'
        if "path" in k:
            rec_string += f', path: "{k.get("path", "")}"'
        if "content" in k:
            content = k.get("content", "").replace('"', '\\"').replace('\n', '\\n')
            rec_string += f', content: "{content}"'
        if "version" in k:
            rec_string += f', version: "{k.get("version", "")}"'
        if "level" in k:
            rec_string += f', level: {k.get("level")}'
        if "public" in k:
            rec_string += f', public: {"true" if k.get("public") else "false"}'
        if "rentable" in k:
            rec_string += f', rentable: {"true" if k.get("rentable") else "false"}'
        if "price" in k:
            rec_string += f', price: {k.get("price")}'
        if "price_model" in k:
            rec_string += f', price_model: "{k.get("price_model", "")}"'
        if "tags" in k:
            tags = k.get("tags", [])
            if isinstance(tags, (list, dict)):
                tags = json.dumps(tags, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', tags: "{tags}"'
        if "categories" in k:
            categories = k.get("categories", [])
            if isinstance(categories, (list, dict)):
                categories = json.dumps(categories, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', categories: "{categories}"'
        if "config" in k:
            config = k.get("config", {})
            if isinstance(config, dict):
                config = json.dumps(config, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', config: "{config}"'
        if "settings" in k:
            settings = k.get("settings", {})
            if isinstance(settings, dict):
                settings = json.dumps(settings, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', settings: "{settings}"'
        rec_string += " }"
        if i != len(knowledges) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        ) { id success error }
    }
    """
    return query_string


def gen_remove_agent_knowledges_string(removeOrders):
    """Generate GraphQL mutation string for removing agent knowledges
    
    New schema: removeAgentKnowledges(input: [ID!]!): [KnowledgeMutationResult!]!
    Input is just an array of IDs
    """
    ids = []
    for item in removeOrders:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            ids.append(item.get("id", item.get("oid", "")))
    
    ids_str = ', '.join([f'"{id}"' for id in ids])
    
    query_string = f'''
        mutation MyMutation {{
      removeAgentKnowledges (input: [{ids_str}]) {{ id success error }}
    }}
    '''
    return query_string


def gen_query_agent_knowledges_string(q_settings):
    """Generate GraphQL query string for querying agent knowledges
    
    New schema: queryAgentKnowledges(input: KnowledgeQueryInput): [AgentKnowledge!]!
    KnowledgeQueryInput has: id, name, description (all optional)
    """
    input_parts = []
    if q_settings.get("id"):
        input_parts.append(f'id: "{q_settings["id"]}"')
    if q_settings.get("name"):
        input_parts.append(f'name: "{q_settings["name"]}"')
    if q_settings.get("description"):
        input_parts.append(f'description: "{q_settings["description"]}"')
    
    input_str = ", ".join(input_parts) if input_parts else ""
    
    query_string = f'''query MyKnowledgeQuery {{
  queryAgentKnowledges(input: {{ {input_str} }}) {{
    id
    owner
    name
    description
    knowledge_type
    status
    path
    content
    version
    level
    public
    rentable
    price
    price_model
    tags
    categories
    config
    settings
    access_methods
    limitations
  }}
}}'''
    return query_string


def send_add_agent_knowledges_to_cloud(session, knowledges, token, endpoint, timeout=180):
    """Add Agent Knowledge entities to cloud"""
    mutationInfo = gen_add_agent_knowledges_string(knowledges)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addAgentKnowledges", "addAgentKnowledges")


def send_update_agent_knowledges_to_cloud(session, knowledges, token, endpoint, timeout=180):
    """Update Agent Knowledge entities in cloud"""
    mutationInfo = gen_update_agent_knowledges_string(knowledges)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updateAgentKnowledges", "updateAgentKnowledges")


def send_remove_agent_knowledges_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Agent Knowledge entities from cloud"""
    mutationInfo = gen_remove_agent_knowledges_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeAgentKnowledges", "removeAgentKnowledges")


def send_query_agent_knowledges_to_cloud(session, token, q_settings, endpoint):
    """Query Agent Knowledge entities from cloud"""
    queryInfo = gen_query_agent_knowledges_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentKnowledges", "queryAgentKnowledges")


# ============================================================================
# Avatar Resource Operations
# ============================================================================

def gen_add_avatar_resources_string(resources):
    """Generate GraphQL mutation string for adding avatar resources
    
    New schema: addAvatars(input: [AvatarInput!]!): [AvatarMutationResult!]!
    AvatarInput has all optional fields: id, owner, name, description, resource_type, etc.
    """
    query_string = """
        mutation MyMutation {
      addAvatars (input:[
    """
    rec_string = ""
    for i, res in enumerate(resources):
        rec_string += "{ "
        parts = []
        if res.get("id"):
            parts.append(f'id: "{res.get("id")}"')
        if res.get("owner"):
            parts.append(f'owner: "{res.get("owner")}"')
        if res.get("name"):
            parts.append(f'name: "{res.get("name")}"')
        if res.get("description"):
            description = res.get("description", "").replace('"', '\\"').replace('\n', '\\n')
            parts.append(f'description: "{description}"')
        if res.get("resource_type"):
            parts.append(f'resource_type: "{res.get("resource_type")}"')
        if res.get("image_path"):
            parts.append(f'image_path: "{res.get("image_path")}"')
        if res.get("video_path"):
            parts.append(f'video_path: "{res.get("video_path")}"')
        if res.get("image_hash"):
            parts.append(f'image_hash: "{res.get("image_hash")}"')
        if res.get("video_hash"):
            parts.append(f'video_hash: "{res.get("video_hash")}"')
        if res.get("cloud_image_url"):
            parts.append(f'cloud_image_url: "{res.get("cloud_image_url")}"')
        if res.get("cloud_video_url"):
            parts.append(f'cloud_video_url: "{res.get("cloud_video_url")}"')
        if res.get("cloud_image_key"):
            parts.append(f'cloud_image_key: "{res.get("cloud_image_key")}"')
        if res.get("cloud_video_key"):
            parts.append(f'cloud_video_key: "{res.get("cloud_video_key")}"')
        if "cloud_synced" in res:
            parts.append(f'cloud_synced: {"true" if res.get("cloud_synced") else "false"}')
        if res.get("avatar_metadata"):
            avatar_metadata = res.get("avatar_metadata", {})
            if isinstance(avatar_metadata, dict):
                avatar_metadata = json.dumps(avatar_metadata, ensure_ascii=False).replace('"', '\\"')
            parts.append(f'avatar_metadata: "{avatar_metadata}"')
        if res.get("usage_count") is not None:
            parts.append(f'usage_count: {res.get("usage_count")}')
        if "is_public" in res:
            parts.append(f'is_public: {"true" if res.get("is_public") else "false"}')
        rec_string += ", ".join(parts)
        rec_string += " }"
        if i != len(resources) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        ) { id success error image_upload_url video_upload_url }
    }
    """
    return query_string


def gen_update_avatar_resources_string(resources):
    """Generate GraphQL mutation string for updating avatar resources
    
    New schema: updateAvatars(input: [AvatarUpdateInput!]!): [AvatarMutationResult!]!
    AvatarUpdateInput has: id (required), and many optional fields
    """
    query_string = """
        mutation MyMutation {
      updateAvatars (input:[
    """
    rec_string = ""
    for i, res in enumerate(resources):
        rec_string += "{ "
        rec_string += f'id: "{res.get("id", "")}"'
        if "owner" in res:
            rec_string += f', owner: "{res.get("owner", "")}"'
        if "resource_type" in res:
            rec_string += f', resource_type: "{res.get("resource_type", "")}"'
        if "name" in res:
            rec_string += f', name: "{res.get("name", "")}"'
        if "description" in res:
            description = res.get("description", "").replace('"', '\\"').replace('\n', '\\n')
            rec_string += f', description: "{description}"'
        if "image_path" in res:
            rec_string += f', image_path: "{res.get("image_path", "")}"'
        if "video_path" in res:
            rec_string += f', video_path: "{res.get("video_path", "")}"'
        if "cloud_image_url" in res:
            rec_string += f', cloud_image_url: "{res.get("cloud_image_url", "")}"'
        if "cloud_video_url" in res:
            rec_string += f', cloud_video_url: "{res.get("cloud_video_url", "")}"'
        if "cloud_synced" in res:
            rec_string += f', cloud_synced: {"true" if res.get("cloud_synced") else "false"}'
        if "avatar_metadata" in res:
            avatar_metadata = res.get("avatar_metadata", {})
            if isinstance(avatar_metadata, dict):
                avatar_metadata = json.dumps(avatar_metadata, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', avatar_metadata: "{avatar_metadata}"'
        if "usage_count" in res:
            rec_string += f', usage_count: {res.get("usage_count", 0)}'
        if "is_public" in res:
            rec_string += f', is_public: {"true" if res.get("is_public") else "false"}'
        rec_string += " }"
        if i != len(resources) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        ) { id success error image_upload_url video_upload_url }
    }
    """
    return query_string


def gen_remove_avatar_resources_string(removeOrders):
    """Generate GraphQL mutation string for removing avatar resources
    
    New schema: removeAvatars(input: [ID!]!): [AvatarMutationResult!]!
    Input is just an array of IDs
    """
    ids = []
    for item in removeOrders:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            ids.append(item.get("id", item.get("oid", "")))
    
    ids_str = ', '.join([f'"{id}"' for id in ids])
    
    query_string = f'''
        mutation MyMutation {{
      removeAvatars (input: [{ids_str}]) {{ id success error }}
    }}
    '''
    return query_string


def gen_query_avatar_resources_string(q_settings):
    """Generate GraphQL query string for querying avatar resources
    
    New schema: queryAvatars(input: AvatarQueryInput): [AvatarResource!]!
    AvatarQueryInput has: owner, resource_type (all optional)
    """
    # Build input object based on q_settings
    input_parts = []
    if q_settings.get("owner"):
        input_parts.append(f'owner: "{q_settings["owner"]}"')
    if q_settings.get("resource_type"):
        input_parts.append(f'resource_type: "{q_settings["resource_type"]}"')
    
    input_str = ", ".join(input_parts) if input_parts else ""
    
    query_string = f'''query MyAvatarQuery {{
  queryAvatars(input: {{ {input_str} }}) {{
    id
    owner
    name
    description
    resource_type
    image_path
    image_hash
    video_path
    video_hash
    cloud_image_key
    cloud_image_url
    cloud_video_key
    cloud_video_url
    cloud_synced
    avatar_metadata
    is_public
    usage_count
  }}
}}'''
    return query_string


@cloud_api(DataType.AVATAR_RESOURCE, Operation.ADD)
def send_add_avatar_resources_to_cloud(session, resources, token, endpoint, timeout=180, upload_files=True):
    """Add Avatar Resource entities to cloud
    
    Args:
        session: HTTP session
        resources: List of avatar resource dicts with image_path and/or video_path
        token: Auth token
        endpoint: API endpoint
        timeout: Request timeout
        upload_files: If True, automatically upload files using presigned URLs from response
    
    Returns:
        List of mutation results, with upload_results added if upload_files=True
    """
    logger.info(f"[Avatar ADD] Sending addAvatars mutation for {len(resources)} resource(s)")
    mutationInfo = gen_add_avatar_resources_string(resources)
    logger.debug(f"[Avatar ADD] Mutation: {mutationInfo[:500]}...")
    
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    logger.info(f"[Avatar ADD] Received response from server")
    logger.debug(f"[Avatar ADD] Raw response: {json.dumps(jresp, default=str)[:1000]}")
    
    results = safe_parse_response(jresp, "addAvatars", "addAvatars")
    logger.info(f"[Avatar ADD] Parsed {len(results) if results else 0} result(s)")
    
    # Log presigned URLs received
    if results:
        for i, result in enumerate(results):
            avatar_id = result.get("id", "unknown")
            success = result.get("success", False)
            has_image_url = bool(result.get("image_upload_url"))
            has_video_url = bool(result.get("video_upload_url"))
            logger.info(f"[Avatar ADD] Result[{i}]: id={avatar_id}, success={success}, has_image_url={has_image_url}, has_video_url={has_video_url}")
            if has_image_url:
                logger.debug(f"[Avatar ADD] image_upload_url: {result.get('image_upload_url')[:100]}...")
            if has_video_url:
                logger.debug(f"[Avatar ADD] video_upload_url: {result.get('video_upload_url')[:100]}...")
    
    # If upload_files is True and we got presigned URLs, upload the files
    if upload_files and results:
        logger.info(f"[Avatar ADD] Starting file uploads (upload_files={upload_files})")
        for i, result in enumerate(results):
            if result.get("success") and i < len(resources):
                resource = resources[i]
                avatar_id = result.get("id", "unknown")
                
                # Upload image if we have image_path and image_upload_url
                if result.get("image_upload_url") and resource.get("image_path"):
                    image_path = resource["image_path"]
                    logger.info(f"[Avatar ADD] 📤 Uploading image for {avatar_id}: {image_path}")
                    upload_result = upload_file_to_presigned_url(image_path, result["image_upload_url"])
                    result["image_upload_result"] = upload_result
                    logger.info(f"[Avatar ADD] Image upload result: {upload_result}")
                else:
                    if not result.get("image_upload_url"):
                        logger.debug(f"[Avatar ADD] No image_upload_url in response for {avatar_id}")
                    if not resource.get("image_path"):
                        logger.debug(f"[Avatar ADD] No image_path in resource for {avatar_id}")
                
                # Upload video if we have video_path and video_upload_url
                if result.get("video_upload_url") and resource.get("video_path"):
                    video_path = resource["video_path"]
                    logger.info(f"[Avatar ADD] 📤 Uploading video for {avatar_id}: {video_path}")
                    upload_result = upload_file_to_presigned_url(video_path, result["video_upload_url"])
                    result["video_upload_result"] = upload_result
                    logger.info(f"[Avatar ADD] Video upload result: {upload_result}")
                else:
                    if not result.get("video_upload_url"):
                        logger.debug(f"[Avatar ADD] No video_upload_url in response for {avatar_id}")
                    if not resource.get("video_path"):
                        logger.debug(f"[Avatar ADD] No video_path in resource for {avatar_id}")
    else:
        logger.info(f"[Avatar ADD] Skipping file uploads (upload_files={upload_files}, results={bool(results)})")
    
    logger.info(f"[Avatar ADD] Completed")
    return results


@cloud_api(DataType.AVATAR_RESOURCE, Operation.UPDATE)
def send_update_avatar_resources_to_cloud(session, resources, token, endpoint, timeout=180, upload_files=True):
    """Update Avatar Resource entities in cloud
    
    Args:
        session: HTTP session
        resources: List of avatar resource dicts with id (required) and optional image_path/video_path
        token: Auth token
        endpoint: API endpoint
        timeout: Request timeout
        upload_files: If True, automatically upload files using presigned URLs from response
    
    Returns:
        List of mutation results, with upload_results added if upload_files=True
    """
    logger.info(f"[Avatar UPDATE] Sending updateAvatars mutation for {len(resources)} resource(s)")
    mutationInfo = gen_update_avatar_resources_string(resources)
    logger.debug(f"[Avatar UPDATE] Mutation: {mutationInfo[:500]}...")
    
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    logger.info(f"[Avatar UPDATE] Received response from server")
    logger.debug(f"[Avatar UPDATE] Raw response: {json.dumps(jresp, default=str)[:1000]}")
    
    results = safe_parse_response(jresp, "updateAvatars", "updateAvatars")
    logger.info(f"[Avatar UPDATE] Parsed {len(results) if results else 0} result(s)")
    
    # Log presigned URLs received
    if results:
        for i, result in enumerate(results):
            avatar_id = result.get("id", "unknown")
            success = result.get("success", False)
            has_image_url = bool(result.get("image_upload_url"))
            has_video_url = bool(result.get("video_upload_url"))
            logger.info(f"[Avatar UPDATE] Result[{i}]: id={avatar_id}, success={success}, has_image_url={has_image_url}, has_video_url={has_video_url}")
    
    # If upload_files is True and we got presigned URLs, upload the files
    if upload_files and results:
        logger.info(f"[Avatar UPDATE] Starting file uploads (upload_files={upload_files})")
        for i, result in enumerate(results):
            if result.get("success") and i < len(resources):
                resource = resources[i]
                avatar_id = result.get("id", "unknown")
                
                # Upload image if we have image_path and image_upload_url
                if result.get("image_upload_url") and resource.get("image_path"):
                    image_path = resource["image_path"]
                    logger.info(f"[Avatar UPDATE] 📤 Uploading image for {avatar_id}: {image_path}")
                    upload_result = upload_file_to_presigned_url(image_path, result["image_upload_url"])
                    result["image_upload_result"] = upload_result
                    logger.info(f"[Avatar UPDATE] Image upload result: {upload_result}")
                
                # Upload video if we have video_path and video_upload_url
                if result.get("video_upload_url") and resource.get("video_path"):
                    video_path = resource["video_path"]
                    logger.info(f"[Avatar UPDATE] 📤 Uploading video for {avatar_id}: {video_path}")
                    upload_result = upload_file_to_presigned_url(video_path, result["video_upload_url"])
                    result["video_upload_result"] = upload_result
                    logger.info(f"[Avatar UPDATE] Video upload result: {upload_result}")
    else:
        logger.info(f"[Avatar UPDATE] Skipping file uploads (upload_files={upload_files}, results={bool(results)})")
    
    logger.info(f"[Avatar UPDATE] Completed")
    return results


@cloud_api(DataType.AVATAR_RESOURCE, Operation.DELETE)
def send_remove_avatar_resources_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Avatar Resource entities from cloud"""
    mutationInfo = gen_remove_avatar_resources_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeAvatars", "removeAvatars")


@cloud_api(DataType.AVATAR_RESOURCE, Operation.QUERY)
def send_query_avatar_resources_to_cloud(session, token, q_settings, endpoint):
    """Query Avatar Resource entities from cloud"""
    queryInfo = gen_query_avatar_resources_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAvatars", "queryAvatars")


# ============================================================================
# Organization Operations
# ============================================================================

def gen_query_organizations_string(q_settings):
    """Generate GraphQL query string for querying organizations
    
    New schema: queryOrgs(input: OrgQueryInput): [Org!]!
    OrgQueryInput has: name, org_type, status (all optional)
    """
    # Build input object based on q_settings
    input_parts = []
    if q_settings.get("name"):
        input_parts.append(f'name: "{q_settings["name"]}"')
    if q_settings.get("org_type"):
        input_parts.append(f'org_type: "{q_settings["org_type"]}"')
    if q_settings.get("status"):
        input_parts.append(f'status: "{q_settings["status"]}"')
    
    input_str = ", ".join(input_parts) if input_parts else ""
    
    query_string = f'''query MyOrgQuery {{
  queryOrgs(input: {{ {input_str} }}) {{
    id
    name
    description
    org_type
    parent_id
    level
    sort_order
    status
    settings
  }}
}}'''
    return query_string


def gen_get_organizations_string(ids):
    """Generate GraphQL query string for getting organizations by IDs"""
    ids_str = ",".join(ids) if isinstance(ids, list) else str(ids)
    query_string = f'''
        query MyQuery {{
            getOrganizations(ids: "{ids_str}")
        }}
    '''
    return query_string


@cloud_api(DataType.ORGANIZATION, Operation.QUERY)
def send_query_organizations_to_cloud(session, token, q_settings, endpoint):
    """Query Organization entities from cloud"""
    queryInfo = gen_query_organizations_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryOrgs", "queryOrgs")


def gen_add_organizations_string(organizations):
    """Generate GraphQL mutation string for adding organizations
    
    New schema: addOrgs(input: [OrgInput!]!): [OrgMutationResult!]!
    OrgInput has: id, name!, description, org_type, parent_id, settings, sort_order, status
    Note: No 'owner' field in OrgInput
    """
    query_string = """
        mutation MyMutation {
      addOrgs (input:[
    """
    rec_string = ""
    for i, org in enumerate(organizations):
        rec_string += "{ "
        if org.get("id"):
            rec_string += f'id: "{org.get("id")}", '
        rec_string += f'name: "{org.get("name", "")}"'
        if org.get("description"):
            description = org.get("description", "").replace('"', '\\"').replace('\n', '\\n')
            rec_string += f', description: "{description}"'
        if org.get("org_type"):
            rec_string += f', org_type: "{org.get("org_type")}"'
        if org.get("status"):
            rec_string += f', status: "{org.get("status")}"'
        if org.get("parent_id"):
            rec_string += f', parent_id: "{org.get("parent_id")}"'
        if org.get("sort_order") is not None:
            rec_string += f', sort_order: {org.get("sort_order")}'
        if org.get("settings"):
            settings = org.get("settings", {})
            if isinstance(settings, dict):
                settings = json.dumps(settings, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', settings: "{settings}"'
        rec_string += " }"
        if i != len(organizations) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        ) { id success error }
    }
    """
    return query_string


def gen_update_organizations_string(organizations):
    """Generate GraphQL mutation string for updating organizations
    
    New schema: updateOrgs(input: [OrgUpdateInput!]!): [OrgMutationResult!]!
    OrgUpdateInput has: id!, name, description, org_type, parent_id, level, settings, sort_order, status
    """
    query_string = """
        mutation MyMutation {
      updateOrgs (input:[
    """
    rec_string = ""
    for i, org in enumerate(organizations):
        rec_string += "{ "
        rec_string += f'id: "{org.get("id", "")}"'
        if "name" in org:
            rec_string += f', name: "{org.get("name", "")}"'
        if "description" in org:
            description = org.get("description", "").replace('"', '\\"').replace('\n', '\\n')
            rec_string += f', description: "{description}"'
        if "org_type" in org:
            rec_string += f', org_type: "{org.get("org_type", "")}"'
        if "status" in org:
            rec_string += f', status: "{org.get("status", "")}"'
        if "parent_id" in org:
            rec_string += f', parent_id: "{org.get("parent_id", "")}"'
        if "level" in org:
            rec_string += f', level: {org.get("level")}'
        if "sort_order" in org:
            rec_string += f', sort_order: {org.get("sort_order")}'
        if "settings" in org:
            settings = org.get("settings", {})
            if isinstance(settings, dict):
                settings = json.dumps(settings, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', settings: "{settings}"'
        rec_string += " }"
        if i != len(organizations) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        ) { id success error }
    }
    """
    return query_string


def gen_remove_organizations_string(removeOrders):
    """Generate GraphQL mutation string for removing organizations
    
    New schema: removeOrgs(input: [ID!]!): [OrgMutationResult!]!
    Input is just an array of IDs
    """
    # Extract IDs from removeOrders (can be list of strings or list of dicts)
    ids = []
    for item in removeOrders:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            ids.append(item.get("id", item.get("oid", "")))
    
    ids_str = ', '.join([f'"{id}"' for id in ids])
    
    query_string = f'''
        mutation MyMutation {{
      removeOrgs (input: [{ids_str}]) {{ id success error }}
    }}
    '''
    return query_string


@cloud_api(DataType.ORGANIZATION, Operation.ADD)
def send_add_organizations_to_cloud(session, organizations, token, endpoint, timeout=180):
    """Add Organization entities to cloud"""
    mutationInfo = gen_add_organizations_string(organizations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addOrgs", "addOrgs")


@cloud_api(DataType.ORGANIZATION, Operation.UPDATE)
def send_update_organizations_to_cloud(session, organizations, token, endpoint, timeout=180):
    """Update Organization entities in cloud"""
    mutationInfo = gen_update_organizations_string(organizations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updateOrgs", "updateOrgs")


@cloud_api(DataType.ORGANIZATION, Operation.DELETE)
def send_remove_organizations_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Organization entities from cloud"""
    mutationInfo = gen_remove_organizations_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeOrgs", "removeOrgs")


# ============================================================================
# Skill Entity Query (missing query operation)
# ============================================================================

def gen_query_skills_entity_string(q_settings):
    """Generate GraphQL query string for querying skill entities
    
    New schema: queryAgentSkills(input: SkillQueryInput): [AgentSkill!]!
    SkillQueryInput has: id, name, description (all optional)
    """
    # Build input object based on q_settings
    input_parts = []
    if q_settings.get("id"):
        input_parts.append(f'id: "{q_settings["id"]}"')
    if q_settings.get("name"):
        input_parts.append(f'name: "{q_settings["name"]}"')
    if q_settings.get("description"):
        input_parts.append(f'description: "{q_settings["description"]}"')
    
    input_str = ", ".join(input_parts) if input_parts else ""
    
    query_string = f'''query MySkillQuery {{
  queryAgentSkills(input: {{ {input_str} }}) {{
    id
    owner
    name
    description
    version
    level
    config
    diagram
    examples
    inputModes
    outputModes
    apps
    limitations
    path
    source
    tags
    price
    price_model
    public
    rentable
  }}
}}'''
    return query_string


@cloud_api(DataType.SKILL, Operation.QUERY)
def send_query_skills_entity_to_cloud(session, token, q_settings, endpoint):
    """Query Skill entities from cloud"""
    queryInfo = gen_query_skills_entity_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentSkills", "queryAgentSkills")


# ============================================================================
# Task Entity Query (missing query operation)
# ============================================================================

def gen_query_tasks_entity_string(q_settings):
    """Generate GraphQL query string for querying task entities
    
    New schema: queryAgentTasks(input: TaskQueryInput): [Task!]!
    TaskQueryInput has: id, name, description (all optional)
    """
    # Build input object based on q_settings
    input_parts = []
    if q_settings.get("id"):
        input_parts.append(f'id: "{q_settings["id"]}"')
    if q_settings.get("name"):
        input_parts.append(f'name: "{q_settings["name"]}"')
    if q_settings.get("description"):
        input_parts.append(f'description: "{q_settings["description"]}"')
    
    input_str = ", ".join(input_parts) if input_parts else ""
    
    query_string = f'''query MyTaskQuery {{
  queryAgentTasks(input: {{ {input_str} }}) {{
    id
    owner
    name
    description
    task_type
    status
    priority
    trigger_type
    schedule
    objectives
    metadata
    progress
    result
    error_message
    org_id
  }}
}}'''
    return query_string


@cloud_api(DataType.TASK, Operation.QUERY)
def send_query_tasks_entity_to_cloud(session, token, q_settings, endpoint):
    """Query Task entities from cloud"""
    queryInfo = gen_query_tasks_entity_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentTasks", "queryAgentTasks")


# ============================================================================
# Tool Entity Query (missing query operation)
# ============================================================================

def gen_query_tools_entity_string(q_settings):
    """Generate GraphQL query string for querying tool entities
    
    New schema: queryAgentTools(input: ToolQueryInput): [AgentTool!]!
    ToolQueryInput has: id, name, description (all optional)
    """
    # Build input object based on q_settings
    input_parts = []
    if q_settings.get("id"):
        input_parts.append(f'id: "{q_settings["id"]}"')
    if q_settings.get("name"):
        input_parts.append(f'name: "{q_settings["name"]}"')
    if q_settings.get("description"):
        input_parts.append(f'description: "{q_settings["description"]}"')
    
    input_str = ", ".join(input_parts) if input_parts else ""
    
    query_string = f'''query MyToolQuery {{
  queryAgentTools(input: {{ {input_str} }}) {{
    id
    owner
    name
    description
    tool_type
    status
    version
    level
    config
    capabilities
    dependencies
    limitations
    settings
    path
    price
    price_model
    public
    rentable
  }}
}}'''
    return query_string


@cloud_api(DataType.TOOL, Operation.QUERY)
def send_query_tools_entity_to_cloud(session, token, q_settings, endpoint):
    """Query Tool entities from cloud"""
    queryInfo = gen_query_tools_entity_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentTools", "queryAgentTools")


# ============================================================================
# Second-Level Relationship Operations: Skill-Tool
# ============================================================================

def gen_add_skill_tool_relations_string(relations):
    """Generate GraphQL mutation string for adding skill-tool relations"""
    from agent.cloud_api.graphql_builder import build_mutation
    return build_mutation(DataType.SKILL_TOOL, Operation.ADD, relations)


def gen_query_skill_tool_relations_string(q_settings):
    """Generate GraphQL query string for querying skill-tool relations"""
    qb = json.dumps(q_settings, ensure_ascii=False).replace('"', '\\"')
    query_string = f'''
        query MyQuery {{
            queryAgentSkillToolRels(input: "{qb}")
        }}
    '''
    return query_string


@cloud_api(DataType.SKILL_TOOL, Operation.ADD)
def send_add_skill_tool_relations_to_cloud(session, relations, token, endpoint, timeout=180):
    """Add Skill-Tool relations to cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_TOOL, Operation.ADD, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addAgentSkillToolRels", "addAgentSkillToolRels")


@cloud_api(DataType.SKILL_TOOL, Operation.UPDATE)
def send_update_skill_tool_relations_to_cloud(session, relations, token, endpoint, timeout=180):
    """Update Skill-Tool relations in cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_TOOL, Operation.UPDATE, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updateAgentSkillToolRels", "updateAgentSkillToolRels")


@cloud_api(DataType.SKILL_TOOL, Operation.DELETE)
def send_remove_skill_tool_relations_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Skill-Tool relations from cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_TOOL, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeAgentSkillToolRels", "removeAgentSkillToolRels")


@cloud_api(DataType.SKILL_TOOL, Operation.QUERY)
def send_query_skill_tool_relations_to_cloud(session, token, q_settings, endpoint):
    """Query Skill-Tool relations from cloud"""
    queryInfo = gen_query_skill_tool_relations_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentSkillToolRels", "queryAgentSkillToolRels")


# ============================================================================
# Second-Level Relationship Operations: Skill-Knowledge
# ============================================================================

def gen_query_skill_knowledge_relations_string(q_settings):
    """Generate GraphQL query string for querying skill-knowledge relations"""
    qb = json.dumps(q_settings, ensure_ascii=False).replace('"', '\\"')
    query_string = f'''
        query MyQuery {{
            queryAgentSkillKnowledgeRels(input: "{qb}")
        }}
    '''
    return query_string


@cloud_api(DataType.SKILL_KNOWLEDGE, Operation.ADD)
def send_add_skill_knowledge_relations_to_cloud(session, relations, token, endpoint, timeout=180):
    """Add Skill-Knowledge relations to cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_KNOWLEDGE, Operation.ADD, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addAgentSkillKnowledgeRels", "addAgentSkillKnowledgeRels")


@cloud_api(DataType.SKILL_KNOWLEDGE, Operation.UPDATE)
def send_update_skill_knowledge_relations_to_cloud(session, relations, token, endpoint, timeout=180):
    """Update Skill-Knowledge relations in cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_KNOWLEDGE, Operation.UPDATE, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updateAgentSkillKnowledgeRels", "updateAgentSkillKnowledgeRels")


@cloud_api(DataType.SKILL_KNOWLEDGE, Operation.DELETE)
def send_remove_skill_knowledge_relations_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Skill-Knowledge relations from cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_KNOWLEDGE, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeAgentSkillKnowledgeRels", "removeAgentSkillKnowledgeRels")


@cloud_api(DataType.SKILL_KNOWLEDGE, Operation.QUERY)
def send_query_skill_knowledge_relations_to_cloud(session, token, q_settings, endpoint):
    """Query Skill-Knowledge relations from cloud"""
    queryInfo = gen_query_skill_knowledge_relations_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentSkillKnowledgeRels", "queryAgentSkillKnowledgeRels")


# ============================================================================
# Second-Level Relationship Operations: Task-Skill
# ============================================================================

def gen_query_task_skill_relations_string(q_settings):
    """Generate GraphQL query string for querying task-skill relations"""
    qb = json.dumps(q_settings, ensure_ascii=False).replace('"', '\\"')
    query_string = f'''
        query MyQuery {{
            queryAgentTaskSkillRels(input: "{qb}")
        }}
    '''
    return query_string


@cloud_api(DataType.TASK_SKILL, Operation.ADD)
def send_add_task_skill_relations_to_cloud(session, relations, token, endpoint, timeout=180):
    """Add Task-Skill relations to cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.TASK_SKILL, Operation.ADD, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addAgentTaskSkillRels", "addAgentTaskSkillRels")


@cloud_api(DataType.TASK_SKILL, Operation.UPDATE)
def send_update_task_skill_relations_to_cloud(session, relations, token, endpoint, timeout=180):
    """Update Task-Skill relations in cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.TASK_SKILL, Operation.UPDATE, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updateAgentTaskSkillRels", "updateAgentTaskSkillRels")


@cloud_api(DataType.TASK_SKILL, Operation.DELETE)
def send_remove_task_skill_relations_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Task-Skill relations from cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.TASK_SKILL, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeAgentTaskSkillRels", "removeAgentTaskSkillRels")


@cloud_api(DataType.TASK_SKILL, Operation.QUERY)
def send_query_task_skill_relations_to_cloud(session, token, q_settings, endpoint):
    """Query Task-Skill relations from cloud"""
    queryInfo = gen_query_task_skill_relations_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentTaskSkillRels", "queryAgentTaskSkillRels")


# ============================================================================
# Vehicle Operations (missing remove and query)
# ============================================================================

def gen_add_vehicles_string(vehicles):
    """Generate GraphQL mutation string for adding vehicles
    
    New schema: addVehicles(input: [VehicleInput!]!): [VehicleMutationResult!]!
    VehicleInput has: id, name (required), and many optional fields
    """
    query_string = """
        mutation MyMutation {
      addVehicles (input:[
    """
    rec_string = ""
    for i, v in enumerate(vehicles):
        rec_string += "{ "
        if v.get("id"):
            rec_string += f'id: "{v.get("id")}", '
        rec_string += f'name: "{v.get("name", "")}"'
        if v.get("description"):
            description = v.get("description", "").replace('"', '\\"').replace('\n', '\\n')
            rec_string += f', description: "{description}"'
        if v.get("vehicle_type"):
            rec_string += f', vehicle_type: "{v.get("vehicle_type")}"'
        if v.get("status"):
            rec_string += f', status: "{v.get("status")}"'
        if v.get("hostname"):
            rec_string += f', hostname: "{v.get("hostname")}"'
        if v.get("ip_address"):
            rec_string += f', ip_address: "{v.get("ip_address")}"'
        if v.get("port") is not None:
            rec_string += f', port: {v.get("port")}'
        if v.get("url"):
            rec_string += f', url: "{v.get("url")}"'
        if v.get("platform"):
            rec_string += f', platform: "{v.get("platform")}"'
        if v.get("architecture"):
            rec_string += f', architecture: "{v.get("architecture")}"'
        if v.get("environment"):
            rec_string += f', environment: "{v.get("environment")}"'
        if v.get("capabilities"):
            caps = v.get("capabilities", {})
            if isinstance(caps, dict):
                caps = json.dumps(caps, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', capabilities: "{caps}"'
        if v.get("settings"):
            settings = v.get("settings", {})
            if isinstance(settings, dict):
                settings = json.dumps(settings, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', settings: "{settings}"'
        rec_string += " }"
        if i != len(vehicles) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        ) { id success error }
    }
    """
    return query_string


def gen_update_vehicles_new_string(vehicles):
    """Generate GraphQL mutation string for updating vehicles
    
    New schema: updateVehicles(input: [VehicleUpdateInput!]!): [VehicleMutationResult!]!
    VehicleUpdateInput has: id (required), and many optional fields
    """
    query_string = """
        mutation MyMutation {
      updateVehicles (input:[
    """
    rec_string = ""
    for i, v in enumerate(vehicles):
        rec_string += "{ "
        rec_string += f'id: "{v.get("id", "")}"'
        if "name" in v:
            rec_string += f', name: "{v.get("name", "")}"'
        if "description" in v:
            description = v.get("description", "").replace('"', '\\"').replace('\n', '\\n')
            rec_string += f', description: "{description}"'
        if "vehicle_type" in v:
            rec_string += f', vehicle_type: "{v.get("vehicle_type", "")}"'
        if "status" in v:
            rec_string += f', status: "{v.get("status", "")}"'
        if "hostname" in v:
            rec_string += f', hostname: "{v.get("hostname", "")}"'
        if "ip_address" in v:
            rec_string += f', ip_address: "{v.get("ip_address", "")}"'
        if "port" in v:
            rec_string += f', port: {v.get("port")}'
        if "url" in v:
            rec_string += f', url: "{v.get("url", "")}"'
        if "platform" in v:
            rec_string += f', platform: "{v.get("platform", "")}"'
        if "architecture" in v:
            rec_string += f', architecture: "{v.get("architecture", "")}"'
        if "environment" in v:
            rec_string += f', environment: "{v.get("environment", "")}"'
        if "capabilities" in v:
            caps = v.get("capabilities", {})
            if isinstance(caps, dict):
                caps = json.dumps(caps, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', capabilities: "{caps}"'
        if "settings" in v:
            settings = v.get("settings", {})
            if isinstance(settings, dict):
                settings = json.dumps(settings, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', settings: "{settings}"'
        rec_string += " }"
        if i != len(vehicles) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        ) { id success error }
    }
    """
    return query_string


def gen_remove_vehicles_string(removeOrders):
    """Generate GraphQL mutation string for removing vehicles
    
    New schema: removeVehicles(input: [ID!]!): [VehicleMutationResult!]!
    Input is just an array of IDs
    """
    # Extract IDs from removeOrders (can be list of strings or list of dicts)
    ids = []
    for item in removeOrders:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            ids.append(item.get("id", item.get("vid", item.get("oid", ""))))
    
    ids_str = ', '.join([f'"{id}"' for id in ids])
    
    query_string = f'''
        mutation MyMutation {{
      removeVehicles (input: [{ids_str}]) {{ id success error }}
    }}
    '''
    return query_string


def gen_query_vehicles_string(q_settings):
    """Generate GraphQL query string for querying vehicles
    
    New schema: queryVehicles(input: VehicleQueryInput): [Vehicle!]!
    VehicleQueryInput has: id, name, description (all optional)
    """
    # Build input object based on q_settings
    input_parts = []
    if q_settings.get("id"):
        input_parts.append(f'id: "{q_settings["id"]}"')
    if q_settings.get("name"):
        input_parts.append(f'name: "{q_settings["name"]}"')
    if q_settings.get("description"):
        input_parts.append(f'description: "{q_settings["description"]}"')
    
    input_str = ", ".join(input_parts) if input_parts else ""
    
    query_string = f'''query MyVehicleQuery {{
  queryVehicles(input: {{ {input_str} }}) {{
    id
    owner
    name
    description
    vehicle_type
    status
    hostname
    ip_address
    port
    url
    platform
    architecture
    environment
    cpu_cores
    memory_gb
    storage_gb
    gpu_info
    capabilities
    limitations
    settings
    extra_metadata
    max_concurrent_tasks
    health_score
    uptime_seconds
    timezone
    location
    security_level
    ssl_enabled
    access_token
  }}
}}'''
    return query_string


@cloud_api(DataType.VEHICLE, Operation.DELETE)
def send_remove_vehicles_request_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Vehicle entities from cloud"""
    mutationInfo = gen_remove_vehicles_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeVehicles", "removeVehicles")


@cloud_api(DataType.VEHICLE, Operation.QUERY)
def send_query_vehicles_request_to_cloud(session, token, q_settings, endpoint):
    """Query Vehicle entities from cloud"""
    queryInfo = gen_query_vehicles_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryVehicles", "queryVehicles")


# ============================================================================
# Prompt Operations
# ============================================================================

def gen_add_prompts_string(prompts):
    """Generate GraphQL mutation string for adding prompts
    
    New schema: addPrompts(input: [PromptInput!]!): [PromptMutationResult!]!
    PromptInput has: id, owner, version, prompt (AWSJSON, required)
    """
    query_string = """
        mutation MyMutation {
      addPrompts (input:[
    """
    rec_string = ""
    for i, prompt in enumerate(prompts):
        rec_string += "{ "
        if prompt.get("id"):
            rec_string += f'id: "{prompt.get("id")}", '
        if prompt.get("owner"):
            rec_string += f'owner: "{prompt.get("owner")}", '
        if prompt.get("version"):
            rec_string += f'version: "{prompt.get("version")}", '
        # prompt field is required AWSJSON
        prompt_data = prompt.get("prompt", {})
        if isinstance(prompt_data, dict):
            prompt_json = json.dumps(prompt_data, ensure_ascii=False).replace('"', '\\"')
        else:
            prompt_json = str(prompt_data).replace('"', '\\"')
        rec_string += f'prompt: "{prompt_json}"'
        rec_string += " }"
        if i != len(prompts) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        ) { id success error }
    }
    """
    return query_string


def gen_update_prompts_string(prompts):
    """Generate GraphQL mutation string for updating prompts
    
    New schema: updatePrompts(input: [PromptUpdateInput!]!): [PromptMutationResult!]!
    PromptUpdateInput has: id (required), version, prompt (AWSJSON)
    """
    query_string = """
        mutation MyMutation {
      updatePrompts (input:[
    """
    rec_string = ""
    for i, prompt in enumerate(prompts):
        rec_string += "{ "
        rec_string += f'id: "{prompt.get("id", "")}"'
        if "version" in prompt:
            rec_string += f', version: "{prompt.get("version", "")}"'
        if "prompt" in prompt:
            prompt_data = prompt.get("prompt", {})
            if isinstance(prompt_data, dict):
                prompt_json = json.dumps(prompt_data, ensure_ascii=False).replace('"', '\\"')
            else:
                prompt_json = str(prompt_data).replace('"', '\\"')
            rec_string += f', prompt: "{prompt_json}"'
        rec_string += " }"
        if i != len(prompts) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        ) { id success error }
    }
    """
    return query_string


def gen_remove_prompts_string(removeOrders):
    """Generate GraphQL mutation string for removing prompts
    
    New schema: removePrompts(input: [ID!]!): [PromptMutationResult!]!
    Input is just an array of IDs
    """
    # Extract IDs from removeOrders (can be list of strings or list of dicts)
    ids = []
    for item in removeOrders:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            ids.append(item.get("id", item.get("oid", "")))
    
    ids_str = ', '.join([f'"{id}"' for id in ids])
    
    query_string = f'''
        mutation MyMutation {{
      removePrompts (input: [{ids_str}]) {{ id success error }}
    }}
    '''
    return query_string


def gen_query_prompts_string(q_settings):
    """Generate GraphQL query string for querying prompts
    
    New schema: queryPrompts(input: PromptQueryInput): [Prompt!]!
    PromptQueryInput has: id, owner, version, search (all optional)
    """
    # Build input object based on q_settings
    input_parts = []
    if q_settings.get("id"):
        input_parts.append(f'id: "{q_settings["id"]}"')
    if q_settings.get("owner"):
        input_parts.append(f'owner: "{q_settings["owner"]}"')
    if q_settings.get("version"):
        input_parts.append(f'version: "{q_settings["version"]}"')
    if q_settings.get("search"):
        input_parts.append(f'search: "{q_settings["search"]}"')
    
    input_str = ", ".join(input_parts) if input_parts else ""
    
    query_string = f'''query MyPromptQuery {{
  queryPrompts(input: {{ {input_str} }}) {{
    id
    owner
    version
    prompt
  }}
}}'''
    return query_string


@cloud_api(DataType.PROMPT, Operation.ADD)
def send_add_prompts_request_to_cloud(session, prompts, token, endpoint, timeout=180):
    """Add Prompt entities to cloud"""
    mutationInfo = gen_add_prompts_string(prompts)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addPrompts", "addPrompts")


@cloud_api(DataType.PROMPT, Operation.UPDATE)
def send_update_prompts_request_to_cloud(session, prompts, token, endpoint, timeout=180):
    """Update Prompt entities in cloud"""
    mutationInfo = gen_update_prompts_string(prompts)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updatePrompts", "updatePrompts")


@cloud_api(DataType.PROMPT, Operation.DELETE)
def send_remove_prompts_request_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Prompt entities from cloud"""
    mutationInfo = gen_remove_prompts_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removePrompts", "removePrompts")


@cloud_api(DataType.PROMPT, Operation.QUERY)
def send_query_prompts_request_to_cloud(session, token, q_settings, endpoint):
    """Query Prompt entities from cloud"""
    queryInfo = gen_query_prompts_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryPrompts", "queryPrompts")


# ==========================================================
# C2L (Cloud to Local) WebSocket Test
# ==========================================================

def gen_run_test_mutation_string(tests):
    """
    Generate GraphQL mutation string for runTest.
    
    Schema:
    input TestInput {
        id: String!
        name: String!
        description: String
        input: AWSJSON
    }
    runTest(input: [TestInput]!): AWSJSON!
    """
    import uuid
    import time
    
    query_string = """
        mutation RunTestMutation {
      runTest (input:[
    """
    rec_string = ""
    for i, test in enumerate(tests):
        test_id = test.get('id') or str(uuid.uuid4())
        name = test.get('name', 'C2L_WS_TEST')
        description = test.get('description') or ''
        input_json = test.get('input') or '{}'
        
        # Escape strings for GraphQL
        name = name.replace('"', '\\"')
        description = description.replace('"', '\\"')
        if isinstance(input_json, dict):
            input_json = json.dumps(input_json).replace('"', '\\"')
        else:
            input_json = str(input_json).replace('"', '\\"')
        
        rec_string += '{'
        rec_string += f'id: "{test_id}", '
        rec_string += f'name: "{name}", '
        rec_string += f'description: "{description}", '
        rec_string += f'input: "{input_json}"'
        rec_string += '}'
        if i < len(tests) - 1:
            rec_string += ','
    
    query_string += rec_string
    query_string += """
      ])
    }
    """
    return query_string


def send_run_test_to_cloud(session, token, tests, endpoint=None, timeout=60):
    """
    Send runTest mutation to cloud AppSync.
    
    This is used for C2L (Cloud to Local) WebSocket testing.
    The cloud will receive this test request and can push messages back
    to the local client via WebSocket subscriptions.
    
    Args:
        session: requests.Session object
        token: Authentication token
        tests: List of test configurations, each with id, name, description, input
        endpoint: API endpoint URL (optional)
        timeout: Request timeout in seconds
    
    Returns:
        Response from cloud
    """
    mutation_string = gen_run_test_mutation_string(tests)
    logger.info(f"[C2L-WS-Test] Sending runTest mutation to cloud: {len(tests)} tests")
    logger.debug(f"[C2L-WS-Test] Mutation: {mutation_string[:200]}...")
    
    jresp = appsync_http_request(mutation_string, session, token, endpoint, timeout=timeout)
    
    if "errors" in jresp:
        logger.error(f"[C2L-WS-Test] Error from cloud: {jresp['errors']}")
        return {"success": False, "errors": jresp["errors"]}
    
    try:
        result = jresp.get("data", {}).get("runTest")
        if result and isinstance(result, str):
            result = json.loads(result)
        logger.info(f"[C2L-WS-Test] Success: {result}")
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"[C2L-WS-Test] Failed to parse response: {e}")
        return {"success": True, "data": jresp.get("data", {}).get("runTest")}


# ==========================================================
# Cloud Skill Execution (run_in_cloud mode)
# ==========================================================

def gen_write_skill_file_mutation_string(files: list) -> str:
    """
    Generate GraphQL mutation string for writeSkillFile.
    
    Schema:
    input SkillFileInput {
        content: String!
        filePath: String!
        userId: String
    }
    writeSkillFile(input: [SkillFileInput!]): [SkillFileInfo]
    """
    query_string = """
        mutation WriteSkillFileMutation {
      writeSkillFile (input:[
    """
    rec_string = ""
    for i, file_item in enumerate(files):
        file_path = json.dumps(file_item.get('filePath', ''))
        content = json.dumps(file_item.get('content', ''))
        user_id = json.dumps(file_item.get('userId', '')) if file_item.get('userId', '') else ''
        
        rec_string += '{'
        rec_string += f'filePath: {file_path}, '
        rec_string += f'content: {content}'
        if user_id:
            rec_string += f', userId: {user_id}'
        rec_string += '}'
        if i < len(files) - 1:
            rec_string += ','
    
    query_string += rec_string
    query_string += """
      ]) {
        filePath
        fileName
        fileSize
        skillName
        updatedAt
      }
    }
    """
    return query_string


def gen_run_skill_mutation_string(skill_json: str, username: str, meta_data: dict = None) -> str:
    """
    Generate GraphQL mutation string for runSkill.
    
    Schema:
    input RunSkillInput {
        skill: AWSJSON!
        username: String
        meta_data: AWSJSON
    }
    runSkill(input: RunSkillInput!): RunControlResult
    """
    # Escape the skill JSON for GraphQL
    skill_escaped = skill_json.replace('\\', '\\\\').replace('"', '\\"')
    username_escaped = username.replace('"', '\\"') if username else ''
    
    meta_data_part = ""
    if meta_data:
        meta_data_json = json.dumps(meta_data).replace('\\', '\\\\').replace('"', '\\"')
        meta_data_part = f', meta_data: "{meta_data_json}"'
    
    query_string = f"""
        mutation RunSkillMutation {{
          runSkill(input: {{
            skill: "{skill_escaped}",
            username: "{username_escaped}"{meta_data_part}
          }}) {{
            runId
            status
            message
            data
          }}
        }}
    """
    return query_string


def upload_skill_files_to_cloud(session, token, files: list, endpoint=None, timeout=60):
    """
    Upload skill files to cloud S3 via writeSkillFile mutation.
    
    Args:
        session: requests.Session object
        token: Authentication token
        files: List of file items, each with filePath, content, userId
        endpoint: API endpoint URL (optional)
        timeout: Request timeout in seconds
    
    Returns:
        Response from cloud with uploaded file info
    """
    # CN (TCB/COS): writeSkillFile only registers the file and returns a
    # signed COS PUT URL — the CLIENT must upload the bytes. Intl (AWS):
    # the Lambda writes S3 server-side and its SDL has no uploadUrl field,
    # so the extra selection must stay CN-only.
    cn = is_cn_app()
    extra_fields = "\n            uploadUrl\n            method\n            expiresIn" if cn else ""
    mutation_string = f"""
        mutation WriteSkillFile($input: [SkillFileInput!]!) {{
          writeSkillFile(input: $input) {{
            filePath
            fileName
            fileSize
            skillName
            updatedAt{extra_fields}
          }}
        }}
    """
    logger.info(f"[CloudSkill] Uploading {len(files)} skill files to cloud")
    logger.debug(f"[CloudSkill] writeSkillFile using variables, fileCount={len(files)}")

    jresp = appsync_http_request(
        mutation_string,
        session,
        token,
        endpoint,
        timeout=timeout,
        variables={"input": files},
    )

    if "errors" in jresp:
        logger.error(f"[CloudSkill] writeSkillFile error: {jresp['errors']}")
        return {"success": False, "errors": jresp["errors"]}

    try:
        result = jresp.get("data", {}).get("writeSkillFile")
        uploaded_count = len(result) if result else 0
        if uploaded_count == 0:
            logger.warning("[CloudSkill] writeSkillFile returned zero uploaded files")
            return {"success": False, "error": "writeSkillFile returned zero uploaded files", "data": result}

        # CN: PUT each file's content to its signed COS URL. Without this
        # step the metadata row exists but the object never lands in COS
        # (the historical split-persistence bug).
        if cn:
            content_by_path = {
                str(f.get("filePath")): f.get("content")
                for f in files if isinstance(f, dict) and f.get("filePath")
            }
            put_ok, put_fail = 0, 0
            for item in result:
                if not isinstance(item, dict):
                    continue
                url = item.get("uploadUrl") or item.get("upload_url")
                if not url:
                    continue
                body = content_by_path.get(str(item.get("filePath") or item.get("file_path")))
                if body is None:
                    logger.warning(f"[CloudSkill] No local content for signed URL of {item.get('filePath')}")
                    put_fail += 1
                    continue
                method = str(item.get("method") or "PUT").upper()
                try:
                    # No explicit Content-Type: the signature may include the
                    # header set server-side; keep the request minimal.
                    resp = session.request(
                        method=method, url=url,
                        data=body.encode("utf-8") if isinstance(body, str) else body,
                        timeout=timeout,
                    )
                    if resp.status_code in (200, 204):
                        put_ok += 1
                    else:
                        put_fail += 1
                        logger.warning(
                            f"[CloudSkill] COS PUT failed ({resp.status_code}) for "
                            f"{item.get('filePath')}: {resp.text[:200]}"
                        )
                except Exception as put_e:
                    put_fail += 1
                    logger.warning(f"[CloudSkill] COS PUT raised for {item.get('filePath')}: {put_e}")
            logger.info(f"[CloudSkill] COS uploads: {put_ok} ok, {put_fail} failed of {uploaded_count}")
            if put_fail and not put_ok:
                return {"success": False, "error": f"all {put_fail} COS uploads failed", "data": result}
            if put_fail:
                return {"success": False, "error": f"{put_fail} of {uploaded_count} COS uploads failed", "data": result}

        logger.info(f"[CloudSkill] writeSkillFile success: {uploaded_count} files uploaded")
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"[CloudSkill] Failed to parse writeSkillFile response: {e}")
        return {"success": False, "error": str(e)}


def query_cloud_task_run_id(session, token, task_id: str, host_name: str = None, meta_data: dict = None, endpoint=None, timeout=30):
    """
    Query the cloud task's runID via queryCloudTaskRunId GraphQL query.
    
    Used by the local scheduler to obtain the cloud task's runID before
    starting the local helper task for hybrid cloud execution.
    
    Args:
        session: requests.Session object
        token: Authentication token
        task_id: Cloud task ID to look up
        host_name: Hostname of the local client
        meta_data: Optional metadata dict (e.g. owner)
        endpoint: API endpoint URL (optional)
        timeout: Request timeout in seconds
    
    Returns:
        dict with {success, data: {id, runID, runner, status, error}}
    """
    meta_json = json.dumps(meta_data or {}).replace('"', '\\"')
    host = (host_name or '').replace('"', '\\"')
    tid = (task_id or '').replace('"', '\\"')

    query_string = (
        'query { queryCloudTaskRunId(input: {'
        f'task_id: "{tid}", '
        f'host_name: "{host}", '
        f'meta_data: "{meta_json}"'
        '}) { id runID runner status success error timestamp } }'
    )

    logger.info(f"[CloudAPI] queryCloudTaskRunId: task_id={task_id}, host_name={host_name}")

    jresp = appsync_http_request(query_string, session, token, endpoint, timeout=timeout)

    if "errors" in jresp:
        logger.error(f"[CloudAPI] queryCloudTaskRunId error: {jresp['errors']}")
        return {"success": False, "errors": jresp["errors"]}

    try:
        result = jresp.get("data", {}).get("queryCloudTaskRunId")
        if result and result.get("success"):
            logger.info(f"[CloudAPI] queryCloudTaskRunId success: runID={result.get('runID')}")
            return {"success": True, "data": result}
        else:
            error_msg = result.get("error", "Unknown") if result else "No data"
            logger.warning(f"[CloudAPI] queryCloudTaskRunId: no runID yet - {error_msg}")
            return {"success": False, "data": result, "error": error_msg}
    except Exception as e:
        logger.error(f"[CloudAPI] Failed to parse queryCloudTaskRunId response: {e}")
        return {"success": False, "error": str(e)}


def query_cloud_task_run_id_with_retry(session, token, task_id: str, host_name: str = None,
                                        meta_data: dict = None, endpoint=None,
                                        max_wait_seconds: int = 120, poll_interval: int = 5):
    """
    Poll queryCloudTaskRunId until the cloud task's runID is available.
    
    The cloud task and local helper task are scheduled to run at the same time,
    but the local client waits for the cloud task to start first so the runID
    is available.
    
    Args:
        session: requests.Session object
        token: Authentication token
        task_id: Cloud task ID
        host_name: Local client hostname
        meta_data: Optional metadata
        endpoint: API endpoint
        max_wait_seconds: Maximum time to wait for runID
        poll_interval: Seconds between polls
    
    Returns:
        dict with {success, run_id, data} or {success: False, error}
    """
    import time as _time

    elapsed = 0
    last_error = None

    while elapsed < max_wait_seconds:
        result = query_cloud_task_run_id(session, token, task_id, host_name, meta_data, endpoint)

        if result.get("success") and result.get("data", {}).get("runID"):
            run_id = result["data"]["runID"]
            logger.info(f"[CloudAPI] Got cloud runID after {elapsed}s: {run_id}")
            return {"success": True, "run_id": run_id, "data": result["data"]}

        last_error = result.get("error") or "runID not available yet"
        logger.debug(f"[CloudAPI] Waiting for cloud runID... ({elapsed}/{max_wait_seconds}s) - {last_error}")
        _time.sleep(poll_interval)
        elapsed += poll_interval

    logger.warning(f"[CloudAPI] Timed out waiting for cloud runID after {max_wait_seconds}s: {last_error}")
    return {"success": False, "error": f"Timed out after {max_wait_seconds}s: {last_error}"}


def run_cloud_tasks(session, token, task_ids: list, endpoint=None, timeout=60,
                    agent_id: str = None, task_name: str = None, options: dict = None):
    """
    Launch cloud tasks via the runCloudTasks GraphQL mutation and return
    a mapping of task_id → run_id.

    Used for on-demand hybrid cloud execution (chat prompt / agent command)
    where the cloud task is launched immediately and the runID is returned
    in the response (no polling needed).

    Schema:
        input CloudTaskInput { options: AWSJSON!, task_id: String, task_name: String }
        runCloudTasks(input: [CloudTaskInput]!): AWSJSON!

    Args:
        session: requests.Session object
        token: Authentication token
        task_ids: List of cloud task IDs to launch
        endpoint: API endpoint URL (optional)
        timeout: Request timeout in seconds
        agent_id: Optional agent ID to include in each CloudTaskInput
        task_name: Optional task name to include in each CloudTaskInput
        options: Optional dict of extra options (serialized as AWSJSON)

    Returns:
        dict with {success, run_ids: {task_id: run_id, ...}} or {success: False, error}
    """
    if not task_ids:
        return {"success": False, "error": "No task IDs provided"}

    # New schema (2026-02):
    #   input CloudTaskInput { agent_id, task_id, task_name, options: AWSJSON! }
    #   runCloudTasks(input: [CloudTaskInput]!): AWSJSON!

    logger.info(f"[CloudAPI] runCloudTasks: task_ids={task_ids}, agent_id={agent_id}, task_name={task_name}")

    if not endpoint:
        endpoint = get_appsync_endpoint()

    # Build CloudTaskInput items — options is AWSJSON so must be a JSON string
    opts_json = json.dumps(options or {})
    input_items = []
    for tid in task_ids:
        item = {"task_id": str(tid), "options": opts_json}
        if agent_id:
            item["agent_id"] = agent_id
        if task_name:
            item["task_name"] = task_name
        input_items.append(item)

    query = """mutation RunCloudTasks($input: [CloudTaskInput]!) {
        runCloudTasks(input: $input)
    }"""
    variables = {"input": input_items}

    headers = {
        'Content-Type': "application/json",
        'Authorization': _http_auth_header(token),
        'cache-control': "no-cache",
    }

    jresp = None
    last_errors = None
    try:
        logger.debug(f"[CloudAPI] runCloudTasks request: variables={json.dumps(variables)[:500]}")
        response = session.request(
            url=endpoint, method='POST', timeout=timeout,
            headers=headers,
            json={"query": query, "variables": variables},
        )
        jresp = response.json()
    except Exception as e:
        logger.error(f"[CloudAPI] runCloudTasks HTTP error: {e}")
        jresp = {"errors": [{"errorType": "RequestError", "message": str(e)}]}

    if not jresp:
        return {"success": False, "error": "Empty response"}
    if "errors" in jresp:
        logger.error(f"[CloudAPI] runCloudTasks error: {jresp['errors']}")
        return {"success": False, "errors": jresp["errors"], "last_errors": last_errors}

    try:
        raw = jresp.get("data", {}).get("runCloudTasks")

        # runCloudTasks returns AWSJSON — may be a JSON string (sometimes double-encoded)
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, str):
            raw = json.loads(raw)

        # Normalize various response shapes into {task_id: run_id}
        mapping = {}
        extras = {}  # per-task extra fields (e.g. local_helper_skill_name)
        if isinstance(raw, dict) and "items" in raw:
            raw = raw["items"]

        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                tid = item.get("taskId") or item.get("taskID") or item.get("id") or item.get("task_id")
                rid = item.get("runId") or item.get("runID") or item.get("run_id")
                if tid and rid:
                    mapping[str(tid)] = str(rid)
                # Extract optional fields from response
                helper_name = item.get("local_helper_skill_name") or item.get("localHelperSkillName")
                if tid and helper_name:
                    extras.setdefault(str(tid), {})["local_helper_skill_name"] = helper_name
        elif isinstance(raw, dict):
            # Check for top-level local_helper_skill_name
            top_helper = raw.pop("local_helper_skill_name", None) or raw.pop("localHelperSkillName", None)
            for k, v in raw.items():
                if k and v:
                    mapping[str(k)] = str(v)
            if top_helper:
                extras["_default"] = {"local_helper_skill_name": top_helper}

        if mapping:
            logger.info(f"[CloudAPI] runCloudTasks success: {mapping}")
            result = {"success": True, "run_ids": mapping}
            if extras:
                result["extras"] = extras
            return result

        logger.warning(f"[CloudAPI] runCloudTasks: no run_id mapping in response: {raw}")
        return {"success": False, "error": f"Unexpected response: {raw}"}
    except Exception as e:
        logger.error(f"[CloudAPI] Failed to parse runCloudTasks response: {e}")
        return {"success": False, "error": str(e)}


def run_skill_in_cloud(session, token, skill_json: str, username: str, meta_data: dict = None, endpoint=None, timeout=120):
    """
    Run a skill in the cloud via runSkill mutation.
    
    Args:
        session: requests.Session object
        token: Authentication token
        skill_json: JSON string of the skill to run
        username: Username for the run
        meta_data: Optional metadata dict with run_in_cloud, client_id, run_id
        endpoint: API endpoint URL (optional)
        timeout: Request timeout in seconds
    
    Returns:
        Response from cloud with run status
    """
    mutation_string = gen_run_skill_mutation_string(skill_json, username, meta_data)
    logger.info(f"[CloudSkill] Sending runSkill mutation to cloud for user: {username}")
    logger.debug(f"[CloudSkill] meta_data: {meta_data}")
    logger.debug(f"[CloudSkill] runSkill mutation: {mutation_string[:300]}...")
    
    jresp = appsync_http_request(mutation_string, session, token, endpoint, timeout=timeout)
    
    if "errors" in jresp:
        logger.error(f"[CloudSkill] runSkill error: {jresp['errors']}")
        return {"success": False, "errors": jresp["errors"]}
    
    try:
        result = jresp.get("data", {}).get("runSkill")
        logger.info(f"[CloudSkill] runSkill success: runId={result.get('runId') if result else 'N/A'}")
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"[CloudSkill] Failed to parse runSkill response: {e}")
        return {"success": False, "error": str(e)}
