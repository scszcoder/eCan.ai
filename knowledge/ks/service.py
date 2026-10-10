"""
KnowledgeService: the facade used by IPC handlers and agent tools.

Desktop: one service per signed-in user, SQLite under the user's data dir,
one merchant tenant created on first use. Servers construct it with a
PostgreSQL URL and pass tenant ids explicitly.
"""
from __future__ import annotations

import hashlib
import os
import threading
from typing import Any, Callable, Dict, List, Optional

from knowledge.ks import catalog_import, doc_extract
from knowledge.ks.authz import Authorizer, PermissionDenied
from knowledge.ks.chunking import document_chunks, embed_text, policy_chunks, product_chunks
from knowledge.ks.embedding import Embedder, HashingEmbedder
from knowledge.ks.identity import Principal, local_principal, subject_of
from knowledge.ks.index import IndexCache
from knowledge.ks.jobs import JobContext, JobRunner
from knowledge.ks.members import MemberAdmin
from knowledge.ks.retrieval import ProductRetriever
from knowledge.ks.store import KSStore
from knowledge.ks.text import POLICY_TOPIC_LABELS, POLICY_TOPICS, clean_text
from knowledge.ks._log import logger

DEFAULT_TENANT_NAME = "我的店铺"


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class KnowledgeService:
    def __init__(self, db_url: str, embedder: Optional[Embedder] = None, owner: str = "",
                 job_listener: Optional[Callable[[Dict[str, Any]], None]] = None,
                 db_schema: str = "", db_connect_args: Optional[Dict[str, Any]] = None):
        self.store = KSStore(db_url, schema=db_schema, connect_args=db_connect_args)
        self.embedder: Embedder = embedder or HashingEmbedder()
        self.owner = owner
        self.indexes = IndexCache(lambda tid: self.store.load_index(tid)[:2],
                                  version=self.store.index_version, bump=self.store.bump_index_version)
        self.retriever = ProductRetriever(self.store, self.indexes, self.embedder)
        self.jobs = JobRunner(self.store, [job_listener] if job_listener else [])
        self._tenant_lock = threading.Lock()
        self._default_tenant: Optional[Dict[str, Any]] = None
        self.authz = Authorizer(self.store)
        self.members = MemberAdmin(self.store)
        self.local = local_principal(owner)

    # ---- authorisation ------------------------------------------------------
    # principal=None means the trusted local caller (the desktop app acting
    # for its signed-in user on their own database). A server always passes
    # the verified principal of the request, and every rule applies.
    def _check(self, principal: Optional[Principal], tenant_id: str, permission: str = "read") -> None:
        if principal is None:
            return
        kb = self.catalog_kb(tenant_id)
        self.authz.require_kb(principal, tenant_id, kb["id"], permission)

    def _admin(self, principal: Optional[Principal], tenant_id: str) -> str:
        """Require tenant admin; returns the actor's role."""
        if principal is None:
            return "owner"
        return self.authz.require_role(principal, tenant_id, "admin").role

    def _actor(self, principal: Optional[Principal]) -> str:
        return (principal or self.local).user_id

    def _audit(self, principal: Optional[Principal], tenant_id: str, action: str, target: str = "",
               detail: Optional[dict] = None) -> None:
        actor = principal.user_id if principal is not None else (self.owner or "local")
        self.store.audit(actor, action, target, detail, tenant_id=tenant_id)

    # ---- tenant / KB --------------------------------------------------------
    def default_tenant(self) -> Dict[str, Any]:
        with self._tenant_lock:
            if self._default_tenant is None:
                t = self.store.ensure_tenant(DEFAULT_TENANT_NAME)
                self.store.ensure_kb(t["id"], "商品知识库", kind="catalog", owner=self.owner)
                self.members.ensure_owner(t["id"], self.local.user_id, self.local.email, self.local.name)
                self._default_tenant = t
            return self._default_tenant

    def tenant_id(self, tenant_id: Optional[str] = None) -> str:
        return tenant_id or self.default_tenant()["id"]

    def catalog_kb(self, tenant_id: str) -> Dict[str, Any]:
        return self.store.ensure_kb(tenant_id, "商品知识库", kind="catalog", owner=self.owner)

    def overview(self, tenant_id: Optional[str] = None, principal: Optional[Principal] = None) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
        self._check(principal, tid, "read")
        stats = self.store.stats(tid)
        stale = [e for e in stats["embedders"] if e and e != self.embedder.id]
        return {
            "tenant": self.store.get_tenant(tid),
            "kbs": self.store.list_kbs(tid),
            "stores": self.store.list_stores(tid),
            "stats": stats,
            "categories": self.store.categories(tid),
            "embedder": {"id": self.embedder.id,
                         "is_fallback": self.embedder.id.startswith("hashing"),
                         "needs_reindex": bool(stale), "stale_embedders": stale},
            "jobs": self.store.list_jobs(tid, limit=10),
        }

    # ---- embedding helpers ------------------------------------------------------
    def _tenant_owner(self, tenant_id: str) -> str:
        for m in self.members.list_members(tenant_id):
            if m["role"] == "owner" and m["status"] == "active":
                # Billing knows the provider's own subject, not our namespaced id.
                return subject_of(m["user_id"]) or m["email"]
        return tenant_id

    def _billing(self, tenant_id: str):
        from knowledge.ks.embedding import billing_owner
        return billing_owner.set(self._tenant_owner(tenant_id))

    def _embed_chunks(self, chunks: List[Dict[str, Any]], tenant_id: str = ""):
        if not chunks:
            return None
        from knowledge.ks.embedding import billing_owner
        token = self._billing(tenant_id) if tenant_id else None
        try:
            return self.embedder.embed([embed_text(c["doc_type"], c["text"], c.get("answer", "")) for c in chunks])
        finally:
            if token is not None:
                billing_owner.reset(token)

    def _index_product(self, product: Dict[str, Any]) -> int:
        chunks = product_chunks(product)
        n = self.store.replace_chunks(
            {"kb_id": product["kb_id"], "tenant_id": product["tenant_id"], "product_id": product["id"],
             "category": product.get("category", "")},
            chunks, self._embed_chunks(chunks, product["tenant_id"]), self.embedder.id)
        self.indexes.invalidate(product["tenant_id"])
        return n

    def _index_policy(self, policy: Dict[str, Any]) -> int:
        kb = self.catalog_kb(policy["tenant_id"])
        chunks = policy_chunks(policy["topic"], policy.get("title", ""), policy["text"])
        n = self.store.replace_chunks(
            {"kb_id": kb["id"], "tenant_id": policy["tenant_id"], "policy_id": policy["id"],
             "store_id": policy.get("store_id")},
            chunks, self._embed_chunks(chunks, policy["tenant_id"]), self.embedder.id)
        self.indexes.invalidate(policy["tenant_id"])
        return n

    # ---- stores -------------------------------------------------------------------
    def save_store(self, data: Dict[str, Any], tenant_id: Optional[str] = None,
                   principal: Optional[Principal] = None) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
        self._admin(principal, tid)
        name = clean_text(data.get("name"))
        if not name:
            raise ValueError("店铺名称不能为空 / store name is required")
        st = self.store.upsert_store(tid, name, data.get("platform", ""), data.get("id"),
                                     data.get("platform_store_id", ""), data.get("ecan_store_id", ""))
        self._audit(principal, tid, "store.save", st["id"], {"name": name})
        return st

    def delete_store(self, store_id: str, principal: Optional[Principal] = None) -> None:
        st = self.store.get_store(store_id)
        if st:
            self._admin(principal, st["tenant_id"])
        self.store.delete_store(store_id)
        if st:
            self.indexes.invalidate(st["tenant_id"])
        self._audit(principal, st["tenant_id"] if st else "", "store.delete", store_id)

    # ---- products -----------------------------------------------------------------
    def save_product(self, data: Dict[str, Any], tenant_id: Optional[str] = None,
                     principal: Optional[Principal] = None) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
        self._check(principal, tid, "write")
        if data.get("id"):
            existing = self.store.get_product(data["id"])
            if existing and existing["tenant_id"] != tid:
                raise PermissionDenied("product belongs to another tenant")
        if "listings" in data:
            self.store.stores_belong(tid, [l.get("store_id") for l in data.get("listings") or []])
        kb = self.catalog_kb(tid)
        rec = dict(data)
        rec["title"] = clean_text(rec.get("title"))
        rec["code"] = clean_text(rec.get("code")) or rec["title"]
        if not rec["title"]:
            raise ValueError("商品标题不能为空 / product title is required")
        rec.setdefault("source", "manual")
        product, changed = self.store.upsert_product(tid, kb["id"], rec)
        if "listings" in data:
            self.store.set_listings(product["id"], data.get("listings") or [])
        product = self.store.get_product(product["id"])
        if changed:
            self._index_product(product)
        self._audit(principal, tid, "product.save", product["id"], {"code": product["code"], "changed": changed})
        return product

    def get_product(self, product_id: str, principal: Optional[Principal] = None) -> Optional[Dict[str, Any]]:
        p = self.store.get_product(product_id)
        if p:
            self._check(principal, p["tenant_id"], "read")
            p["documents"] = self.store.list_documents(product_id)
        return p

    def delete_product(self, product_id: str, principal: Optional[Principal] = None) -> None:
        p = self.store.get_product(product_id)
        if p:
            self._check(principal, p["tenant_id"], "write")
        tid = self.store.delete_product(product_id)
        if tid:
            self.indexes.invalidate(tid)
        self._audit(principal, p["tenant_id"] if p else "", "product.delete", product_id)

    def list_products(self, tenant_id: Optional[str] = None, principal: Optional[Principal] = None,
                      **filters) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
        self._check(principal, tid, "read")
        return self.store.list_products(tid, **filters)

    # ---- catalog import -------------------------------------------------------------
    def preview_catalog(self, path: str) -> Dict[str, Any]:
        headers, rows = catalog_import.read_table(path)
        mapping = catalog_import.suggest_mapping(headers)
        products, report = catalog_import.build_products(rows, mapping)
        return {
            "path": path, "filename": os.path.basename(path), "headers": headers, "mapping": mapping,
            "fields": [{"value": f, "label": catalog_import.FIELD_LABELS[f]} for f in catalog_import.FIELDS],
            "rows_preview": catalog_import.preview_rows(rows), "report": report.to_dict(),
            "products_preview": products[:5],
            "stores_in_file": sorted({l["store"] for p in products for l in p["listings"] if l.get("store")}),
        }

    def recheck_catalog(self, path: str, mapping: Dict[str, str]) -> Dict[str, Any]:
        headers, rows = catalog_import.read_table(path)
        products, report = catalog_import.build_products(rows, mapping)
        return {"report": report.to_dict(), "products_preview": products[:5]}

    def import_catalog(self, path: str, mapping: Dict[str, str], default_store_id: str = "",
                       tenant_id: Optional[str] = None, run_inline: bool = False,
                       principal: Optional[Principal] = None) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
        self._check(principal, tid, "write")
        self.store.stores_belong(tid, [default_store_id])

        def work(ctx: JobContext) -> Dict[str, Any]:
            ctx.progress("parse", 0, 1, "读取文件 / reading file", force=True)
            headers, rows = catalog_import.read_table(path)
            ctx.progress("clean", 0, len(rows), f"清洗 {len(rows)} 行 / cleaning rows", force=True)
            products, report = catalog_import.build_products(rows, mapping)
            if report.errors:
                raise ValueError("; ".join(report.errors))
            store_ids: Dict[str, str] = {}
            created = updated = unchanged = chunks = 0
            total = len(products)
            for i, rec in enumerate(products, start=1):
                rec["source"] = "import"
                listings = rec.pop("listings", [])
                try:
                    kb = self.catalog_kb(tid)
                    product, changed = self.store.upsert_product(tid, kb["id"], rec)
                    is_new = product.pop("created", False)
                    for l in listings:
                        sid = default_store_id
                        if l.get("store"):
                            if l["store"] not in store_ids:
                                store_ids[l["store"]] = self.store.upsert_store(tid, l["store"])["id"]
                            sid = store_ids[l["store"]]
                        if sid:
                            self.store.add_listing(product["id"], sid, l.get("platform_item_id", ""))
                    if not listings and default_store_id:
                        self.store.add_listing(product["id"], default_store_id)
                    if changed:
                        product = self.store.get_product(product["id"])
                        chunks += self._index_product(product)
                        created += 1 if is_new else 0
                        updated += 0 if is_new else 1
                    else:
                        unchanged += 1
                except Exception as e:
                    ctx.error(f"{rec.get('code')}: {e}")
                ctx.progress("index", i, total, f"{i}/{total} {rec.get('title', '')[:30]}")
            self._audit(principal, tid, "catalog.import", os.path.basename(path),
                        {"products": total, "warnings": len(report.warnings)})
            return {"report": report.to_dict(), "products": total, "changed": created + updated,
                    "unchanged": unchanged, "chunks": chunks, "stores_created": list(store_ids),
                    "_message": f"导入完成：{total} 个商品，{created + updated} 个已更新，{unchanged} 个无变化"}

        return self.jobs.submit("catalog_import", f"导入 {os.path.basename(path)}", work, tid, run_inline)

    # ---- single product document -----------------------------------------------------
    def draft_from_document(self, path: str) -> Dict[str, Any]:
        text, tables = doc_extract.extract_document(path)
        draft = doc_extract.draft_product(path, text, tables)
        return {"path": path, "filename": os.path.basename(path), "draft": draft,
                "stats": {"chars": len(text), "tables": len(tables), "attributes": len(draft["attributes"]),
                          "faq": len(draft["faq"]), "has_size_chart": bool(draft["size_chart"])},
                "text_preview": text[:1500]}

    def attach_document(self, product_id: str, path: str, principal: Optional[Principal] = None) -> Dict[str, Any]:
        """Store a source document's text as searchable chunks of the product."""
        product = self.store.get_product(product_id)
        if not product:
            raise ValueError("product not found")
        self._check(principal, product["tenant_id"], "write")
        text, _ = doc_extract.extract_document(path)
        doc = self.store.add_document(product["kb_id"], product["tenant_id"], os.path.basename(path),
                                      _file_hash(path), "product_doc", product_id=product_id)
        chunks = document_chunks(product["title"], text)
        n = self.store.replace_chunks(
            {"kb_id": product["kb_id"], "tenant_id": product["tenant_id"], "product_id": product_id,
             "document_id": doc["id"], "category": product.get("category", "")},
            chunks, self._embed_chunks(chunks, product["tenant_id"]), self.embedder.id)
        self.indexes.invalidate(product["tenant_id"])
        self._audit(principal, product["tenant_id"], "document.attach", doc["id"], {"product_id": product_id, "chunks": n})
        return {**doc, "chunk_count": n}

    def ingest_product_files(self, paths: List[str], store_id: str = "", tenant_id: Optional[str] = None,
                             run_inline: bool = False, principal: Optional[Principal] = None) -> Dict[str, Any]:
        """Batch: one product per document, saved from its draft (review later)."""
        tid = self.tenant_id(tenant_id)
        self._check(principal, tid, "write")

        def work(ctx: JobContext) -> Dict[str, Any]:
            saved = []
            for i, path in enumerate(paths, start=1):
                ctx.progress("extract", i - 1, len(paths), os.path.basename(path), force=True)
                try:
                    draft = self.draft_from_document(path)["draft"]
                    draft["source"] = "document"
                    if store_id:
                        draft["listings"] = [{"store_id": store_id, "platform_item_id": ""}]
                    p = self.save_product(draft, tid)
                    self.attach_document(p["id"], path)
                    saved.append({"id": p["id"], "title": p["title"], "file": os.path.basename(path)})
                except Exception as e:
                    ctx.error(f"{os.path.basename(path)}: {e}")
                ctx.progress("index", i, len(paths), os.path.basename(path))
            return {"saved": saved, "_message": f"已处理 {len(saved)}/{len(paths)} 个文档"}

        return self.jobs.submit("product_docs", f"导入 {len(paths)} 个商品文档", work, tid, run_inline)

    def delete_document(self, document_id: str, principal: Optional[Principal] = None) -> None:
        if principal is not None:
            from knowledge.ks.models import Document
            with self.store.session() as sess:
                d = sess.get(Document, document_id)
                if d:
                    self._check(principal, d.tenant_id, "write")
        tid = self.store.delete_document(document_id)
        if tid:
            self.indexes.invalidate(tid)

    # ---- policies ----------------------------------------------------------------------
    def policy_topics(self) -> List[Dict[str, str]]:
        return [{"value": t, "label": POLICY_TOPIC_LABELS[t]} for t in list(POLICY_TOPICS) + ["other"]]

    def save_policy(self, topic: str, text: str, store_id: Optional[str] = None, title: str = "",
                    tenant_id: Optional[str] = None, principal: Optional[Principal] = None) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
        self._check(principal, tid, "write")
        if store_id:
            st = self.store.get_store(store_id)
            if not st or st["tenant_id"] != tid:
                raise PermissionDenied("store belongs to another tenant")
        text = clean_text(text)
        if not text:
            raise ValueError("规则内容不能为空 / policy text is required")
        pol = self.store.upsert_policy(tid, topic, text, store_id or None, title)
        self._index_policy(pol)
        self._audit(principal, tid, "policy.save", pol["id"], {"topic": topic, "store_id": store_id})
        return pol

    def delete_policy(self, policy_id: str, tenant_id: Optional[str] = None,
                      principal: Optional[Principal] = None) -> None:
        tid = self.tenant_id(tenant_id)
        self._check(principal, tid, "write")
        if not any(p["id"] == policy_id for p in self.store.list_policies(tid)):
            raise PermissionDenied("policy belongs to another tenant")
        self.store.delete_policy(policy_id)
        self.indexes.invalidate(tid)

    def policies_view(self, tenant_id: Optional[str] = None, principal: Optional[Principal] = None) -> Dict[str, Any]:
        """Merchant defaults + each store's overrides, per topic."""
        tid = self.tenant_id(tenant_id)
        self._check(principal, tid, "read")
        rows = self.store.list_policies(tid)
        defaults = {p["topic"]: p for p in rows if p["store_id"] is None}
        overrides: Dict[str, Dict[str, Any]] = {}
        for p in rows:
            if p["store_id"]:
                overrides.setdefault(p["store_id"], {})[p["topic"]] = p
        return {"topics": self.policy_topics(), "defaults": defaults, "overrides": overrides,
                "stores": self.store.list_stores(tid)}

    # ---- re-index ---------------------------------------------------------------------
    def reindex(self, tenant_id: Optional[str] = None, run_inline: bool = False,
                principal: Optional[Principal] = None) -> Dict[str, Any]:
        """Re-embed every chunk with the current embedder (after a model change)."""
        tid = self.tenant_id(tenant_id)
        self._admin(principal, tid)

        def work(ctx: JobContext) -> Dict[str, Any]:
            items = [(cid, embed_text(dt, text, ans)) for cid, dt, text, ans in self.store.chunk_texts_for_reindex(tid)]
            total, batch = len(items), 64
            for i in range(0, total, batch):
                part = items[i:i + batch]
                from knowledge.ks.embedding import billing_owner
                tok = self._billing(tid)
                try:
                    vecs = self.embedder.embed([t for _, t in part])
                finally:
                    billing_owner.reset(tok)
                self.store.set_chunk_vectors([cid for cid, _ in part], vecs, self.embedder.id)
                ctx.progress("embed", min(total, i + batch), total, "重新向量化 / re-embedding")
            for kb in self.store.list_kbs(tid):
                self.store.update_kb(kb["id"], embedder_id=self.embedder.id)
            self.indexes.invalidate(tid)
            return {"chunks": total, "_message": f"已重新向量化 {total} 个分块"}

        return self.jobs.submit("reindex", "重新建立索引", work, tid, run_inline)

    # ---- retrieval -----------------------------------------------------------------------
    def search(self, query: str, store_ref: str = "", platform_item_id: str = "", product_id: str = "",
               tenant_id: Optional[str] = None, k: int = 5, principal: Optional[Principal] = None) -> Dict[str, Any]:
        query = clean_text(query)
        if not query:
            raise ValueError("query is required")
        tid = self.tenant_id(tenant_id)
        allowed = None
        if principal is not None:
            # Hard partition: only KBs this principal may read are searched.
            allowed = self.authz.readable_kbs(principal, tid)
            if not allowed:
                raise PermissionDenied(f"{principal.user_id} may not read this tenant's knowledge")
        from knowledge.ks.embedding import billing_owner
        tok = self._billing(tid)
        try:
            r = self.retriever.retrieve(tid, query, store_ref=store_ref, platform_item_id=str(platform_item_id or ""),
                                        product_id=product_id, k=k, allowed_kbs=allowed,
                                        policy_kb=self.catalog_kb(tid)["id"])
        finally:
            billing_owner.reset(tok)
        out = r.to_dict()
        kb = self.catalog_kb(tid)
        out["plane"] = kb["plane"]
        # Knowledge from a private plane or a confidential KB must stay on private models.
        out["sensitivity"] = "private" if kb["plane"] == "private" or kb["sensitivity"] == "confidential" else "internal"
        return out

    # ---- jobs ------------------------------------------------------------------------------
    def get_job(self, job_id: str, principal: Optional[Principal] = None) -> Optional[Dict[str, Any]]:
        job = self.store.get_job(job_id)
        if job and principal is not None:
            self._check(principal, job["tenant_id"], "read")
        return job

    def list_jobs(self, tenant_id: Optional[str] = None, limit: int = 30,
                  principal: Optional[Principal] = None) -> List[Dict[str, Any]]:
        tid = self.tenant_id(tenant_id)
        self._check(principal, tid, "read")
        return self.store.list_jobs(tid, limit)

    def cancel_job(self, job_id: str, principal: Optional[Principal] = None) -> None:
        job = self.store.get_job(job_id)
        if job and principal is not None:
            self._check(principal, job["tenant_id"], "write")
        self.jobs.cancel(job_id)

    # ---- members & permissions ------------------------------------------------------
    def access_view(self, tenant_id: Optional[str] = None, principal: Optional[Principal] = None) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
        self._admin(principal, tid)
        return {"tenant": self.store.get_tenant(tid), "members": self.members.list_members(tid),
                "groups": self.members.list_groups(tid), "grants": self.members.list_grants(tid),
                "kbs": self.store.list_kbs(tid), "stores": self.store.list_stores(tid),
                "me": (principal or self.local).to_dict()}

    def save_member(self, email: str, role: str = "viewer", status: Optional[str] = None, member_id: Optional[str] = None,
                    display_name: str = "", tenant_id: Optional[str] = None,
                    principal: Optional[Principal] = None) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
        actor_role = self._admin(principal, tid)
        m = self.members.save_member(tid, email, role, status, display_name, member_id, actor_role)
        self._audit(principal, tid, "member.save", m["id"], {"email": m["email"], "role": role, "status": m["status"]})
        return m

    def remove_member(self, member_id: str, tenant_id: Optional[str] = None,
                      principal: Optional[Principal] = None) -> None:
        tid = self.tenant_id(tenant_id)
        actor_role = self._admin(principal, tid)
        self.members.remove_member(tid, member_id, actor_role)
        self._audit(principal, tid, "member.remove", member_id)

    def save_group(self, name: str, member_ids: List[str], description: str = "", group_id: Optional[str] = None,
                   tenant_id: Optional[str] = None, principal: Optional[Principal] = None) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
        self._admin(principal, tid)
        g = self.members.save_group(tid, name, member_ids, description, group_id)
        self._audit(principal, tid, "group.save", g["id"], {"name": name, "members": len(g["member_ids"])})
        return g

    def delete_group(self, group_id: str, tenant_id: Optional[str] = None, principal: Optional[Principal] = None) -> None:
        tid = self.tenant_id(tenant_id)
        self._admin(principal, tid)
        self.members.delete_group(tid, group_id)
        self._audit(principal, tid, "group.delete", group_id)

    def set_grant(self, kb_id: str, principal_type: str, principal_id: str, permission: str,
                  tenant_id: Optional[str] = None, principal: Optional[Principal] = None) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
        self._admin(principal, tid)
        g = self.members.set_grant(tid, kb_id, principal_type, principal_id, permission)
        self._audit(principal, tid, "grant.set", kb_id, g)
        return g

    def remove_grant(self, grant_id: str, tenant_id: Optional[str] = None, principal: Optional[Principal] = None) -> None:
        tid = self.tenant_id(tenant_id)
        self._admin(principal, tid)
        self.members.remove_grant(tid, grant_id)
        self._audit(principal, tid, "grant.remove", grant_id)

    def update_kb(self, kb_id: str, tenant_id: Optional[str] = None, principal: Optional[Principal] = None,
                  **fields) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
        self._admin(principal, tid)
        kb = self.store.get_kb(kb_id)
        if not kb or kb["tenant_id"] != tid:
            raise PermissionDenied("knowledge base belongs to another tenant")
        allowed = {k: v for k, v in fields.items() if k in ("name", "description", "plane", "sensitivity")}
        if allowed.get("plane") and allowed["plane"] not in ("local", "private", "public"):
            raise ValueError("unknown plane")
        if allowed.get("sensitivity") and allowed["sensitivity"] not in ("public", "internal", "confidential"):
            raise ValueError("unknown sensitivity")
        kb = self.store.update_kb(kb_id, **allowed)
        self._audit(principal, tid, "kb.update", kb_id, allowed)
        return kb

    def set_email_domain(self, domain: str, tenant_id: Optional[str] = None,
                         principal: Optional[Principal] = None) -> None:
        tid = self.tenant_id(tenant_id)
        actor_role = self._admin(principal, tid)
        if actor_role != "owner":
            raise PermissionDenied("only an owner can set the auto-join email domain")
        self.members.set_email_domain(tid, domain)
        self._audit(principal, tid, "tenant.email_domain", tid, {"domain": domain})

    def list_audit(self, tenant_id: Optional[str] = None, limit: int = 100,
                   principal: Optional[Principal] = None) -> List[Dict[str, Any]]:
        tid = self.tenant_id(tenant_id)
        self._admin(principal, tid)
        return self.store.list_audit(tid, limit)


# ---- per-user singleton for the desktop app ---------------------------------------------------
_services: Dict[str, KnowledgeService] = {}
_services_lock = threading.Lock()


EMBEDDER_KEY = "ks_embedding_api_key"


def embedder_config(main_window=None) -> Dict[str, Any]:
    """The product-knowledge embedding model: the app default, or an
    OpenAI-compatible endpoint (LM Studio, vLLM on the private server, cloud)."""
    import json
    path = os.path.join(_ks_folder(main_window), "embedder.json")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    return {"mode": cfg.get("mode", "app"), "base_url": cfg.get("base_url", ""), "model": cfg.get("model", ""),
            "verify_tls": bool(cfg.get("verify_tls", True)), "has_api_key": bool(_embed_key(main_window))}


def _embed_key(main_window=None) -> str:
    try:
        from utils.env.secure_store import secure_store
        return secure_store.get(EMBEDDER_KEY) or ""
    except Exception:
        return ""


def save_embedder_config(mode: str, base_url: str = "", model: str = "", api_key: Optional[str] = None,
                         verify_tls: bool = True, main_window=None) -> Dict[str, Any]:
    import json
    if mode not in ("app", "openai"):
        raise ValueError("mode must be app or openai")
    if mode == "openai":
        if not base_url.startswith(("http://", "https://")) or not model.strip():
            raise ValueError("an http(s) address and a model name are required")
    folder = _ks_folder(main_window)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "embedder.json"), "w", encoding="utf-8") as f:
        json.dump({"mode": mode, "base_url": base_url.strip(), "model": model.strip(), "verify_tls": verify_tls}, f)
    if api_key is not None:
        try:
            from utils.env.secure_store import secure_store
            if api_key:
                secure_store.set(EMBEDDER_KEY, api_key)
            else:
                secure_store.delete(EMBEDDER_KEY)
        except Exception as e:
            logger.warning(f"[KS] could not store the embedding API key securely: {e}")
    reset_services()  # next get_service() uses the new model; the KS shows "re-index needed"
    return embedder_config(main_window)


def _configured_embedder(main_window=None):
    from knowledge.ks.embedding import OpenAICompatibleEmbedder, resolve_app_embedder
    cfg = embedder_config(main_window)
    if cfg["mode"] == "openai" and cfg["base_url"] and cfg["model"]:
        return OpenAICompatibleEmbedder(cfg["base_url"], cfg["model"], _embed_key(main_window),
                                        verify_tls=cfg["verify_tls"])
    return resolve_app_embedder(main_window)


def get_service(main_window=None) -> KnowledgeService:
    """The signed-in user's KnowledgeService (SQLite in their data dir)."""
    if main_window is None:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
    base = getattr(main_window, "my_ecb_data_homepath", None) if main_window else None
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".ecan")
    user = str(getattr(main_window, "log_user", "") or "") if main_window else ""
    key = os.path.abspath(base)
    with _services_lock:
        svc = _services.get(key)
        if svc is None:
            folder = os.path.join(base, "knowledge_service")
            os.makedirs(folder, exist_ok=True)
            url = "sqlite:///" + os.path.join(folder, "ks.db").replace("\\", "/")
            svc = KnowledgeService(url, embedder=_configured_embedder(main_window), owner=user,
                                   job_listener=_broadcast_job)
            _services[key] = svc
            logger.info(f"[KS] Knowledge Service ready at {url} (embedder={svc.embedder.id})")
        return svc


_routers: Dict[str, Any] = {}


def get_router(main_window=None):
    """PlaneRouter over the user's local service and saved connections."""
    from knowledge.ks.planes import ConnectionStore, PlaneRouter
    svc = get_service(main_window)
    key = str(id(svc))
    with _services_lock:
        router = _routers.get(key)
        if router is None:
            folder = os.path.dirname(svc.store.engine.url.database or "") or "."
            router = PlaneRouter(svc, ConnectionStore(os.path.join(folder, "connections.json")),
                                 lan_source=lambda: get_lan(main_window)["source"])
            _routers[key] = router
        return router


_lan: Dict[str, Any] = {}


def _ks_folder(main_window=None) -> str:
    """The user's knowledge_service folder (same place get_service uses)."""
    if main_window is None:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
    base = getattr(main_window, "my_ecb_data_homepath", None) if main_window else None
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".ecan")
    return os.path.join(base, "knowledge_service")  # created on first write


def get_lan(main_window=None) -> Dict[str, Any]:
    """LAN sharing objects for this user: access (commander), source (platoon), runner."""
    from knowledge.ks.lan import GatewayRunner, LanAccess, LanSource
    folder = _ks_folder(main_window)
    with _services_lock:
        if _lan.get("folder") != folder:
            old = _lan.get("runner")
            if old is not None:
                old.stop()
            _lan.update(folder=folder, access=LanAccess(folder), source=LanSource(folder), runner=GatewayRunner())
        return _lan


def machine_role(main_window=None) -> str:
    try:
        if main_window is None:
            from app_context import AppContext
            main_window = AppContext.get_main_window()
        return str(getattr(main_window, "machine_role", "") or "")
    except Exception:
        return ""


def lan_sharing_status(main_window=None) -> Dict[str, Any]:
    from knowledge.ks.lan import lan_addresses
    lan = get_lan(main_window)
    cfg = lan["access"].config()
    runner = lan["runner"]
    return {"role": machine_role(main_window), "enabled": cfg["enabled"], "port": cfg["port"],
            "running": runner.running, "error": runner.error,
            "addresses": [f"http://{ip}:{cfg['port']}" for ip in lan_addresses()],
            "devices": lan["access"].devices(), "source": lan["source"].get()}


def apply_lan_sharing(main_window=None) -> Dict[str, Any]:
    """Start or stop the commander's LAN gateway to match the saved setting."""
    lan = get_lan(main_window)
    cfg = lan["access"].config()
    runner = lan["runner"]
    if not cfg["enabled"]:
        runner.stop()
        return lan_sharing_status(main_window)
    if runner.running and runner.port == cfg["port"]:
        return lan_sharing_status(main_window)
    from knowledge.ks.lan import create_gateway_app
    import socket as _socket

    def _lightrag_base() -> str:
        from knowledge.lightrag_client import _resolve_base_url
        return _resolve_base_url(local_only=True)

    app = create_gateway_app(get_service(main_window), lan["access"], _lightrag_base,
                             lambda: os.environ.get("LIGHTRAG_API_KEY", ""), _socket.gethostname())
    runner.start(app, cfg["port"])
    logger.info(f"[KS-LAN] gateway {'listening on port ' + str(cfg['port']) if runner.running else 'failed: ' + runner.error}")
    return lan_sharing_status(main_window)


def init_lan_sharing(main_window=None) -> None:
    """App startup: a Commander shares knowledge with its LAN machines by default."""
    try:
        lan = get_lan(main_window)
        access = lan["access"]
        if not os.path.exists(access.config_path) and "commander" in machine_role(main_window).lower():
            access.set_config(enabled=True)
        apply_lan_sharing(main_window)
    except Exception as e:
        logger.warning(f"[KS-LAN] LAN sharing not started: {e}")


def reset_services() -> None:
    """Drop cached services (e.g. after the embedding provider changes)."""
    with _services_lock:
        _services.clear()
        _routers.clear()


def _broadcast_job(job: Dict[str, Any]) -> None:
    try:
        from gui.LocalServer import app_ws_manager
        app_ws_manager.broadcast_sync("ks.jobProgress", job)
    except Exception:
        pass  # the GUI also polls ks.getJob
