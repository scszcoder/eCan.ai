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
from knowledge.ks.chunking import document_chunks, policy_chunks, product_chunks
from knowledge.ks.embedding import Embedder, HashingEmbedder
from knowledge.ks.index import IndexCache
from knowledge.ks.jobs import JobContext, JobRunner
from knowledge.ks.retrieval import ProductRetriever
from knowledge.ks.store import KSStore
from knowledge.ks.text import POLICY_TOPIC_LABELS, POLICY_TOPICS, clean_text
from utils.logger_helper import logger_helper as logger

DEFAULT_TENANT_NAME = "我的店铺"


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class KnowledgeService:
    def __init__(self, db_url: str, embedder: Optional[Embedder] = None, owner: str = "",
                 job_listener: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.store = KSStore(db_url)
        self.embedder: Embedder = embedder or HashingEmbedder()
        self.owner = owner
        self.indexes = IndexCache(lambda tid: self.store.load_index(tid)[:2])
        self.retriever = ProductRetriever(self.store, self.indexes, self.embedder)
        self.jobs = JobRunner(self.store, [job_listener] if job_listener else [])
        self._tenant_lock = threading.Lock()
        self._default_tenant: Optional[Dict[str, Any]] = None

    # ---- tenant / KB --------------------------------------------------------
    def default_tenant(self) -> Dict[str, Any]:
        with self._tenant_lock:
            if self._default_tenant is None:
                t = self.store.ensure_tenant(DEFAULT_TENANT_NAME)
                self.store.ensure_kb(t["id"], "商品知识库", kind="catalog", owner=self.owner)
                self._default_tenant = t
            return self._default_tenant

    def tenant_id(self, tenant_id: Optional[str] = None) -> str:
        return tenant_id or self.default_tenant()["id"]

    def catalog_kb(self, tenant_id: str) -> Dict[str, Any]:
        return self.store.ensure_kb(tenant_id, "商品知识库", kind="catalog", owner=self.owner)

    def overview(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
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
    def _embed_chunks(self, chunks: List[Dict[str, Any]]):
        if not chunks:
            return None
        return self.embedder.embed([c["text"] for c in chunks])

    def _index_product(self, product: Dict[str, Any]) -> int:
        chunks = product_chunks(product)
        n = self.store.replace_chunks(
            {"kb_id": product["kb_id"], "tenant_id": product["tenant_id"], "product_id": product["id"],
             "category": product.get("category", "")},
            chunks, self._embed_chunks(chunks), self.embedder.id)
        self.indexes.invalidate(product["tenant_id"])
        return n

    def _index_policy(self, policy: Dict[str, Any]) -> int:
        kb = self.catalog_kb(policy["tenant_id"])
        chunks = policy_chunks(policy["topic"], policy.get("title", ""), policy["text"])
        n = self.store.replace_chunks(
            {"kb_id": kb["id"], "tenant_id": policy["tenant_id"], "policy_id": policy["id"],
             "store_id": policy.get("store_id")},
            chunks, self._embed_chunks(chunks), self.embedder.id)
        self.indexes.invalidate(policy["tenant_id"])
        return n

    # ---- stores -------------------------------------------------------------------
    def save_store(self, data: Dict[str, Any], tenant_id: Optional[str] = None) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
        name = clean_text(data.get("name"))
        if not name:
            raise ValueError("店铺名称不能为空 / store name is required")
        st = self.store.upsert_store(tid, name, data.get("platform", ""), data.get("id"),
                                     data.get("platform_store_id", ""), data.get("ecan_store_id", ""))
        self.store.audit(self.owner, "store.save", st["id"], {"name": name})
        return st

    def delete_store(self, store_id: str) -> None:
        st = self.store.get_store(store_id)
        self.store.delete_store(store_id)
        if st:
            self.indexes.invalidate(st["tenant_id"])
        self.store.audit(self.owner, "store.delete", store_id)

    # ---- products -----------------------------------------------------------------
    def save_product(self, data: Dict[str, Any], tenant_id: Optional[str] = None) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
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
        self.store.audit(self.owner, "product.save", product["id"], {"code": product["code"], "changed": changed})
        return product

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        p = self.store.get_product(product_id)
        if p:
            p["documents"] = self.store.list_documents(product_id)
        return p

    def delete_product(self, product_id: str) -> None:
        tid = self.store.delete_product(product_id)
        if tid:
            self.indexes.invalidate(tid)
        self.store.audit(self.owner, "product.delete", product_id)

    def list_products(self, tenant_id: Optional[str] = None, **filters) -> Dict[str, Any]:
        return self.store.list_products(self.tenant_id(tenant_id), **filters)

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
                       tenant_id: Optional[str] = None, run_inline: bool = False) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)

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
            self.store.audit(self.owner, "catalog.import", os.path.basename(path),
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

    def attach_document(self, product_id: str, path: str) -> Dict[str, Any]:
        """Store a source document's text as searchable chunks of the product."""
        product = self.store.get_product(product_id)
        if not product:
            raise ValueError("product not found")
        text, _ = doc_extract.extract_document(path)
        doc = self.store.add_document(product["kb_id"], product["tenant_id"], os.path.basename(path),
                                      _file_hash(path), "product_doc", product_id=product_id)
        chunks = document_chunks(product["title"], text)
        n = self.store.replace_chunks(
            {"kb_id": product["kb_id"], "tenant_id": product["tenant_id"], "product_id": product_id,
             "document_id": doc["id"], "category": product.get("category", "")},
            chunks, self._embed_chunks(chunks), self.embedder.id)
        self.indexes.invalidate(product["tenant_id"])
        self.store.audit(self.owner, "document.attach", doc["id"], {"product_id": product_id, "chunks": n})
        return {**doc, "chunk_count": n}

    def ingest_product_files(self, paths: List[str], store_id: str = "", tenant_id: Optional[str] = None,
                             run_inline: bool = False) -> Dict[str, Any]:
        """Batch: one product per document, saved from its draft (review later)."""
        tid = self.tenant_id(tenant_id)

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

    def delete_document(self, document_id: str) -> None:
        tid = self.store.delete_document(document_id)
        if tid:
            self.indexes.invalidate(tid)

    # ---- policies ----------------------------------------------------------------------
    def policy_topics(self) -> List[Dict[str, str]]:
        return [{"value": t, "label": POLICY_TOPIC_LABELS[t]} for t in list(POLICY_TOPICS) + ["other"]]

    def save_policy(self, topic: str, text: str, store_id: Optional[str] = None, title: str = "",
                    tenant_id: Optional[str] = None) -> Dict[str, Any]:
        tid = self.tenant_id(tenant_id)
        text = clean_text(text)
        if not text:
            raise ValueError("规则内容不能为空 / policy text is required")
        pol = self.store.upsert_policy(tid, topic, text, store_id or None, title)
        self._index_policy(pol)
        self.store.audit(self.owner, "policy.save", pol["id"], {"topic": topic, "store_id": store_id})
        return pol

    def delete_policy(self, policy_id: str, tenant_id: Optional[str] = None) -> None:
        self.store.delete_policy(policy_id)
        self.indexes.invalidate(self.tenant_id(tenant_id))

    def policies_view(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Merchant defaults + each store's overrides, per topic."""
        tid = self.tenant_id(tenant_id)
        rows = self.store.list_policies(tid)
        defaults = {p["topic"]: p for p in rows if p["store_id"] is None}
        overrides: Dict[str, Dict[str, Any]] = {}
        for p in rows:
            if p["store_id"]:
                overrides.setdefault(p["store_id"], {})[p["topic"]] = p
        return {"topics": self.policy_topics(), "defaults": defaults, "overrides": overrides,
                "stores": self.store.list_stores(tid)}

    # ---- re-index ---------------------------------------------------------------------
    def reindex(self, tenant_id: Optional[str] = None, run_inline: bool = False) -> Dict[str, Any]:
        """Re-embed every chunk with the current embedder (after a model change)."""
        tid = self.tenant_id(tenant_id)

        def work(ctx: JobContext) -> Dict[str, Any]:
            items = self.store.chunk_texts_for_reindex(tid)
            total, batch = len(items), 64
            for i in range(0, total, batch):
                part = items[i:i + batch]
                vecs = self.embedder.embed([t for _, t in part])
                self.store.set_chunk_vectors([cid for cid, _ in part], vecs, self.embedder.id)
                ctx.progress("embed", min(total, i + batch), total, "重新向量化 / re-embedding")
            for kb in self.store.list_kbs(tid):
                self.store.update_kb(kb["id"], embedder_id=self.embedder.id)
            self.indexes.invalidate(tid)
            return {"chunks": total, "_message": f"已重新向量化 {total} 个分块"}

        return self.jobs.submit("reindex", "重新建立索引", work, tid, run_inline)

    # ---- retrieval -----------------------------------------------------------------------
    def search(self, query: str, store_ref: str = "", platform_item_id: str = "", product_id: str = "",
               tenant_id: Optional[str] = None, k: int = 5) -> Dict[str, Any]:
        query = clean_text(query)
        if not query:
            raise ValueError("query is required")
        tid = self.tenant_id(tenant_id)
        r = self.retriever.retrieve(tid, query, store_ref=store_ref, platform_item_id=str(platform_item_id or ""),
                                    product_id=product_id, k=k)
        return r.to_dict()

    # ---- jobs ------------------------------------------------------------------------------
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_job(job_id)

    def list_jobs(self, tenant_id: Optional[str] = None, limit: int = 30) -> List[Dict[str, Any]]:
        return self.store.list_jobs(self.tenant_id(tenant_id), limit)

    def cancel_job(self, job_id: str) -> None:
        self.jobs.cancel(job_id)


# ---- per-user singleton for the desktop app ---------------------------------------------------
_services: Dict[str, KnowledgeService] = {}
_services_lock = threading.Lock()


def get_service(main_window=None) -> KnowledgeService:
    """The signed-in user's KnowledgeService (SQLite in their data dir)."""
    from knowledge.ks.embedding import resolve_app_embedder
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
            svc = KnowledgeService(url, embedder=resolve_app_embedder(main_window), owner=user,
                                   job_listener=_broadcast_job)
            _services[key] = svc
            logger.info(f"[KS] Knowledge Service ready at {url} (embedder={svc.embedder.id})")
        return svc


def reset_services() -> None:
    """Drop cached services (e.g. after the embedding provider changes)."""
    with _services_lock:
        _services.clear()


def _broadcast_job(job: Dict[str, Any]) -> None:
    try:
        from gui.LocalServer import app_ws_manager
        app_ws_manager.broadcast_sync("ks.jobProgress", job)
    except Exception:
        pass  # the GUI also polls ks.getJob
