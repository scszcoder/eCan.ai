"""
Planes: where knowledge lives, and routing a question across them.

  local    the Knowledge Service inside this desktop app
  private  a KS server on the customer's own hardware (on-prem)
  public   a KS server in our cloud

Connections to private/public servers are saved per user in
``connections.json`` next to the local database. A question fans out to the
local service and every enabled connection; results are tagged with their
plane and sensitivity, and the best confident answer wins. If any private
result is used, the answer is marked ``private`` so the agent harness keeps
it away from cloud LLMs (taint.py).
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from knowledge.ks._log import logger

SENSITIVITY_RANK = {"public": 0, "internal": 1, "private": 2}


def most_sensitive(values) -> str:
    vals = [v for v in values if v in SENSITIVITY_RANK] or ["internal"]
    return max(vals, key=lambda v: SENSITIVITY_RANK[v])


class RemoteKS:
    """Client for a Knowledge Service server (server.py)."""

    def __init__(self, base_url: str, token_provider: Callable[[], str], tenant_id: str = "",
                 verify_tls: bool = True, timeout: float = 15.0, agent_id: str = "", store_id: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token_provider = token_provider
        self.tenant_id = tenant_id
        self.verify_tls = verify_tls
        self.timeout = timeout
        self.agent_id, self.store_id = agent_id, store_id

    def _headers(self) -> Dict[str, str]:
        h = {"Authorization": f"Bearer {self.token_provider() or ''}"}
        if self.agent_id:
            h["X-Ecan-Agent"] = self.agent_id
        if self.store_id:
            h["X-Ecan-Store"] = self.store_id
        return h

    def _request(self, method: str, path: str, **kw) -> Any:
        import httpx
        with httpx.Client(timeout=self.timeout, verify=self.verify_tls) as c:
            r = c.request(method, self.base_url + path, headers=self._headers(), **kw)
        if r.status_code >= 400:
            try:
                msg = r.json().get("message") or r.text
            except Exception:
                msg = r.text
            raise RemoteError(r.status_code, msg)
        return r.json()

    def health(self) -> Dict[str, Any]:
        import httpx
        with httpx.Client(timeout=5.0, verify=self.verify_tls) as c:
            r = c.get(self.base_url + "/v1/health")
            r.raise_for_status()
            return r.json()

    def me(self) -> Dict[str, Any]:
        return self._request("GET", "/v1/me")

    def search(self, query: str, store: str = "", platform_item_id: str = "", product_id: str = "") -> Dict[str, Any]:
        return self._request("POST", f"/v1/tenants/{self.tenant_id}/search", json={
            "query": query, "store": store, "platform_item_id": platform_item_id, "product_id": product_id})

    def local_login(self, email: str, password: str) -> str:
        import httpx
        with httpx.Client(timeout=self.timeout, verify=self.verify_tls) as c:
            r = c.post(self.base_url + "/v1/auth/local", json={"email": email, "password": password})
        if r.status_code >= 400:
            raise RemoteError(r.status_code, r.json().get("message", r.text))
        return r.json()["access_token"]


class RemoteError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


# ---- connections ---------------------------------------------------------------------
class ConnectionStore:
    """Saved connections to private / public KS servers (no secrets on disk:
    tokens are kept in memory or the app's secure store)."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._tokens: Dict[str, str] = {}

    def list(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _write(self, items: List[Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def save(self, conn: Dict[str, Any]) -> Dict[str, Any]:
        plane = conn.get("plane")
        if plane not in ("private", "public"):
            raise ValueError("plane must be private or public")
        url = str(conn.get("base_url") or "").strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise ValueError("server address must start with http:// or https://")
        if plane == "public" and url.startswith("http://") and not _is_loopback_url(url):
            raise ValueError("cloud connections must use https://")
        # A private server authenticates with its own key by default: the app
        # sign-in token is the account's key to the eCan cloud (CN: a 30-day
        # session token) and must not go to arbitrary servers.
        auth = conn.get("auth") or ("local" if plane == "private" else "app")
        if auth not in ("app", "local"):
            raise ValueError("auth must be app or local")
        if auth == "app" and not _token_safe_url(url):
            raise ValueError("signing in with the app account needs an https:// server address "
                             "(or this machine); use the server's own key for http://")
        with self._lock:
            items = self.list()
            cid = conn.get("id") or f"cn_{uuid.uuid4().hex[:10]}"
            row = {"id": cid, "name": str(conn.get("name") or url), "plane": plane, "base_url": url,
                   "tenant_id": str(conn.get("tenant_id") or ""), "auth": auth,
                   "enabled": bool(conn.get("enabled", True)), "verify_tls": bool(conn.get("verify_tls", True)),
                   "send_queries": bool(conn.get("send_queries", True))}
            items = [i for i in items if i["id"] != cid] + [row]
            self._write(items)
            return row

    def delete(self, cid: str) -> None:
        with self._lock:
            self._write([i for i in self.list() if i["id"] != cid])
            self._tokens.pop(cid, None)

    def set_token(self, cid: str, token: str) -> None:
        self._tokens[cid] = token

    def token(self, cid: str) -> str:
        return self._tokens.get(cid, "")


def _is_loopback_url(url: str) -> bool:
    from urllib.parse import urlparse
    return (urlparse(url).hostname or "") in ("127.0.0.1", "localhost", "::1")


def _token_safe_url(url: str) -> bool:
    """The app account token may only travel over https, or stay on this machine."""
    return str(url or "").lower().startswith("https://") or _is_loopback_url(url)


_warned_unsafe: set = set()


def app_token() -> str:
    """The desktop app's current sign-in token (Cognito / CloudBase)."""
    try:
        from app_context import AppContext
        mw = AppContext.get_main_window()
        am = getattr(mw, "auth_manager", None)
        if am is None or not getattr(am, "signed_in", False):
            return ""
        # CN: the 30-day eCan session token, the account key the CN backend uses.
        if getattr(am, "_is_cn", False):
            get_session = getattr(am, "_get_wechat_session_token", None)
            if callable(get_session):
                ok, session = get_session()
                if ok and session:
                    return session
        best = getattr(am, "_get_best_id_token", None)
        tok = best() if callable(best) else None
        if not tok:
            tokens = am.get_tokens() or {}
            tok = tokens.get("id_token") or tokens.get("IdToken") or tokens.get("access_token") or ""
        return tok or ""
    except Exception:
        return ""


# ---- routing ---------------------------------------------------------------------------
class PlaneRouter:
    def __init__(self, local_service, connections: ConnectionStore,
                 client_factory: Optional[Callable[[Dict[str, Any]], RemoteKS]] = None,
                 lan_source: Optional[Callable[[], Any]] = None):
        self.local = local_service
        self.connections = connections
        self.lan_source = lan_source
        self.client_factory = client_factory or self._default_client
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ks-plane")

    def all_connections(self) -> List[Dict[str, Any]]:
        """Saved servers, plus the commander when this platoon is paired with it."""
        conns = list(self.connections.list())
        src = self.lan_source() if self.lan_source else None
        if src is not None and src.use_commander():
            conns.append({"id": "lan-commander", "name": src.get().get("commander") or "Commander", "plane": "lan",
                          "base_url": src.url(), "tenant_id": "commander", "auth": "lan", "enabled": True,
                          "verify_tls": True, "send_queries": True})
        return conns

    def _default_client(self, conn: Dict[str, Any]) -> RemoteKS:
        if conn.get("auth") == "lan":
            src = self.lan_source()
            return RemoteKS(conn["base_url"], src.token, conn["tenant_id"])
        if conn["auth"] == "local":
            token_fn = lambda: self.connections.token(conn["id"])
        elif _token_safe_url(conn["base_url"]):
            token_fn = app_token
        else:
            # A connection saved before the https rule: never send the account
            # token in cleartext (anyone on the network could replay it).
            if conn["id"] not in _warned_unsafe:
                _warned_unsafe.add(conn["id"])
                logger.warning(f"[KS] connection {conn.get('name')!r} is plain http; the app sign-in token "
                               f"is not sent to it -- use the server's own key or https")
            token_fn = lambda: ""
        return RemoteKS(conn["base_url"], token_fn, conn["tenant_id"], verify_tls=conn.get("verify_tls", True))

    def search(self, query: str, store: str = "", platform_item_id: str = "", product_id: str = "",
               include_local: bool = True, timeout_s: float = 8.0) -> Dict[str, Any]:
        """Fan out to the local service and enabled connections; pick the best answer."""
        t0 = time.perf_counter()
        jobs = {}
        if include_local:
            jobs["local"] = self._pool.submit(self._local_search, query, store, platform_item_id, product_id)
        conns = [c for c in self.all_connections() if c.get("enabled", True) and c.get("send_queries", True)]
        for conn in conns:
            client = self.client_factory(conn)
            jobs[conn["id"]] = self._pool.submit(client.search, query, store, platform_item_id, product_id)
        results, errors = [], []
        deadline = time.perf_counter() + timeout_s     # one budget for all planes, not N x timeout_s
        for key, fut in jobs.items():
            conn = next((c for c in conns if c["id"] == key), None)
            plane = conn["plane"] if conn else "local"
            try:
                r = fut.result(timeout=max(0.0, deadline - time.perf_counter()))
            except Exception as e:
                errors.append({"source": conn["name"] if conn else "local", "plane": plane, "error": str(e)})
                logger.warning(f"[KS] plane {plane} ({key}) search failed: {e}")
                continue
            if r is None:
                continue
            r["plane"] = plane
            r["source"] = conn["name"] if conn else "local"
            if plane == "private":
                r["sensitivity"] = "private"  # anything from on-prem stays on private models
            results.append(r)
        answering = [r for r in results if r.get("should_answer")]
        best = max(answering, key=lambda r: r.get("confidence", 0.0)) if answering else None
        if best is None and results:
            best = max(results, key=lambda r: r.get("confidence", 0.0))
        out = dict(best) if best else {"should_answer": False, "confidence": 0.0, "context": "", "reason": "no_results"}
        used = [best] if best else []
        out["sensitivity"] = most_sensitive(r.get("sensitivity", "internal") for r in used)
        out["planes"] = [{"source": r["source"], "plane": r["plane"], "confidence": r.get("confidence"),
                          "should_answer": r.get("should_answer"), "tier": r.get("tier")} for r in results]
        out["plane_errors"] = errors
        out["router_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return out

    def _local_search(self, query, store, platform_item_id, product_id):
        stats = self.local.store.stats(self.local.tenant_id())
        if not (stats["products"] or stats["policies"]):
            return None
        return self.local.search(query, store_ref=store, platform_item_id=platform_item_id, product_id=product_id)


class RemoteAdmin:
    """Access administration on a KS server, same shapes as the local service."""

    def __init__(self, remote: RemoteKS):
        self.r = remote

    def _t(self, path: str = "") -> str:
        return f"/v1/tenants/{self.r.tenant_id}{path}"

    def access_view(self):
        return self.r._request("GET", self._t("/access"))

    def save_member(self, email, role="viewer", status=None, member_id=None, display_name=""):
        return self.r._request("POST", self._t("/members"), json={
            "email": email, "role": role, "status": status, "member_id": member_id, "display_name": display_name})

    def remove_member(self, member_id):
        return self.r._request("DELETE", self._t(f"/members/{member_id}"))

    def save_group(self, name, member_ids, description="", group_id=None):
        return self.r._request("POST", self._t("/groups"), json={
            "name": name, "member_ids": member_ids, "description": description, "group_id": group_id})

    def delete_group(self, group_id):
        return self.r._request("DELETE", self._t(f"/groups/{group_id}"))

    def set_grant(self, kb_id, principal_type, principal_id, permission):
        return self.r._request("POST", self._t("/grants"), json={
            "kb_id": kb_id, "principal_type": principal_type, "principal_id": principal_id, "permission": permission})

    def remove_grant(self, grant_id):
        return self.r._request("DELETE", self._t(f"/grants/{grant_id}"))

    def update_kb(self, kb_id, **fields):
        return self.r._request("PATCH", self._t(f"/kbs/{kb_id}"), json=fields)

    def list_audit(self, limit=100):
        return self.r._request("GET", self._t(f"/audit?limit={int(limit)}"))
