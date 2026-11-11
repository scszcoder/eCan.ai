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
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

_CACHE_TTL_S = 300
_models_cache: Dict[str, Any] = {"ts": 0.0, "ids": None, "rows": None}
_fetch_failure_warned = False
# The last live list, saved so a restart without network still shows the
# server's models; the build-time llm_providers.json is the last resort.
_LIVE_FILE = "llm_live_models.json"

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


def _session_token() -> str:
    from agent.cloud_api.endpoints import llm_proxy_session_token
    return llm_proxy_session_token()


def _fetch_model_rows(base_url: str, api_key: str) -> Optional[List[Dict[str, str]]]:
    """GET <base_url>/models -> [{id, owned_by}]; None on any failure."""
    import urllib.request as _rq
    try:
        req = _rq.Request(base_url.rstrip("/") + "/models",
                          headers={"Authorization": f"Bearer {api_key}"})
        with _rq.urlopen(req, timeout=10) as resp:
            body = json.load(resp)
        rows = [{"id": str(m.get("id")),
                 "owned_by": str(m.get("owned_by") or m.get("provider") or "")}
                for m in (body.get("data") or []) if isinstance(m, dict) and m.get("id")]
        return rows or None
    except Exception as exc:
        # Once per session at WARNING: a failing fetch otherwise just looks
        # like an old model list (intl fetched the CN proxy for months).
        global _fetch_failure_warned
        if not _fetch_failure_warned:
            _fetch_failure_warned = True
            logger.warning(f"[ecanai_utils] model list fetch from {base_url} failed: {exc}; "
                           "showing the saved or bundled list")
        else:
            logger.debug(f"[ecanai_utils] model fetch failed: {exc}")
        return None


def _fetch_model_ids(base_url: str, api_key: str) -> Optional[List[str]]:
    """GET <base_url>/models; None on any failure (cache misses stay cheap)."""
    rows = _fetch_model_rows(base_url, api_key)
    return [r["id"] for r in rows] if rows else None


def _live_file() -> Path:
    from config.app_info import app_info
    return Path(app_info.appdata_path) / _LIVE_FILE


def _save_live(rows: List[Dict[str, str]]) -> None:
    try:
        path = _live_file()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"fetched_at": time.time(), "models": rows}, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        logger.debug(f"[ecanai_utils] could not save the live model list: {exc}")


def _load_saved() -> Optional[List[Dict[str, str]]]:
    try:
        data = json.loads(_live_file().read_text(encoding="utf-8"))
        rows = [r for r in (data.get("models") or []) if isinstance(r, dict) and r.get("id")]
        return rows or None
    except Exception:
        return None


def live_model_rows(providers: List[Dict[str, Any]]) -> Tuple[Optional[List[Dict[str, str]]], str]:
    """The llm-proxy's model list: (rows, source). Live (memory cache, else a
    fetch -- which is then saved), else the list saved by the last good fetch,
    else (None, "none") -- callers keep the build-time llm_providers.json."""
    now = time.time()
    if _models_cache.get("rows") and now - _models_cache["ts"] < _CACHE_TTL_S:
        return _models_cache["rows"], "live"
    target = next((p for p in providers if isinstance(p, dict) and _is_ecanai(p)), None)
    base_url = str((target or {}).get("base_url") or "").strip()
    api_key = (_api_key("llm") or _session_token()) if base_url else ""
    rows = _fetch_model_rows(base_url, api_key) if (base_url and api_key) else None
    if rows:
        _models_cache.update(ts=now, rows=rows, ids=[r["id"] for r in rows])
        _save_live(rows)
        return rows, "live"
    saved = _load_saved()
    if saved:
        return saved, "saved"
    return None, "none"


# Local / self-hosted providers list their own models (ollama_utils, ryoais_utils).
_LOCAL_PROVIDERS = {"ollama", "ryoais"}


# The catalogue is one flat list: speech, image/video and OCR models share the
# chat providers' owners (owned_by "qwen" covers wan2.x and cosyvoice too).
_NON_CHAT = re.compile(r"embedding|rerank|tts|asr|paraformer|cosyvoice|^wan\d|image|t2i|i2i|t2v|i2v|ocr")


def _is_chat_model(model_id: str) -> bool:
    return not _NON_CHAT.search(str(model_id or "").lower())


def _name_prefix(model: str) -> str:
    m = re.match(r"[a-z]+", str(model or "").lower())
    return m.group(0) if m and len(m.group(0)) >= 3 else ""


def _provider_keys(provider: Dict[str, Any]) -> set:
    return {str(provider.get(k) or "").strip().lower() for k in ("name", "provider", "display_name")} - {""}


def merge_live_models_to_providers(providers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every cloud provider's model choices from the llm-proxy's catalogue (all
    LLM calls go through it), so a model added on the server appears without an
    app release. A model is a provider's when its owned_by names the provider,
    else when its id starts like the provider's build-time models (qwen…,
    deepseek…). A provider the catalogue says nothing about keeps its
    build-time list. Mutates and returns *providers*."""
    try:
        rows, source = live_model_rows(providers)
        if not rows:
            return providers
        llm_rows = [r for r in rows if _is_chat_model(r["id"])]
        for p in providers:
            if not isinstance(p, dict) or _is_ecanai(p):
                continue
            keys = _provider_keys(p)
            if keys & _LOCAL_PROVIDERS:
                continue
            bundled = [m for m in (p.get("supported_models") or []) if isinstance(m, dict)]
            prefixes = {_name_prefix(m.get("model_id") or m.get("name")) for m in bundled} - {""}
            mine = [r for r in llm_rows
                    if (r.get("owned_by") and r["owned_by"].lower() in keys)
                    or (not r.get("owned_by") and _name_prefix(r["id"]) in prefixes)]
            if not mine:
                continue
            by_id = {str(m.get("model_id") or m.get("name")): m for m in bundled}
            p["supported_models"] = [
                {**by_id.get(r["id"], {}), "name": r["id"], "model_id": r["id"],
                 "display_name": (by_id.get(r["id"]) or {}).get("display_name") or r["id"]}
                for r in mine]
            p["models_source"] = source
        logger.debug(f"[ecanai_utils] provider model lists from the {source} llm-proxy catalogue")
    except Exception as exc:
        logger.warning(f"[ecanai_utils] live model merge skipped: {exc}")
    return providers


def _ids_for_role(ids: List[str], provider_type: str) -> List[str]:
    if provider_type == "embedding":
        return [i for i in ids if "embedding" in i.lower()]
    if provider_type == "rerank":
        return [i for i in ids if "rerank" in i.lower()]
    return [i for i in ids if _is_chat_model(i)]   # not embedding/rerank/speech/image/video/OCR


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

        rows, _src = live_model_rows(providers)
        if not rows:
            logger.debug("[ecanai_utils] no live or saved model list — keeping the build-time row")
            return providers
        ids = [r["id"] for r in rows]

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
