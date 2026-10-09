"""
LAN knowledge sharing: one commander machine serves knowledge to the
merchant's platoon machines on the same network.

  commander  LightRAG stays on 127.0.0.1. A small gateway (default port 9630)
             is the only thing exposed on the LAN. It requires a per-device
             token for everything except /v1/lan/info and pairing.
  platoon    pairs once with a 6-digit code shown on the commander, then sends
             its LightRAG queries and product-knowledge searches to the
             gateway instead of its own empty local stores.

Pairing codes live 10 minutes, are single-use, and the gateway locks pairing
for a minute after 5 wrong codes, so a 6-digit code can't be brute-forced.
Device tokens are random 256-bit values; only their SHA-256 is stored, and
each device can be revoked on the commander. Platoons get read access only:
knowledge is managed on the commander.
"""
import hashlib
import hmac
import json
import os
import secrets
import socket
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from knowledge.ks._log import logger

DEFAULT_PORT = 9630
CODE_TTL_S = 600
MAX_BAD_CODES = 5
LOCKOUT_S = 60

# LightRAG routes a platoon may use through the gateway (read-only).
LIGHTRAG_READ_ROUTES = (
    ("POST", "/query"), ("POST", "/query/stream"), ("POST", "/query/data"),
    ("GET", "/graphs"), ("GET", "/graph/label/list"), ("GET", "/graph/label/popular"),
    ("GET", "/graph/label/search"), ("GET", "/health"), ("GET", "/documents/pipeline_status"),
    ("POST", "/documents/paginated"), ("GET", "/documents/status_counts"),
)


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def lan_addresses() -> List[str]:
    """This machine's private IPv4 addresses (what platoons can reach)."""
    try:
        from agent.fleet.lan import private_addrs
        addrs = private_addrs()
        if addrs:
            return addrs
    except Exception:
        pass
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        out.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return out


# ---- commander side -----------------------------------------------------------------
class LanAccess:
    """Paired devices and pairing codes on the commander."""

    def __init__(self, folder: str):
        self.folder = folder
        self.config_path = os.path.join(folder, "lan_share.json")
        self.devices_path = os.path.join(folder, "lan_devices.json")
        self._lock = threading.Lock()
        self._codes: Dict[str, float] = {}
        self._bad: List[float] = []

    # config ----------------------------------------------------------------------
    def config(self) -> Dict[str, Any]:
        cfg = _read_json(self.config_path, {})
        return {"enabled": bool(cfg.get("enabled", False)), "port": int(cfg.get("port", DEFAULT_PORT))}

    def set_config(self, enabled: Optional[bool] = None, port: Optional[int] = None) -> Dict[str, Any]:
        cfg = self.config()
        if enabled is not None:
            cfg["enabled"] = bool(enabled)
        if port is not None:
            if not (1024 <= int(port) <= 65535):
                raise ValueError("port must be between 1024 and 65535")
            cfg["port"] = int(port)
        _write_json(self.config_path, cfg)
        return cfg

    # pairing -------------------------------------------------------------------------
    def new_code(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            self._codes = {c: exp for c, exp in self._codes.items() if exp > now}
            code = f"{secrets.randbelow(1_000_000):06d}"
            self._codes[code] = now + CODE_TTL_S
            return {"code": code, "expires_in": CODE_TTL_S}

    def redeem(self, code: str, device_name: str, ip: str = "") -> str:
        """Exchange a pairing code for a long-lived device token."""
        with self._lock:
            now = time.time()
            self._bad = [t for t in self._bad if now - t < LOCKOUT_S]
            if len(self._bad) >= MAX_BAD_CODES:
                raise PermissionError("too many wrong codes; wait a minute and create a new code")
            code = (code or "").strip()
            exp = self._codes.get(code)
            if not exp or exp < now:
                self._bad.append(now)
                raise PermissionError("wrong or expired pairing code")
            del self._codes[code]
            token = secrets.token_urlsafe(32)
            devices = _read_json(self.devices_path, [])
            devices.append({"id": f"dv_{uuid.uuid4().hex[:10]}", "name": (device_name or "platoon")[:80],
                            "ip": ip, "token_sha256": _sha(token), "paired_at": int(now), "last_seen": int(now)})
            _write_json(self.devices_path, devices)
            return token

    # devices ---------------------------------------------------------------------------
    def devices(self) -> List[Dict[str, Any]]:
        return [{k: v for k, v in d.items() if k != "token_sha256"} for d in _read_json(self.devices_path, [])]

    def verify(self, token: str, ip: str = "") -> Optional[Dict[str, Any]]:
        if not token:
            return None
        digest = _sha(token)
        with self._lock:
            devices = _read_json(self.devices_path, [])
            for d in devices:
                if hmac.compare_digest(d.get("token_sha256", ""), digest):
                    now = int(time.time())
                    if now - d.get("last_seen", 0) > 60 or (ip and d.get("ip") != ip):
                        d["last_seen"], d["ip"] = now, ip or d.get("ip", "")
                        _write_json(self.devices_path, devices)
                    return {k: v for k, v in d.items() if k != "token_sha256"}
        return None

    def revoke(self, device_id: str) -> None:
        with self._lock:
            _write_json(self.devices_path, [d for d in _read_json(self.devices_path, []) if d["id"] != device_id])


def create_gateway_app(service, access: LanAccess, lightrag_base: Any, lightrag_key: Any, machine_name: str = ""):
    """FastAPI app the commander exposes on the LAN.

    ``lightrag_base`` / ``lightrag_key`` are callables (the local LightRAG
    server may restart on another port with the same key).
    """
    from fastapi import FastAPI, Header, HTTPException, Request
    from fastapi.responses import JSONResponse, Response, StreamingResponse

    from pydantic import BaseModel

    # FastAPI resolves these at runtime; this module deliberately has no
    # postponed annotations so locally imported types (Request, Header) work.
    class PairBody(BaseModel):
        code: str
        device_name: str = ""

    class SearchBody(BaseModel):
        query: str
        store: str = ""
        platform_item_id: str = ""
        product_id: str = ""
        k: int = 5

    app = FastAPI(title="eCan LAN knowledge gateway")

    def device(request: Request, authorization: str) -> Dict[str, Any]:
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        d = access.verify(token, request.client.host if request.client else "")
        if d is None:
            raise HTTPException(401, "this machine is not paired with the commander")
        return d

    @app.get("/v1/lan/info")
    def info():
        return {"service": "ecan-lan-knowledge", "machine": machine_name or socket.gethostname(), "pairing": True}

    @app.get("/v1/health")
    def health():
        return {"status": "ok", "plane": "lan", "embedder": service.embedder.id}

    @app.post("/v1/lan/pair")
    def pair(body: PairBody, request: Request):
        try:
            token = access.redeem(body.code, body.device_name, request.client.host if request.client else "")
        except PermissionError as e:
            return JSONResponse({"error": "forbidden", "message": str(e)}, status_code=403)
        return {"token": token}

    @app.get("/v1/me")
    def me(request: Request, authorization: str = Header(default="")):
        d = device(request, authorization)
        t = service.default_tenant()
        return {"principal": {"user_id": f"lan:{d['id']}", "email": "", "name": d["name"]},
                "tenants": [{**t, "role": "viewer"}], "plane": "lan"}

    # Product knowledge (read-only). Any tenant id maps to the commander's own.
    @app.post("/v1/tenants/{tid}/search")
    def search(tid: str, body: SearchBody, request: Request, authorization: str = Header(default="")):
        device(request, authorization)
        r = service.search(body.query, store_ref=body.store, platform_item_id=body.platform_item_id,
                           product_id=body.product_id, k=body.k)
        r["plane"] = "lan"
        return r

    @app.get("/v1/tenants/{tid}/overview")
    def overview(tid: str, request: Request, authorization: str = Header(default="")):
        device(request, authorization)
        return service.overview()

    @app.get("/v1/tenants/{tid}/products")
    def products(tid: str, request: Request, q: str = "", category: str = "", store_id: str = "",
                 offset: int = 0, limit: int = 50, authorization: str = Header(default="")):
        device(request, authorization)
        return service.list_products(q=q, category=category, store_id=store_id, offset=offset, limit=min(limit, 200))

    @app.get("/v1/tenants/{tid}/policies")
    def policies(tid: str, request: Request, authorization: str = Header(default="")):
        device(request, authorization)
        return service.policies_view()

    # LightRAG documents (read-only routes), proxied to the commander's loopback server.
    @app.api_route("/lightrag/{path:path}", methods=["GET", "POST"])
    async def lightrag_proxy(path: str, request: Request, authorization: str = Header(default="")):
        device(request, authorization)
        route = "/" + path
        if (request.method, route) not in LIGHTRAG_READ_ROUTES:
            raise HTTPException(403, f"{request.method} {route} is not available to LAN machines")
        import httpx
        headers = {"X-API-Key": lightrag_key() or "", "Content-Type": request.headers.get("content-type", "application/json")}
        ws = request.headers.get("lightrag-workspace")
        if ws:
            headers["LIGHTRAG-WORKSPACE"] = ws
        url = f"{lightrag_base().rstrip('/')}{route}"
        body = await request.body()
        params = dict(request.query_params)
        if route.endswith("/stream"):
            client = httpx.AsyncClient(timeout=None)
            upstream = await client.send(client.build_request(request.method, url, headers=headers, content=body,
                                                              params=params), stream=True)

            async def relay():
                try:
                    async for chunk in upstream.aiter_raw():
                        yield chunk
                finally:
                    await upstream.aclose()
                    await client.aclose()
            return StreamingResponse(relay(), status_code=upstream.status_code,
                                     media_type=upstream.headers.get("content-type", "application/x-ndjson"))
        async with httpx.AsyncClient(timeout=120) as client:
            up = await client.request(request.method, url, headers=headers, content=body, params=params)
        return Response(content=up.content, status_code=up.status_code,
                        media_type=up.headers.get("content-type", "application/json"))

    return app


class GatewayRunner:
    """Runs the gateway with uvicorn in a background thread."""

    def __init__(self):
        self._server = None
        self._thread: Optional[threading.Thread] = None
        self.port: Optional[int] = None
        self.error: str = ""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, app, port: int, host: str = "0.0.0.0") -> None:
        import uvicorn
        self.stop()
        self.error = ""
        config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
        self._server = uvicorn.Server(config)
        self.port = port

        def _run():
            try:
                self._server.run()
            except BaseException as e:  # uvicorn exits via SystemExit when the port is taken
                self.error = f"cannot listen on port {port}: {e}"
                logger.warning(f"[KS-LAN] gateway stopped: {self.error}")

        self._thread = threading.Thread(target=_run, name="ks-lan-gateway", daemon=True)
        self._thread.start()
        for _ in range(50):
            if getattr(self._server, "started", False) or not self._thread.is_alive():
                break
            time.sleep(0.05)
        if not getattr(self._server, "started", False) and not self.error:
            self.error = f"gateway did not start on port {port}"

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server, self._thread = None, None


# ---- platoon side ----------------------------------------------------------------------
class LanSource:
    """Which knowledge a platoon machine uses: its own, or the commander's."""

    def __init__(self, folder: str):
        self.path = os.path.join(folder, "lan_source.json")

    def get(self) -> Dict[str, Any]:
        d = _read_json(self.path, {})
        return {"mode": d.get("mode", "local"), "url": d.get("url", ""), "commander": d.get("commander", ""),
                "paired": bool(d.get("token"))}

    def token(self) -> str:
        return _read_json(self.path, {}).get("token", "")

    def use_commander(self) -> bool:
        d = _read_json(self.path, {})
        return d.get("mode") == "commander" and bool(d.get("url")) and bool(d.get("token"))

    def url(self) -> str:
        return _read_json(self.path, {}).get("url", "")

    def pair(self, url: str, code: str, device_name: str, commander: str = "") -> Dict[str, Any]:
        import httpx
        url = url.strip().rstrip("/")
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"http://{url}"
        if url.count(":") < 2:  # no port given
            url = f"{url}:{DEFAULT_PORT}"
        with httpx.Client(timeout=8) as c:
            r = c.post(f"{url}/v1/lan/pair", json={"code": code, "device_name": device_name})
        if r.status_code != 200:
            try:
                msg = r.json().get("message") or r.text
            except Exception:
                msg = r.text
            raise PermissionError(msg)
        _write_json(self.path, {"mode": "commander", "url": url, "token": r.json()["token"], "commander": commander})
        return self.get()

    def set_mode(self, mode: str) -> Dict[str, Any]:
        if mode not in ("local", "commander"):
            raise ValueError("mode must be local or commander")
        d = _read_json(self.path, {})
        if mode == "commander" and not d.get("token"):
            raise ValueError("pair with the commander first")
        d["mode"] = mode
        _write_json(self.path, d)
        return self.get()

    def forget(self) -> None:
        _write_json(self.path, {"mode": "local"})


def discover_commanders(timeout_s: float = 1.5) -> List[Dict[str, Any]]:
    """Commanders seen by LAN discovery that answer on the gateway port."""
    import httpx
    found = []
    try:
        from agent.a2a.discovery.directory import get_directory
        nodes = [n for n in get_directory().list_nodes() if "commander" in (n.role or "").lower() and n.lan_host]
    except Exception:
        nodes = []
    for n in nodes:
        url = f"http://{n.lan_host}:{DEFAULT_PORT}"
        entry = {"machine_name": n.machine_name, "host": n.lan_host, "url": url, "sharing": False}
        try:
            with httpx.Client(timeout=timeout_s) as c:
                entry["sharing"] = c.get(f"{url}/v1/lan/info").status_code == 200
        except Exception:
            pass
        found.append(entry)
    return found
