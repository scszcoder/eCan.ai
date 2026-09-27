"""Thin async REST client for the eBay Sell/Commerce APIs used to list items."""
import json
from typing import Any, Dict, List, Optional

import httpx

from . import auth, config


class EbayApiError(RuntimeError):
    def __init__(self, status: int, errors: List[dict], where: str = ""):
        self.status, self.errors, self.where = status, errors, where
        first = errors[0] if errors else {}
        super().__init__(f"{where} HTTP {status}: {first.get('message') or first}")


def normalize_errors(body: Any) -> List[dict]:
    """eBay's error/warning objects -> [{error_id, message, detail, parameters}]."""
    if not isinstance(body, dict):
        return []
    out = []
    for severity, key in (("error", "errors"), ("warning", "warnings")):
        for e in body.get(key) or []:
            out.append({
                "error_id": e.get("errorId"),
                "severity": severity,
                "message": e.get("message"),
                "detail": e.get("longMessage") if e.get("longMessage") != e.get("message") else None,
                "parameters": {p.get("name"): p.get("value") for p in e.get("parameters") or []} or None,
            })
    return out


class EbayClient:
    def __init__(self, env: Optional[str] = None, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.env = env or config.current_env()
        self._transport = transport

    async def request(self, method: str, path: str, *, host: str = "api", json_body: Any = None,
                      params: Optional[dict] = None, headers: Optional[dict] = None,
                      content: Optional[bytes] = None, files: Optional[dict] = None,
                      ok=(200, 201, 204)) -> httpx.Response:
        for attempt in (1, 2):
            token = await auth.access_token(self.env)
            h = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            h.update(headers or {})
            async with httpx.AsyncClient(timeout=60, transport=self._transport) as c:
                r = await c.request(method, config.hosts(self.env)[host] + path, params=params,
                                    json=json_body, content=content, files=files, headers=h)
            if r.status_code == 401 and attempt == 1:
                auth.forget_access_token(self.env)  # expired early; mint a new one once
                continue
            break
        if r.status_code not in ok:
            try:
                body = r.json()
            except Exception:
                body = {"errors": [{"message": r.text[:300] or f"HTTP {r.status_code}"}]}
            raise EbayApiError(r.status_code, normalize_errors(body), f"{method} {path}")
        return r

    async def get_json(self, path: str, **kw) -> dict:
        r = await self.request("GET", path, **kw)
        return r.json() if r.content else {}


def body_json(r: httpx.Response) -> dict:
    try:
        return r.json() if r.content else {}
    except json.JSONDecodeError:
        return {}
