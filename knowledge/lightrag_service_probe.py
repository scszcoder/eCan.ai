"""Small, non-destructive probes for model services used by LightRAG."""

from typing import Any, Dict
from urllib.parse import urlparse

import requests


class ServiceProbeError(RuntimeError):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


def _url(host: Any, path: str) -> str:
    base = str(host or "").strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ServiceProbeError("invalid_config", "服务地址必须是有效的 HTTP(S) 地址")
    return base if base.lower().endswith(path.lower()) else f"{base}{path}"


def _post(url: str, payload: Dict[str, Any], api_key: str = "", verify_ssl: bool = False) -> requests.Response:
    headers = {"Content-Type": "application/json"}
    if api_key and api_key != "your_api_key":
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        # A status badge must fail fast. A long model-generation timeout here
        # blocks every automatic provider check and makes the settings page
        # appear stuck. Keep connect/read limits separate so unreachable
        # services are reported promptly while local models still get a
        # little time to answer the minimal probe.
        response = requests.post(
            url, json=payload, headers=headers, timeout=(3, 7), verify=verify_ssl
        )
    except requests.Timeout as exc:
        raise ServiceProbeError("timeout", f"连接服务超时：{url}") from exc
    except requests.ConnectionError as exc:
        raise ServiceProbeError("connection", f"无法连接到服务：{url}（{exc}）") from exc
    except requests.RequestException as exc:
        raise ServiceProbeError("unknown", f"请求服务失败：{url}（{exc}）") from exc
    if response.status_code in (401, 403):
        raise ServiceProbeError("authentication", f"身份验证失败：{url}（HTTP {response.status_code}）")
    if not response.ok:
        body = (response.text or response.reason or "未知错误").strip()[:500]
        raise ServiceProbeError("service_error", f"服务返回异常：{url}（HTTP {response.status_code}）：{body}")
    return response


def probe_model_service(kind: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    service = str(kind or "").strip().lower()
    prefix = {"llm": "LLM", "embedding": "EMBEDDING", "rerank": "RERANK"}.get(service)
    if not prefix:
        raise ServiceProbeError("invalid_config", "不支持的服务类型")

    binding = str(settings.get(f"{prefix}_BINDING") or "").strip().lower()
    host = settings.get(f"{prefix}_BINDING_HOST")
    model = str(settings.get(f"{prefix}_MODEL") or "").strip()
    api_key = str(settings.get(f"{prefix}_BINDING_API_KEY") or "").strip()
    # LightRAG itself defaults SSL_VERIFY to false so self-signed HTTPS
    # providers work. Keep the probe consistent with the actual runtime;
    # callers can explicitly set SSL_VERIFY=true for strict verification.
    ssl_value = str(settings.get("SSL_VERIFY", "false")).strip().lower()
    verify_ssl = ssl_value in {"1", "true", "yes", "on"}
    if not binding:
        raise ServiceProbeError("missing_config", "未选择服务提供商")
    if not model:
        raise ServiceProbeError("missing_config", "未选择模型")

    if service == "llm":
        if binding == "ollama":
            url = _url(host, "/api/chat")
            payload = {"model": model, "messages": [{"role": "user", "content": "Reply OK"}], "stream": False,
                       "options": {"num_predict": 2}}
        else:
            url = _url(host, "/chat/completions")
            payload = {"model": model, "messages": [{"role": "user", "content": "Reply OK"}],
                       "max_completion_tokens": 2, "temperature": 0}
    elif service == "embedding":
        if binding == "ollama":
            url = _url(host, "/api/embed")
            payload = {"model": model, "input": "connection test"}
        else:
            url = _url(host, "/embeddings")
            payload = {"model": model, "input": "connection test"}
    else:
        url = _url(host, "/rerank")
        payload = {"model": model, "query": "connection test", "documents": ["connection test", "other text"], "top_n": 1}

    response = _post(url, payload, api_key, verify_ssl=verify_ssl)
    try:
        response.json()
    except ValueError as exc:
        raise ServiceProbeError("wrong_service", "地址可访问，但返回内容不是预期的 JSON API") from exc
    return {"success": True, "available": True, "kind": service, "binding": binding, "model": model,
            "url": url, "status_code": response.status_code, "ssl_verify": verify_ssl}
