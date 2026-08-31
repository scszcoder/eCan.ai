# -*- coding: utf-8 -*-
"""eCanAI dynamic model discovery for the Settings provider tables.

The eCanAI provider rows (llm/embedding/rerank_providers.json) declare
``dynamic_models: true`` and a ``base_url`` pointing at the llm-proxy's
OpenAI-compatible v1 surface. The Settings page's model column renders
``provider.supported_models``, so this module fills that in from a live
``GET <base_url>/models`` (Bearer = the account API key synced into
secure_store), the same call `ecan apikey test` makes.

Models are partitioned by role with name heuristics (the proxy serves one
flat list): 'embedding' in the id → embedding tab, 'rerank' → rerank tab,
everything else → llm tab.

Results are cached for a short TTL so repeated Settings renders don't
hammer the network; failures (no key, offline) leave the provider row
untouched — the frontend then falls back to default_model.
"""

import json
import time
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

_CACHE_TTL_S = 300
_models_cache: Dict[str, Any] = {"ts": 0.0, "ids": None}

_ROLE_KEY_ENV = {
    "llm": "ECANAI_LLM_API_KEY",
    "embedding": "ECANAI_EMBEDDING_API_KEY",
    "rerank": "ECANAI_RERANK_API_KEY",
}


def _is_ecanai(provider: Dict[str, Any]) -> bool:
    return str(provider.get("provider") or provider.get("name") or "").lower() == "ecanai" \
        or str(provider.get("name") or "").lower() == "ecanai"


def _api_key(provider_type: str) -> str:
    try:
        from utils.env.secure_store import secure_store, get_current_username
        username = get_current_username()
        for env in (_ROLE_KEY_ENV.get(provider_type, ""), _ROLE_KEY_ENV["llm"]):
            if env:
                value = secure_store.get(env, username=username)
                if value:
                    return str(value).strip()
    except Exception:
        pass
    return ""


def _fetch_model_ids(base_url: str, api_key: str) -> Optional[List[str]]:
    """GET <base_url>/models; None on any failure (cache misses stay cheap)."""
    import urllib.request as _rq
    try:
        req = _rq.Request(base_url.rstrip("/") + "/models",
                          headers={"Authorization": f"Bearer {api_key}"})
        with _rq.urlopen(req, timeout=10) as resp:
            body = json.load(resp)
        ids = [str(m.get("id")) for m in (body.get("data") or [])
               if isinstance(m, dict) and m.get("id")]
        return ids or None
    except Exception as exc:
        logger.debug(f"[ecanai_utils] model fetch failed: {exc}")
        return None


def _ids_for_role(ids: List[str], provider_type: str) -> List[str]:
    if provider_type == "embedding":
        return [i for i in ids if "embedding" in i.lower()]
    if provider_type == "rerank":
        return [i for i in ids if "rerank" in i.lower()]
    return [i for i in ids
            if "embedding" not in i.lower() and "rerank" not in i.lower()]


def merge_ecanai_models_to_providers(providers: List[Dict[str, Any]],
                                     provider_type: str = "llm") -> List[Dict[str, Any]]:
    """Populate the eCanAI provider row's supported_models from /v1/models.

    Mirrors merge_ollama_models_to_providers: mutates and returns the list;
    a fetch failure leaves the row untouched.
    """
    try:
        target = next((p for p in providers if isinstance(p, dict) and _is_ecanai(p)), None)
        if target is None:
            return providers
        base_url = str(target.get("base_url") or "").strip()
        if not base_url:
            return providers

        now = time.time()
        ids = _models_cache["ids"] if (now - _models_cache["ts"] < _CACHE_TTL_S) else None
        if ids is None:
            api_key = _api_key(provider_type)
            if not api_key:
                logger.debug("[ecanai_utils] no account API key synced — skipping model fetch")
                return providers
            ids = _fetch_model_ids(base_url, api_key)
            if ids is None:
                return providers
            _models_cache["ts"] = now
            _models_cache["ids"] = ids

        role_ids = _ids_for_role(ids, provider_type)
        if not role_ids:
            return providers
        target["supported_models"] = [
            {"name": i, "model_id": i, "display_name": i} for i in role_ids
        ]
        if not target.get("default_model"):
            target["default_model"] = role_ids[0]
        logger.info(f"[ecanai_utils] eCanAI {provider_type} models: {role_ids}")
    except Exception as exc:
        logger.warning(f"[ecanai_utils] merge skipped: {exc}")
    return providers
