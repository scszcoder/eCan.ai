"""
Knowledge Service HTTP server: one deployment per plane.

- Private plane: runs on the customer's own server next to vLLM / TEI.
  Knowledge stays in-house; desktop and web apps connect over HTTPS.
- Public plane: runs in our cloud (multi-tenant, merchants).

Every request (except /v1/health and local login) needs a bearer token that
this server verifies itself (identity.py); permissions come from authz.py.

Configuration (environment):
  KS_DB_URL               SQLAlchemy URL (sqlite:///... or postgresql+psycopg://...)
  KS_PLANE                private | public            (reported to clients; tags results)
  KS_DATA_DIR             uploads and JWKS cache        (default ./ks_data)
  KS_COGNITO_REGION / KS_COGNITO_POOL_ID / KS_COGNITO_CLIENT_ID   accept Cognito tokens
  KS_OIDC_ISSUER / KS_OIDC_AUDIENCE / KS_OIDC_JWKS_URL            accept an OIDC provider
                                                                   (CloudBase, Azure AD, Keycloak...)
  KS_LOCAL_SECRET         enables local accounts (signing secret)
  KS_BOOTSTRAP_ADMIN      email:password of the first owner (local login), on-prem bootstrap
  KS_BOOTSTRAP_TENANT     name of the tenant created for the bootstrap admin
  KS_ALLOW_TENANT_CREATE  1 = signed-in users may create their own tenant (public plane)
  KS_EMBED_BASE_URL / KS_EMBED_MODEL / KS_EMBED_API_KEY           OpenAI-compatible embeddings
                                                                   (default: offline hashing)

Run:  python -m knowledge.ks.server --host 0.0.0.0 --port 8790
"""
from __future__ import annotations

import hmac
import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from knowledge.ks.authz import PermissionDenied
from knowledge.ks.embedding import HashingEmbedder, OpenAICompatibleEmbedder
from knowledge.ks.identity import AuthError, IdentityRegistry, JWKSVerifier, LocalVerifier, Principal
from knowledge.ks.models import new_id
from knowledge.ks.service import KnowledgeService

API = "/v1"
UPLOAD_EXTS = {".csv", ".tsv", ".xlsx", ".json", ".pdf", ".docx", ".txt", ".md"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class ServerConfig(BaseModel):
    db_url: str = "sqlite:///ks_server.db"
    plane: str = "private"
    data_dir: str = "ks_data"
    allow_tenant_create: bool = False
    bootstrap_admin: str = ""
    bootstrap_tenant: str = "我的企业"

    @classmethod
    def from_env(cls) -> "ServerConfig":
        return cls(
            db_url=os.getenv("KS_DB_URL", "sqlite:///ks_server.db"),
            plane=os.getenv("KS_PLANE", "private"),
            data_dir=os.getenv("KS_DATA_DIR", "ks_data"),
            allow_tenant_create=os.getenv("KS_ALLOW_TENANT_CREATE", "0") in ("1", "true", "yes"),
            bootstrap_admin=os.getenv("KS_BOOTSTRAP_ADMIN", ""),
            bootstrap_tenant=os.getenv("KS_BOOTSTRAP_TENANT", "我的企业"),
        )


def registry_from_env(data_dir: str) -> tuple:
    reg = IdentityRegistry()
    local = None
    if os.getenv("KS_COGNITO_POOL_ID"):
        reg.add(JWKSVerifier.cognito(os.getenv("KS_COGNITO_REGION", "us-east-1"), os.environ["KS_COGNITO_POOL_ID"],
                                     os.getenv("KS_COGNITO_CLIENT_ID"), cache_dir=data_dir))
    if os.getenv("KS_OIDC_ISSUER"):
        reg.add(JWKSVerifier("oidc", os.environ["KS_OIDC_ISSUER"], jwks_url=os.getenv("KS_OIDC_JWKS_URL"),
                             audience=os.getenv("KS_OIDC_AUDIENCE"),
                             cache_path=os.path.join(data_dir, "jwks_oidc.json")))
    if os.getenv("KS_LOCAL_SECRET") or os.getenv("KS_BOOTSTRAP_ADMIN"):
        local = LocalVerifier(secret=os.getenv("KS_LOCAL_SECRET") or None)
        reg.add(local)
    return reg, local


def embedder_from_env():
    if os.getenv("KS_EMBED_BASE_URL") and os.getenv("KS_EMBED_MODEL"):
        return OpenAICompatibleEmbedder(os.environ["KS_EMBED_BASE_URL"], os.environ["KS_EMBED_MODEL"],
                                        os.getenv("KS_EMBED_API_KEY", ""))
    return HashingEmbedder()


# ---- request bodies -------------------------------------------------------------------
class SearchBody(BaseModel):
    query: str
    store: str = ""
    platform_item_id: str = ""
    product_id: str = ""
    k: int = 5


class TenantBody(BaseModel):
    name: str
    kind: str = "merchant"


class StoreBody(BaseModel):
    id: Optional[str] = None
    name: str
    platform: str = ""
    platform_store_id: str = ""
    ecan_store_id: str = ""


class PolicyBody(BaseModel):
    topic: str
    text: str
    store_id: Optional[str] = None
    title: str = ""


class MemberBody(BaseModel):
    email: str = ""
    role: str = "viewer"
    status: Optional[str] = None
    member_id: Optional[str] = None
    display_name: str = ""


class GroupBody(BaseModel):
    name: str
    member_ids: List[str] = []
    description: str = ""
    group_id: Optional[str] = None


class GrantBody(BaseModel):
    kb_id: str
    principal_type: str
    principal_id: str
    permission: str = "read"


class KbBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    plane: Optional[str] = None
    sensitivity: Optional[str] = None


class LocalLogin(BaseModel):
    email: str
    password: str


def create_app(service: KnowledgeService, registry: IdentityRegistry, config: ServerConfig,
               local: Optional[LocalVerifier] = None) -> FastAPI:
    app = FastAPI(title="eCan Knowledge Service", version="1")
    os.makedirs(config.data_dir, exist_ok=True)

    # On-prem bootstrap: the first owner signs in with a local account.
    boot_email, _, boot_password = config.bootstrap_admin.partition(":")
    boot_email = boot_email.strip().lower()
    if boot_email and boot_password:
        tenants = service.authz.tenants_for(Principal(user_id=boot_email, email=boot_email))
        if not tenants:
            t = service.store.ensure_tenant(config.bootstrap_tenant, "enterprise", tenant_id=new_id("tn"))
            service.catalog_kb(t["id"])
            service.store.update_kb(service.catalog_kb(t["id"])["id"], plane=config.plane)
            service.members.ensure_owner(t["id"], boot_email, boot_email, "admin")

    @app.exception_handler(AuthError)
    async def _auth(_: Request, e: AuthError):
        return JSONResponse({"error": "unauthenticated", "message": str(e)}, status_code=401)

    @app.exception_handler(PermissionDenied)
    async def _denied(_: Request, e: PermissionDenied):
        return JSONResponse({"error": "forbidden", "message": str(e)}, status_code=403)

    @app.exception_handler(ValueError)
    async def _bad(_: Request, e: ValueError):
        return JSONResponse({"error": "invalid", "message": str(e)}, status_code=400)

    def principal(authorization: str = Header(default=""), x_ecan_agent: str = Header(default=""),
                  x_ecan_store: str = Header(default="")) -> Principal:
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        p = registry.verify(token)
        # An agent acting for this user / store identifies itself; it never
        # gains more than the user plus the agent's / store's own grants.
        p.agent_id, p.store_id = x_ecan_agent.strip(), x_ecan_store.strip()
        return p

    def tenant_for(tid: str, p: Principal) -> str:
        if not service.store.get_tenant(tid):
            raise HTTPException(404, "tenant not found")
        service.authz.link_user(p, tid)  # invited email / domain auto-join on first use
        return tid

    @app.get(f"{API}/health")
    def health():
        return {"status": "ok", "plane": config.plane, "embedder": service.embedder.id}

    @app.post(f"{API}/auth/local")
    def local_login(body: LocalLogin):
        if not (local and boot_email and boot_password):
            raise HTTPException(404, "local accounts are not enabled on this server")
        ok_user = hmac.compare_digest(body.email.strip().lower(), boot_email)
        ok_pass = hmac.compare_digest(body.password, boot_password)
        if not (ok_user and ok_pass):
            raise AuthError("wrong email or password")
        return {"access_token": local.issue(boot_email, boot_email, "admin"), "token_type": "bearer"}

    @app.get(f"{API}/me")
    def me(p: Principal = Depends(principal)):
        tenants = []
        for tid in service.authz.tenants_for(p):
            m = service.authz.membership(p, tid)
            t = service.store.get_tenant(tid)
            if t and m:
                tenants.append({**t, "role": m.role})
        return {"principal": p.to_dict(), "tenants": tenants, "plane": config.plane}

    @app.post(f"{API}/tenants")
    def create_tenant(body: TenantBody, p: Principal = Depends(principal)):
        if not config.allow_tenant_create:
            raise PermissionDenied("tenant creation is disabled on this server")
        t = service.store.ensure_tenant(body.name.strip() or "未命名", body.kind, tenant_id=new_id("tn"))
        kb = service.catalog_kb(t["id"])
        service.store.update_kb(kb["id"], plane=config.plane)
        service.members.ensure_owner(t["id"], p.user_id, p.email_lc, p.name)
        service.store.audit(p.user_id, "tenant.create", t["id"], {"name": t["name"]})
        return t

    T = API + "/tenants/{tid}"

    @app.get(T + "/overview")
    def overview(tid: str, p: Principal = Depends(principal)):
        return service.overview(tenant_for(tid, p), principal=p)

    @app.post(T + "/search")
    def search(tid: str, body: SearchBody, p: Principal = Depends(principal)):
        r = service.search(body.query, store_ref=body.store, platform_item_id=body.platform_item_id,
                           product_id=body.product_id, tenant_id=tenant_for(tid, p), k=body.k, principal=p)
        r["plane"] = config.plane
        return r

    @app.get(T + "/products")
    def products(tid: str, q: str = "", category: str = "", store_id: str = "", offset: int = 0, limit: int = 50,
                 p: Principal = Depends(principal)):
        return service.list_products(tenant_for(tid, p), principal=p, q=q, category=category, store_id=store_id,
                                     offset=offset, limit=min(limit, 200))

    @app.get(T + "/products/{pid}")
    def get_product(tid: str, pid: str, p: Principal = Depends(principal)):
        prod = service.get_product(pid, principal=p)
        if not prod or prod["tenant_id"] != tid:
            raise HTTPException(404, "product not found")
        return prod

    @app.post(T + "/products")
    def save_product(tid: str, body: Dict[str, Any], p: Principal = Depends(principal)):
        return service.save_product(body, tenant_id=tenant_for(tid, p), principal=p)

    @app.delete(T + "/products/{pid}")
    def delete_product(tid: str, pid: str, p: Principal = Depends(principal)):
        prod = service.store.get_product(pid)
        if not prod or prod["tenant_id"] != tid:
            raise HTTPException(404, "product not found")
        service.delete_product(pid, principal=p)
        return {"deleted": pid}

    @app.post(T + "/stores")
    def save_store(tid: str, body: StoreBody, p: Principal = Depends(principal)):
        return service.save_store(body.model_dump(), tenant_id=tenant_for(tid, p), principal=p)

    @app.delete(T + "/stores/{sid}")
    def delete_store(tid: str, sid: str, p: Principal = Depends(principal)):
        st = service.store.get_store(sid)
        if not st or st["tenant_id"] != tid:
            raise HTTPException(404, "store not found")
        service.delete_store(sid, principal=p)
        return {"deleted": sid}

    @app.get(T + "/policies")
    def policies(tid: str, p: Principal = Depends(principal)):
        return service.policies_view(tenant_for(tid, p), principal=p)

    @app.post(T + "/policies")
    def save_policy(tid: str, body: PolicyBody, p: Principal = Depends(principal)):
        return service.save_policy(body.topic, body.text, body.store_id, body.title, tenant_id=tenant_for(tid, p),
                                   principal=p)

    def _save_upload(tid: str, upload: UploadFile) -> str:
        ext = os.path.splitext(upload.filename or "")[1].lower()
        if ext not in UPLOAD_EXTS:
            raise ValueError(f"unsupported file type {ext}")
        folder = os.path.join(config.data_dir, "uploads", tid)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{uuid.uuid4().hex}{ext}")
        size = 0
        with open(path, "wb") as f:
            while True:
                block = upload.file.read(1 << 20)
                if not block:
                    break
                size += len(block)
                if size > MAX_UPLOAD_BYTES:
                    f.close()
                    os.remove(path)
                    raise ValueError("file too large (max 50 MB)")
                f.write(block)
        return path

    @app.post(T + "/catalog/preview")
    def catalog_preview(tid: str, file: UploadFile = File(...), p: Principal = Depends(principal)):
        tid = tenant_for(tid, p)
        service._check(p, tid, "write")
        path = _save_upload(tid, file)
        out = service.preview_catalog(path)
        out["upload_id"] = os.path.basename(path)
        out.pop("path", None)
        return out

    @app.post(T + "/catalog/import")
    def catalog_import(tid: str, upload_id: str = Form(...), mapping: str = Form(...),
                       default_store_id: str = Form(""), p: Principal = Depends(principal)):
        import json
        tid = tenant_for(tid, p)
        path = os.path.join(config.data_dir, "uploads", tid, os.path.basename(upload_id))
        if not os.path.exists(path):
            raise HTTPException(404, "upload not found; preview the file first")
        return service.import_catalog(path, json.loads(mapping), default_store_id, tenant_id=tid, principal=p)

    @app.get(API + "/jobs/{job_id}")
    def job(job_id: str, p: Principal = Depends(principal)):
        j = service.get_job(job_id, principal=p)
        if not j:
            raise HTTPException(404, "job not found")
        return j

    @app.post(T + "/reindex")
    def reindex(tid: str, p: Principal = Depends(principal)):
        return service.reindex(tenant_for(tid, p), principal=p)

    # ---- access administration ------------------------------------------------------
    @app.get(T + "/access")
    def access(tid: str, p: Principal = Depends(principal)):
        return service.access_view(tenant_for(tid, p), principal=p)

    @app.post(T + "/members")
    def save_member(tid: str, body: MemberBody, p: Principal = Depends(principal)):
        return service.save_member(body.email, body.role, body.status, body.member_id, body.display_name,
                                   tenant_id=tenant_for(tid, p), principal=p)

    @app.delete(T + "/members/{mid}")
    def remove_member(tid: str, mid: str, p: Principal = Depends(principal)):
        service.remove_member(mid, tenant_id=tenant_for(tid, p), principal=p)
        return {"deleted": mid}

    @app.post(T + "/groups")
    def save_group(tid: str, body: GroupBody, p: Principal = Depends(principal)):
        return service.save_group(body.name, body.member_ids, body.description, body.group_id,
                                  tenant_id=tenant_for(tid, p), principal=p)

    @app.delete(T + "/groups/{gid}")
    def delete_group(tid: str, gid: str, p: Principal = Depends(principal)):
        service.delete_group(gid, tenant_id=tenant_for(tid, p), principal=p)
        return {"deleted": gid}

    @app.post(T + "/grants")
    def set_grant(tid: str, body: GrantBody, p: Principal = Depends(principal)):
        return service.set_grant(body.kb_id, body.principal_type, body.principal_id, body.permission,
                                 tenant_id=tenant_for(tid, p), principal=p)

    @app.delete(T + "/grants/{gid}")
    def remove_grant(tid: str, gid: str, p: Principal = Depends(principal)):
        service.remove_grant(gid, tenant_id=tenant_for(tid, p), principal=p)
        return {"deleted": gid}

    @app.patch(T + "/kbs/{kb_id}")
    def update_kb(tid: str, kb_id: str, body: KbBody, p: Principal = Depends(principal)):
        return service.update_kb(kb_id, tenant_id=tenant_for(tid, p), principal=p,
                                 **{k: v for k, v in body.model_dump().items() if v is not None})

    @app.get(T + "/audit")
    def audit(tid: str, limit: int = 100, p: Principal = Depends(principal)):
        return service.list_audit(tenant_for(tid, p), min(limit, 500), principal=p)

    return app


def build_from_env() -> FastAPI:
    config = ServerConfig.from_env()
    os.makedirs(config.data_dir, exist_ok=True)
    registry, local = registry_from_env(config.data_dir)
    service = KnowledgeService(config.db_url, embedder=embedder_from_env(), owner="server")
    return create_app(service, registry, config, local)


def main() -> None:
    import argparse
    import uvicorn
    ap = argparse.ArgumentParser(description="eCan Knowledge Service server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8790)
    args = ap.parse_args()
    uvicorn.run(build_from_env(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
