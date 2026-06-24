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
