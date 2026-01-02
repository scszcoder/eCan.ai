from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from utils.logger_helper import logger_helper as logger

from agent.cloud_api.cloud_api import (
    send_query_components_request_to_cloud,
    send_get_nodes_prompts_request_to_cloud,
    send_query_fom_request_to_cloud,
    send_rank_results_request_to_cloud,
    send_start_long_llm_task_to_cloud,
    send_init_req_scene_to_cloud,
    send_ready_req_scene_to_cloud,
    upload_file_to_presigned_url,
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


def add_ecan_ai_api_req_create_scene_tool_schema(tool_schemas):
    """Add tool schema for ecan_ai_api_req_create_scene."""
    import mcp.types as types

    tool_schema = types.Tool(
        name="ecan_ai_api_req_create_scene",
        description="""Request cloud-side multi-modal scene generation (text2image, text2video, image2image, image2video, video2video).

Complete flow handled in a single call:
1. Sends initReqScene to cloud to get presigned upload URLs (if refs needed)
2. Automatically uploads reference files to S3 using presigned URLs
3. Sends readyReqScene to confirm uploads and start processing

For text-only prompts (no refs), cloud starts processing immediately.
Results are delivered via pub/sub subscription when generation completes.""",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["agent_id", "description", "output_format"],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Agent ID requesting the scene generation"
                        },
                        "description": {
                            "type": "string",
                            "description": "Text prompt describing the desired scene/image/video"
                        },
                        "output_format": {
                            "type": "string",
                            "enum": ["IMAGE", "VIDEO"],
                            "description": "Output format: IMAGE or VIDEO"
                        },
                        "output_resolution": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Output resolution as [width, height], e.g. [1920, 1080]"
                        },
                        "duration_hint_ms": {
                            "type": "integer",
                            "description": "Hint for video duration in milliseconds"
                        },
                        "emotion": {
                            "type": "string",
                            "description": "Emotional tone for the scene (e.g., 'happy', 'sad', 'neutral')"
                        },
                        "mind_state": {
                            "type": "string",
                            "description": "Mental state context for the scene"
                        },
                        "style": {
                            "type": "string",
                            "enum": ["REALISTIC", "CARTOON", "ANIME", "ARTISTIC", "CINEMATIC"],
                            "description": "Visual style for the generated content"
                        },
                        "context": {
                            "type": "object",
                            "description": "Additional context for generation (gemini_job spec, etc.)"
                        },
                        "refs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "file_path": {
                                        "type": "string",
                                        "description": "Local file path to the reference image/video"
                                    },
                                    "type": {
                                        "type": "string",
                                        "enum": ["image", "video"],
                                        "description": "Type of reference asset"
                                    },
                                    "mime_type": {
                                        "type": "string",
                                        "description": "MIME type (e.g., 'image/jpeg', 'video/mp4')"
                                    }
                                }
                            },
                            "description": "Reference assets with local file_path for upload (images/videos to use as input)"
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def ecan_ai_api_req_create_scene(mainwin, config: dict) -> dict:
    """Request cloud-side multi-modal scene generation.
    
    Complete flow handled in a single call:
    1. Send initReqScene to cloud to get presigned upload URLs (if refs needed)
    2. If refs with local file paths are provided, upload them to S3
    3. Send readyReqScene to confirm uploads complete and start processing
    
    For text-only generation (no refs), cloud starts processing immediately after initReqScene.
    Results are delivered via pub/sub subscription when generation completes.
    
    Args:
        mainwin: Main window instance with session, token, endpoints
        config: Request configuration dict with:
            - agent_id: Agent ID requesting generation
            - description: Text prompt
            - output_format: IMAGE or VIDEO
            - refs: List of reference assets with 'file_path' for local files
            - output_resolution, duration_hint_ms, emotion, mind_state, style, context (optional)
        
    Returns:
        dict with request_id, status, message, estimated_time_ms, upload_results
    """
    logger.info("=" * 60)
    logger.info("[ReqCreateScene] Starting scene generation request")
    logger.info(f"[ReqCreateScene] Input config: {json.dumps(config, indent=2, default=str)}")
    
    result = {
        "request_id": "",
        "status": "Error",
        "message": "",
        "estimated_time_ms": 0,
        "upload_results": []
    }
    
    try:
        session = mainwin.session
        token = mainwin.get_auth_token()
        acct_site_id = mainwin.getAcctSiteID()
        
        logger.info(f"[ReqCreateScene] acctSiteID: {acct_site_id}")
        logger.debug(f"[ReqCreateScene] Token present: {bool(token)}, Token length: {len(token) if token else 0}")
        
        # Get endpoint
        network_api_engine = mainwin.getNetworkApiEngine()
        if network_api_engine == "lan":
            endpoint = mainwin.getLanApiEndpoint()
        else:
            endpoint = mainwin.getWanApiEndpoint()
        
        logger.info(f"[ReqCreateScene] Network engine: {network_api_engine}, Endpoint: {endpoint}")
        
        # Extract config parameters
        agent_id = config.get("agent_id", "")
        description = config.get("description", "")
        output_format = config.get("output_format")  # Optional - don't default, let cloud handle it
        output_resolution = config.get("output_resolution", [])
        duration_hint_ms = config.get("duration_hint_ms")
        emotion = config.get("emotion")
        mind_state = config.get("mind_state")
        style = config.get("style")
        context = config.get("context", {})
        refs = config.get("refs", [])
        
        logger.info(f"[ReqCreateScene] Parsed params - agent_id: {agent_id}, output_format: {output_format}")
        logger.info(f"[ReqCreateScene] Description: {description[:100]}..." if len(description) > 100 else f"[ReqCreateScene] Description: {description}")
        logger.info(f"[ReqCreateScene] Refs count: {len(refs)}, Has context: {bool(context)}")
        if refs:
            for i, ref in enumerate(refs):
                logger.debug(f"[ReqCreateScene] Ref[{i}]: {ref}")
        
        # Build context with gemini_job if not already present
        if not context:
            context = {}
        if not any(k in context for k in ["gemini_job", "geminiJob", "media_job"]):
            # Auto-construct gemini_job from parameters
            operation = None
            # Determine operation based on output_format or infer from refs
            if output_format == "IMAGE" or output_format in ["PNG", "JPEG"]:
                if refs:
                    operation = "image_editing"
                else:
                    operation = "text_to_image"
            elif output_format == "VIDEO" or output_format in ["MP4", "WEBM", "GIF"]:
                if refs:
                    operation = "image_to_video"
                else:
                    operation = "text_to_video"
            elif not output_format:
                # No output_format specified - infer from context
                # Default to text_to_image for text-only, image_editing if refs provided
                if refs:
                    operation = "image_editing"
                else:
                    operation = "text_to_image"
            
            logger.info(f"[ReqCreateScene] Auto-detected operation: {operation}")
            
            if operation:
                gemini_job = {
                    "operation": operation,
                    "prompt": description,
                }
                if refs:
                    gemini_job["reference_assets"] = refs
                if output_resolution and len(output_resolution) >= 2:
                    w, h = output_resolution[0], output_resolution[1]
                    if w > h:
                        gemini_job["aspect_ratio"] = "16:9"
                    elif h > w:
                        gemini_job["aspect_ratio"] = "9:16"
                    else:
                        gemini_job["aspect_ratio"] = "1:1"
                if duration_hint_ms:
                    gemini_job["duration_seconds"] = max(1, duration_hint_ms // 1000)
                
                context["gemini_job"] = gemini_job
                logger.info(f"[ReqCreateScene] Auto-constructed gemini_job: {json.dumps(gemini_job, indent=2)}")
        
        # Step 1: Send initReqScene to cloud
        logger.info("=" * 40)
        logger.info("[ReqCreateScene] STEP 1: Sending initReqScene to cloud")
        
        req_scene_input = {
            "acctSiteID": acct_site_id,
            "agent_id": agent_id,
            "description": description,
            "context": context,
        }
        
        # Only include output_format if explicitly provided (it's an enum that must match cloud schema)
        if output_format:
            req_scene_input["output_format"] = output_format
        
        # Add optional fields
        if output_resolution:
            req_scene_input["output_resolution"] = output_resolution
        if duration_hint_ms is not None:
            req_scene_input["duration_hint_ms"] = duration_hint_ms
        if emotion:
            req_scene_input["emotion"] = emotion
        if mind_state:
            req_scene_input["mind_state"] = mind_state
        if style:
            req_scene_input["style"] = style
        if refs:
            req_scene_input["refs"] = refs
        
        logger.info(f"[ReqCreateScene] initReqScene payload: {json.dumps(req_scene_input, indent=2, default=str)}")
        
        init_response = send_init_req_scene_to_cloud(session, token, req_scene_input, endpoint)
        
        logger.info(f"[ReqCreateScene] initReqScene response status: {'ERROR' if 'errors' in init_response else 'OK'}")
        logger.info(f"[ReqCreateScene] initReqScene full response: {json.dumps(init_response, indent=2, default=str)}")
        
        if "errors" in init_response:
            error_msg = init_response.get("message", "initReqScene failed")
            logger.error(f"[ReqCreateScene] initReqScene FAILED: {error_msg}")
            logger.error(f"[ReqCreateScene] Errors: {init_response.get('errors', [])}")
            result["message"] = error_msg
            return result
        
        request_id = init_response.get("request_id", "")
        result["request_id"] = request_id
        result["estimated_time_ms"] = init_response.get("estimated_time_ms", 30000)
        
        ref_ul_links = init_response.get("ref_ul_links", [])
        logger.info(f"[ReqCreateScene] Got request_id: {request_id}")
        logger.info(f"[ReqCreateScene] Got {len(ref_ul_links)} presigned upload URLs")
        
        # Step 2: If we have upload links and local files, upload them
        if ref_ul_links and refs:
            logger.info("=" * 40)
            logger.info(f"[ReqCreateScene] STEP 2: Uploading {len(ref_ul_links)} reference files to S3")
            upload_results = []
            all_uploads_success = True
            
            for i, upload_link_data in enumerate(ref_ul_links):
                logger.info(f"[ReqCreateScene] Processing upload {i+1}/{len(ref_ul_links)}")
                logger.debug(f"[ReqCreateScene] Upload link data: {str(upload_link_data)[:150]}...")
                
                # Parse upload_url from the ref_ul_links entry
                # Cloud may return: 
                # 1. A dict with 'upload_url' key
                # 2. A string like "{ref={...}, upload_url=https://..., s3_key=...}"
                # 3. Just the URL string directly
                upload_url = None
                if isinstance(upload_link_data, dict):
                    upload_url = upload_link_data.get("upload_url") or upload_link_data.get("url")
                elif isinstance(upload_link_data, str):
                    # Try to extract upload_url from string format
                    if upload_link_data.startswith("http"):
                        upload_url = upload_link_data
                    elif "upload_url=" in upload_link_data:
                        # Parse from format: "{ref={...}, upload_url=https://..., s3_key=...}"
                        import re
                        match = re.search(r'upload_url=(https?://[^,}]+)', upload_link_data)
                        if match:
                            upload_url = match.group(1).strip()
                            logger.info(f"[ReqCreateScene] Extracted upload_url from string: {upload_url[:80]}...")
                
                if not upload_url:
                    logger.error(f"[ReqCreateScene] Could not extract upload_url from: {str(upload_link_data)[:200]}")
                    upload_results.append({
                        "index": i,
                        "file_path": None,
                        "success": False,
                        "error": "Could not extract upload_url from response"
                    })
                    all_uploads_success = False
                    continue
                
                logger.debug(f"[ReqCreateScene] Upload URL: {upload_url[:100]}..." if len(upload_url) > 100 else f"[ReqCreateScene] Upload URL: {upload_url}")
                
                # Find corresponding ref with file_path and mime_type
                file_path = None
                mime_type = None
                if i < len(refs):
                    ref = refs[i]
                    logger.debug(f"[ReqCreateScene] Ref[{i}] type: {type(ref)}, value: {ref}")
                    if isinstance(ref, dict):
                        file_path = ref.get("file_path") or ref.get("path") or ref.get("local_path")
                        mime_type = ref.get("mime_type") or ref.get("content_type")
                    elif isinstance(ref, str):
                        # ref might be a file path directly
                        file_path = ref
                
                if file_path:
                    import os
                    file_exists = os.path.exists(file_path)
                    file_size = os.path.getsize(file_path) if file_exists else 0
                    logger.info(f"[ReqCreateScene] Uploading ref {i+1}/{len(ref_ul_links)}: {file_path}")
                    logger.info(f"[ReqCreateScene] File exists: {file_exists}, Size: {file_size} bytes")
                    if mime_type:
                        logger.info(f"[ReqCreateScene] Using mime_type from ref: {mime_type}")
                    
                    if not file_exists:
                        logger.error(f"[ReqCreateScene] File NOT FOUND: {file_path}")
                        upload_results.append({
                            "index": i,
                            "file_path": file_path,
                            "success": False,
                            "error": f"File not found: {file_path}"
                        })
                        all_uploads_success = False
                        continue
                    
                    # Pass mime_type to match what presigned URL was generated with
                    upload_result = upload_file_to_presigned_url(file_path, upload_url, content_type=mime_type)
                    logger.info(f"[ReqCreateScene] Upload result for ref {i+1}: {upload_result}")
                    
                    upload_results.append({
                        "index": i,
                        "file_path": file_path,
                        "success": upload_result.get("success", False),
                        "error": upload_result.get("error", "")
                    })
                    if not upload_result.get("success"):
                        all_uploads_success = False
                        logger.error(f"[ReqCreateScene] ❌ UPLOAD FAILED for {file_path}: {upload_result.get('error')}")
                    else:
                        logger.info(f"[ReqCreateScene] ✅ Upload SUCCESS for {file_path}")
                else:
                    logger.warning(f"[ReqCreateScene] ⚠️ No file_path found for ref {i}, skipping upload")
                    logger.warning(f"[ReqCreateScene] Ref content: {refs[i] if i < len(refs) else 'N/A'}")
                    upload_results.append({
                        "index": i,
                        "file_path": None,
                        "success": False,
                        "error": "No file_path provided in ref"
                    })
                    all_uploads_success = False
            
            result["upload_results"] = upload_results
            logger.info(f"[ReqCreateScene] Upload summary: {len([r for r in upload_results if r['success']])}/{len(upload_results)} succeeded")
            
            # Step 3: Send readyReqScene to confirm uploads
            logger.info("=" * 40)
            logger.info("[ReqCreateScene] STEP 3: Sending readyReqScene to confirm uploads")
            
            upload_status = "Completed" if all_uploads_success else "Error"
            ready_input = {
                "acctSiteID": acct_site_id,
                "request_id": request_id,
                "status": upload_status
            }
            
            logger.info(f"[ReqCreateScene] readyReqScene payload: {json.dumps(ready_input, indent=2)}")
            
            ready_response = send_ready_req_scene_to_cloud(session, token, ready_input, endpoint)
            
            logger.info(f"[ReqCreateScene] readyReqScene response status: {'ERROR' if 'errors' in ready_response else 'OK'}")
            logger.info(f"[ReqCreateScene] readyReqScene full response: {json.dumps(ready_response, indent=2, default=str)}")
            
            if "errors" in ready_response:
                error_msg = ready_response.get("message", "readyReqScene failed")
                logger.error(f"[ReqCreateScene] readyReqScene FAILED: {error_msg}")
                logger.error(f"[ReqCreateScene] Errors: {ready_response.get('errors', [])}")
                result["status"] = "Error"
                result["message"] = error_msg
                return result
            
            if all_uploads_success:
                result["status"] = ready_response.get("status", "Processing")
                result["message"] = ready_response.get("message", "Generation started. Results will be delivered via subscription.")
                logger.info(f"[ReqCreateScene] ✅ All uploads successful, generation started")
            else:
                result["status"] = "UploadFailed"
                result["message"] = "Some uploads failed. Check upload_results for details."
                logger.warning(f"[ReqCreateScene] ⚠️ Some uploads failed, notified cloud with Error status")
        else:
            # No refs or no upload links - text-only generation starts immediately
            logger.info("[ReqCreateScene] No refs to upload - text-only generation, skipping Steps 2 & 3")
            result["status"] = init_response.get("status", "Processing")
            result["message"] = init_response.get("message", "Generation started. Results will be delivered via subscription.")
        
        logger.info("=" * 40)
        logger.info(f"[ReqCreateScene] COMPLETED - Final result: {json.dumps(result, indent=2, default=str)}")
        logger.info("=" * 60)
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEcanAiApiReqCreateScene")
        logger.error(err_trace)
        result["message"] = str(e)
    
    return result


