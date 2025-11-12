import json
import os
import re
from datetime import datetime

import httpx
import asyncio
import io
from PIL import Image

from config.envi import getECBotDataHome
from utils.logger_helper import logger_helper as logger
import traceback
from config.constants import API_DEV_MODE

ecb_data_homepath = getECBotDataHome()


# Constants Copied from AppSync API 'Settings'

def gen_screen_read_request_js(query, local_info):
    q_data = {
        "inScrn": query,
        "requester": local_info["user"],
        "host": local_info["host_name"],
        "host_ip": local_info["ip"],
        "type": "reqScreenTxtRead",
        "query_type": "Query"
    }

    logger.debug(q_data)
    return q_data


def gen_obtain_review_request_js(query, local_info):
    q_data = {
        "getFB": query,
        "requester": local_info["user"],
        "host_name": local_info["host_name"],
        "host_ip": local_info["ip"],
        "type": "reqScreenTxtRead",
        "query_type": "Query"
    }

    logger.debug(q_data)
    return q_data


# reqTrain(input: [Skill]!): AWSJSON!
def gen_train_request_js(query, local_info):
    q_data = {
        "inScrn": query,
        "requester": local_info["user"],
        "host_name": local_info["host_name"],
        "host_ip": local_info["ip"],
        "type": "reqTrain",
        "query_type": "Query"
    }

    logger.debug(q_data)
    return q_data


async def req_lan_read_screen8(session, request, token, api_key, local_info, imgs, lan_endpoint):
    qdata = gen_screen_read_request_js(request, local_info)
    # logger.debug("request qdata:", qdata)
    logger.debug(f"time stamp800: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}")
    jresp = await lan_http_request8(qdata, imgs, session, token, api_key, lan_endpoint)
    logger.debug(f"milan jresp: {jresp}")
    logger.debug(f"time stamp801: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}")

    try:
        jresp = jresp.json()  # Convert the response to JSON
        logger.debug(f"lan jresp: {jresp}")
    except Exception as e:
        logger.error(f"Failed to parse JSON from response: {e}")
        logger.error(f"Raw response: {jresp.text}")
        return None

    if "errors" in jresp:
        screen_error = True
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        # print("jresp:", jresp)
        jresponse = jresp["data"]["reqScreenTxtRead"]

    return jresponse


def req_lan_read_screen(session, request, token, local_info, imgs, lan_endpoint):
    qdata = gen_screen_read_request_js(request, local_info)

    jresp = lan_http_request2(qdata, imgs, session, token, lan_endpoint)

    if "errors" in jresp:
        screen_error = True
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqScreenTxtRead"])

    return jresponse


# send request over the LAN synchronously.
def lan_http_request2(query_js, imgs, session, token, lan_endpoint):
    LAN_API_ENDPOINT_URL = f"{lan_endpoint}/reqScreenTxtRead"
    logger.info(f"lan endpoint: {LAN_API_ENDPOINT_URL}")
    # headers = {
    #     'Content-Type': "multipart/form-data",
    # }
    # logger.debug("endpoint:", LAN_API_ENDPOINT_URL, headers)
    for img in imgs:
        file_path = img["file_name"]
        if not os.path.exists(file_path):
            logger.error(f"❌ Error: File not found -> {file_path}")

    timeout = httpx.Timeout(connect=10.0, read=100.0, write=30.0, pool=10.0)
    with httpx.Client(timeout=timeout,
                      event_hooks={"request": [lambda r: logger.debug(f"🔍 Raw HTTP Request: {r}")]}) as client:
        try:
            logger.debug("no need to read files, img is already there...")
            # Prepare the multipart form-data request
            # files = {"file": (os.path.basename(query_js['img_file_name']), query_js['img'], "image/png")}
            # files = {
            #     os.path.basename(img["file_name"]): (os.path.basename(img["file_name"]), img["bytes"], "image/png")
            #     for img in imgs
            # }
            files = {
                os.path.basename(img["file_name"]): (os.path.basename(img["file_name"]), open(img["file_name"], "rb"),
                                                     "image/png")
                for img in imgs
            }
            payload = {"data": json.dumps(query_js)}

            logger.info("Sending HTTP request...")

            # Send the async request
            headers = {}
            response = client.post(LAN_API_ENDPOINT_URL, files=files, data=payload, headers=headers)
            logger.info(f"📡 Server Response: {response.status_code}, {response.text}")
            # need to repackage response to be the same format as from aws so that
            # the response handler can be the same. ... sc, well, let's push it to
            # the server side.

            logger.debug(f"Response: {response}")

            return response

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorHttpxClient:" + traceback.format_exc() + " " + str(e)
                logger.error(ex_stat)


# since it's LAN, should be fast, so we send file and request data in 1 shot
async def lan_http_request8(query_js, imgs, session, token, api_key, lan_endpoint):
    # Respect full endpoint if provided; otherwise append once.
    base = (lan_endpoint or "").rstrip("/")
    if "reqScreenTxtRead" in base:
        LAN_API_ENDPOINT_URL = base
    else:
        LAN_API_ENDPOINT_URL = f"{base}/reqScreenTxtRead"
    headers = {
        # 'Content-Type': "multipart/form-data",
        "x-api-key": api_key,
        # "Connection": "close",  # Removed: may cause connection issues
        "Accept": "*/*",
        # 'Authorization': token,
        # 'cache-control': "no-cache",
    }
    logger.info(f"endpoint: {LAN_API_ENDPOINT_URL}, headers: {headers}")

    # Increased read timeout to handle slow server responses
    timeout = httpx.Timeout(connect=60.0, read=180.0, write=60.0, pool=60.0)
    limits = httpx.Limits(max_keepalive_connections=0, max_connections=20)
    async with httpx.AsyncClient(timeout=timeout, limits=limits, http2=False) as client:
        try:
            logger.debug(f"preparing multipart files for upload... {len(imgs or [])}")
            # Build multipart parts exactly like requests test: ("files", (filename, bytes, "image/png"))
            files = []
            for i, img in enumerate(imgs or []):
                fname = os.path.basename(img.get("file_name") or f"file_{i}.png")
                content = img.get("bytes")

                # 1) Already bytes
                if isinstance(content, (bytes, bytearray)):
                    files.append(("files", (fname, content, "image/png")))
                    continue

                # 2) File-like: read into bytes
                if hasattr(content, "read"):
                    try:
                        if hasattr(content, "seek"):
                            content.seek(0)
                        buf_bytes = content.read()
                        files.append(("files", (fname, buf_bytes, "image/png")))
                        continue
                    except Exception:
                        pass

                # 3) PIL Image: encode PNG to bytes
                if isinstance(content, Image.Image):
                    buf = io.BytesIO()
                    content.save(buf, format="PNG")
                    files.append(("files", (fname, buf.getvalue(), "image/png")))
                    continue

                # 4) Fallback to file path
                fpath = img.get("file_name")
                if fpath and os.path.exists(fpath):
                    with open(fpath, "rb") as fobj:
                        file_bytes = fobj.read()
                    files.append(("files", (os.path.basename(fpath), file_bytes, "image/png")))
                    continue

                logger.warning(f"Warning: image #{i} has unsupported content type; skipping.")

            if not files:
                raise ValueError("No valid images provided to upload.")

            payload = {"data": json.dumps(query_js)}

            # Calculate total request size for logging
            total_size = len(json.dumps(query_js))
            for _, (fname, content, _) in files:
                total_size += len(content) if isinstance(content, (bytes, bytearray)) else 0
            logger.info(f"Request size: {total_size / 1024 / 1024:.2f} MB ({len(files)} files)")

            # Send with retry on transient network errors
            max_retries = 3
            retry_delay = 1.0  # seconds
            last_error = None

            for attempt in range(max_retries):
                try:
                    logger.info(f"Sending request to {LAN_API_ENDPOINT_URL} (attempt {attempt + 1}/{max_retries})...")
                    response = await client.post(
                        LAN_API_ENDPOINT_URL,
                        headers=headers,
                        files=files,
                        data=payload,
                        follow_redirects=True,
                    )
                    logger.info(f"Request succeeded on attempt {attempt + 1}, status: {response.status_code}")
                    break
                except (httpx.ReadError, httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout,
                        httpx.WriteTimeout) as e:
                    last_error = e
                    error_type = type(e).__name__
                    error_msg = str(e)[:200] if str(e) else "No error message"
                    logger.warning(f"{error_type} on attempt {attempt + 1}/{max_retries}: {error_msg}")

                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        logger.error(f"All {max_retries} attempts failed. Last error: {error_type}")
                        logger.error(
                            f"Endpoint: {LAN_API_ENDPOINT_URL}, Request size: {total_size / 1024 / 1024:.2f} MB")
                        logger.error(
                            f"Possible causes: 1) Server issues 2) Network instability 3) Request too large 4) Server timeout")
                        raise
                except Exception as e:
                    # Other unexpected errors should not be retried
                    logger.error(f"Unexpected error during request: {type(e).__name__}: {e}")
                    logger.error(f"Endpoint: {LAN_API_ENDPOINT_URL}")
                    raise

            logger.debug(f"MILAN Response: {response}")
            return response

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            traceback_info = traceback.extract_tb(e.__traceback__)
            if traceback_info:
                ex_stat = "ErrorHttpxClient:" + traceback.format_exc() + " " + str(e)
                logger.error(ex_stat)
            raise
