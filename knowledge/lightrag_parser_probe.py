"""Non-destructive connectivity probes for LightRAG external parsers."""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import quote, urlparse

import requests


DEFAULT_TIMEOUT_SECONDS = 10


def _base_url(value: Any, field: str) -> str:
    url = str(value or "").strip().rstrip("/")
    if not url:
        raise ValueError(f"未配置 {field}")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"{field} 必须是有效的 HTTP(S) 地址")
    return url


def _request(method: str, url: str, **kwargs: Any) -> requests.Response:
    try:
        return requests.request(
            method,
            url,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            allow_redirects=True,
            **kwargs,
        )
    except requests.Timeout as exc:
        raise RuntimeError(f"连接超时（{DEFAULT_TIMEOUT_SECONDS} 秒）：{url}") from exc
    except requests.ConnectionError as exc:
        raise RuntimeError(f"无法连接到服务：{url}（{exc}）") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"请求失败：{url}（{exc}）") from exc


def _error_detail(response: requests.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = body.get("message") or body.get("msg") or body.get("detail") or body.get("error")
            if detail:
                return str(detail)[:500]
    except ValueError:
        pass
    return (response.text or response.reason or "未知错误").strip()[:500]


def _probe_health(
    engine: str,
    endpoint: str,
    headers: Dict[str, str] | None = None,
    verify_ssl: bool = False,
) -> Dict[str, Any]:
    url = f"{endpoint}/health"
    response = _request("GET", url, headers=headers or {}, verify=verify_ssl)
    if not response.ok:
        raise RuntimeError(
            f"{engine} 健康检查返回 HTTP {response.status_code}：{_error_detail(response)}"
        )
    return {
        "success": True,
        "engine": engine.lower(),
        "url": url,
        "status_code": response.status_code,
        "ssl_verify": verify_ssl,
        "message": f"{engine} 连接成功，健康检查通过",
    }


def probe_mineru(settings: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(settings.get("MINERU_API_MODE") or "local").strip().lower()
    ssl_value = str(settings.get("SSL_VERIFY", "false")).strip().lower()
    verify_ssl = ssl_value in {"1", "true", "yes", "on"}
    if mode in ("local", "ecanai"):
        # ``ecanai`` is an eCan convenience alias; at runtime it is rewritten
        # to ``local`` with ``MINERU_LOCAL_ENDPOINT`` pointed at the eCanAI
        # proxy. Each mode owns a dedicated endpoint env var so the
        # user-typed local value is preserved across mode switches.
        if mode == "local":
            endpoint_field = "MINERU_LOCAL_ENDPOINT_SETTING"
        else:  # ecanai
            endpoint_field = "MINERU_ECANAI_ENDPOINT"
        endpoint_value = settings.get(endpoint_field)
        if mode == "local" and not endpoint_value:
            # Backward compatibility for unsaved legacy settings.
            endpoint_value = settings.get("MINERU_LOCAL_ENDPOINT")
        endpoint = _base_url(endpoint_value, endpoint_field)

        # Per-mode API key: the UI shows the field matching this mode and
        # the user types into it. eCanAI mode uses MINERU_API_TOKEN (the
        # ecanai-only field); local mode uses MINERU_LOCAL_API_KEY. To
        if mode == "local":
            token = str(settings.get("MINERU_LOCAL_API_KEY") or "").strip()
            if not token:
                raise ValueError("local 模式未配置 MINERU_LOCAL_API_KEY")
        else:  # ecanai
            token = str(settings.get("MINERU_API_TOKEN") or "").strip()
            if not token:
                raise ValueError(
                    "ecanai 模式未获取到账户 API Key（MINERU_API_TOKEN / ECANAI_LLM_API_KEY）"
                )
        result = _probe_health(
            "MinerU ecanai" if mode == "ecanai" else "MinerU local",
            endpoint,
            headers={"Authorization": f"Bearer {token}"},
            verify_ssl=verify_ssl,
        )
        result["mode"] = mode
        return result
    if mode != "official":
        raise ValueError("MINERU_API_MODE 只能是 local / ecanai / official")

    endpoint = _base_url(
        settings.get("MINERU_OFFICIAL_ENDPOINT") or "https://mineru.net",
        "MINERU_OFFICIAL_ENDPOINT",
    )
    # Use per-mode API key: MINERU_OFFICIAL_API_KEY for official.
    token = str(settings.get("MINERU_OFFICIAL_API_KEY") or "").strip()
    if not token:
        raise ValueError("official 模式未配置 MINERU_OFFICIAL_API_KEY")

    # Querying a deliberately nonexistent task is read-only. A structured
    # 2xx/4xx response proves the API route is present; 401/403 proves auth is
    # invalid. Generic 404 pages are rejected to avoid false positives.
    probe_id = quote("ecan-configuration-probe", safe="")
    url = f"{endpoint}/api/v4/extract/task/{probe_id}"
    response = _request(
        "GET",
        url,
        headers={"Authorization": f"Bearer {token}"},
        verify=verify_ssl,
    )
    if response.status_code in (401, 403):
        raise RuntimeError(f"MinerU official 鉴权失败（HTTP {response.status_code}），请检查 MINERU_OFFICIAL_API_KEY")
    content_type = response.headers.get("content-type", "").lower()
    if response.status_code >= 500:
        raise RuntimeError(f"MinerU official 服务异常 HTTP {response.status_code}：{_error_detail(response)}")
    if "json" not in content_type:
        raise RuntimeError(
            f"地址可访问，但不像 MinerU official API（HTTP {response.status_code}，返回类型 {content_type or '未知'}）"
        )
    return {
        "success": True,
        "engine": "mineru",
        "mode": mode,
        "url": url,
        "status_code": response.status_code,
        "ssl_verify": verify_ssl,
        "message": "MinerU official 地址可用，API 鉴权已通过",
    }


def probe_docling(settings: Dict[str, Any]) -> Dict[str, Any]:
    provider = str(settings.get("DOCLING_PROVIDER") or "ecanai").strip().lower()
    ssl_value = str(settings.get("SSL_VERIFY", "false")).strip().lower()
    verify_ssl = ssl_value in {"1", "true", "yes", "on"}

    if provider == "local":
        endpoint = _base_url(settings.get("DOCLING_LOCAL_ENDPOINT"), "DOCLING_LOCAL_ENDPOINT")
        api_key = str(settings.get("DOCLING_LOCAL_API_KEY") or "").strip()
        if not api_key:
            raise ValueError("local 模式未配置 DOCLING_LOCAL_API_KEY")
    elif provider == "official":
        endpoint = _base_url(settings.get("DOCLING_OFFICIAL_ENDPOINT"), "DOCLING_OFFICIAL_ENDPOINT")
        api_key = str(settings.get("DOCLING_OFFICIAL_API_KEY") or "").strip()
        if not api_key:
            raise ValueError("official 模式未配置 DOCLING_OFFICIAL_API_KEY")
    else:
        # eCanAI always uses the account-managed key. Local credentials must
        # never leak into this protocol.
        endpoint = _base_url(settings.get("DOCLING_ECANAI_ENDPOINT"), "DOCLING_ECANAI_ENDPOINT")
        api_key = str(settings.get("DOCLING_API_KEY") or "").strip()
        if not api_key:
            raise ValueError(
                "eCanAI 模式未获取到账户 API Key（DOCLING_API_KEY / ECANAI_LLM_API_KEY）"
            )

    return _probe_health(
        f"Docling {provider}",
        endpoint,
        headers={"Authorization": f"Bearer {api_key}"},
        verify_ssl=verify_ssl,
    )


def probe_parser(engine: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    engine_id = str(engine or "").strip().lower()
    if engine_id == "mineru":
        return probe_mineru(settings)
    if engine_id == "docling":
        return probe_docling(settings)
    raise ValueError("只有 MinerU 和 Docling 支持配置探针")
