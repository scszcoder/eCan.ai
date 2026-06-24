"""
China-region GraphQL-over-HTTP transport for ``TencentCloudProvider`` (Layer 4).

GraphQL-parity backend (decided 2026-06-24): the CN backend exposes the SAME
GraphQL schema as AWS AppSync — served by a GraphQL server (SCF / container) behind
Tencent Cloud Native Gateway, authenticated with CIAM JWT bearer tokens. So this is
plain GraphQL-over-HTTP, the same wire shape as the AWS path
(``Authorization: <token>`` + POST ``{query, variables}`` -> ``{data, errors}``),
just pointed at the CN endpoint.

Independent from the AWS code (locked decision: CN + global are fully independent, no
sync; the AWS path stays byte-identical). Inert until the CN endpoint is configured —
every call then returns a GraphQL-error-shaped dict so existing callers'
``if "errors" in resp`` handling keeps working unchanged.
"""

import os
import json

import requests
import aiohttp

from config.envi import getECBotDataHome
from utils.logger_helper import logger_helper

_CN_ENDPOINT_LOGGED = False


def get_cn_graphql_endpoint() -> str | None:
    """Resolve the CN GraphQL endpoint: env override, then settings.json, else None.

    Mirrors ``get_appsync_endpoint``'s settings source (``settings.json``) but with a
    ``cn_api_endpoint`` key. Returns ``None`` when unset so the provider stays inert.
    """
    global _CN_ENDPOINT_LOGGED

    ep = os.environ.get("ECAN_CN_GRAPHQL_ENDPOINT", "").strip()
    if ep:
        if not _CN_ENDPOINT_LOGGED:
            logger_helper.info(f"[CN] Using CN GraphQL endpoint (env): {ep}")
            _CN_ENDPOINT_LOGGED = True
        return ep

    try:
        settings_file = os.path.join(getECBotDataHome(), 'resource', 'data', 'settings.json')
        if os.path.exists(settings_file):
            with open(settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            ep = (settings.get('cn_api_endpoint') or "").strip()
            if ep:
                if not _CN_ENDPOINT_LOGGED:
                    logger_helper.info(f"[CN] Using CN GraphQL endpoint (settings.json): {ep}")
                    _CN_ENDPOINT_LOGGED = True
                return ep
    except Exception:
        pass

    return None


def _not_configured() -> dict:
    return {"errors": [{
        "errorType": "CNNotConfigured",
        "message": "CN GraphQL endpoint not configured "
                   "(set ECAN_CN_GRAPHQL_ENDPOINT or settings.json cn_api_endpoint)",
    }]}


def cn_graphql_request(query_string, session, token, endpoint=None,
                       timeout=180, variables=None) -> dict:
    """Synchronous GraphQL-over-HTTP to the CN backend (CIAM JWT bearer)."""
    endpoint = (endpoint or "").strip() or get_cn_graphql_endpoint()
    if not endpoint:
        logger_helper.warning("[CN] GraphQL request with no CN endpoint configured")
        return _not_configured()

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }
    payload = {'query': query_string}
    if variables:
        payload['variables'] = variables

    try:
        resp = session.request(url=endpoint, method='POST', timeout=timeout,
                               headers=headers, json=payload)
        logger_helper.info(f"[CN] GraphQL response status: {resp.status_code} {resp.reason}")
        return resp.json()
    except Exception as e:
        logger_helper.error(f"[CN] GraphQL request failed: {e}")
        return {"errors": [{"errorType": "CNTransportError", "message": str(e)}]}


async def cn_graphql_request_async(query_string, token, endpoint=None, retries=3) -> dict:
    """Async GraphQL-over-HTTP to the CN backend."""
    endpoint = (endpoint or "").strip() or get_cn_graphql_endpoint()
    if not endpoint:
        return _not_configured()

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
    }
    payload = {'query': query_string}

    last_err = None
    for _ in range(max(1, retries)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(endpoint, headers=headers, json=payload,
                                  timeout=aiohttp.ClientTimeout(total=300)) as r:
                    return await r.json()
        except Exception as e:
            last_err = e
    logger_helper.error(f"[CN] async GraphQL request failed after {retries} tries: {last_err}")
    return {"errors": [{"errorType": "CNTransportError", "message": str(last_err)}]}


# --- COS presigned file transfer ---------------------------------------------
# COS is S3-API-compatible, and the S3-vs-COS difference is entirely in the
# backend-generated grant (returned by reqFileOp, which already routes through the
# CN GraphQL transport above). These client transfers assume the CN backend returns
# S3-shaped grants: a POST-policy ({url, fields}) for uploads and a signed URL for
# download/avatar-PUT. If the backend instead issues COS PUT-presigned upload grants,
# switch the upload functions here to PUT the file bytes — a localized change.

def _upload_timeout(size_bytes: int, min_kbps: int = 50) -> int:
    """Dynamic timeout from file size (30s..600s), matching the AWS heuristic."""
    return max(30, min(600, int((size_bytes / (min_kbps * 1024)) * 1.2)))


def cos_upload_via_presigned(src_file, presigned_resp) -> None:
    """Upload via a COS POST-policy grant ({url, fields}) — S3-compatible."""
    file_size = os.path.getsize(src_file)
    timeout = _upload_timeout(file_size)
    with open(src_file, 'rb') as f:
        files = {'file': f}
        r = requests.post(presigned_resp['url'], data=presigned_resp['fields'],
                          files=files, timeout=timeout)
    logger_helper.debug(f"[CN][COS] upload status: {r.status_code}")


async def cos_upload_via_presigned_async(session, src_file, presigned_resp):
    """Async COS POST-policy upload."""
    async with aiohttp.ClientSession() as s:
        with open(src_file, 'rb') as f:
            form = aiohttp.FormData()
            for key, value in presigned_resp['fields'].items():
                form.add_field(key, value)
            form.add_field('file', f, filename=src_file)
            async with s.post(presigned_resp['url'], data=form) as r:
                logger_helper.debug(f"[CN][COS] async upload status: {r.status}")
                return r.status


def cos_download_via_presigned(dest_file, url) -> None:
    """Download from a signed COS URL to ``dest_file`` (S3-compatible GET)."""
    try:
        head = requests.head(url, timeout=10)
        cl = head.headers.get('Content-Length')
        timeout = _upload_timeout(int(cl), min_kbps=100) if cl else 300
    except Exception:
        timeout = 300
    resp = requests.get(url, stream=True, timeout=timeout)
    if resp.status_code == 200:
        dest_dir = os.path.dirname(dest_file)
        if dest_dir and not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        with open(dest_file, 'wb') as f:
            f.write(resp.content)
    else:
        logger_helper.error(f"[CN][COS] download failed: {resp.status_code}")


def cos_upload_file_to_presigned_url(file_path, presigned_url, content_type=None) -> dict:
    """Upload a local file to a presigned COS PUT URL (avatar path)."""
    if not file_path or not presigned_url:
        return {"success": False, "error": "Missing file_path or presigned_url"}
    try:
        file_size = os.path.getsize(file_path)
        timeout = _upload_timeout(file_size)
        headers = {"Content-Type": content_type} if content_type else {}
        with open(file_path, 'rb') as f:
            r = requests.put(presigned_url, data=f, headers=headers, timeout=timeout)
        if r.status_code in (200, 204):
            return {"success": True, "status_code": r.status_code}
        return {"success": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        logger_helper.error(f"[CN][COS] PUT upload failed: {e}")
        return {"success": False, "error": str(e)}
