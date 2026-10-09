"""
Persistence for the Knowledge Service. Returns plain dicts so results can go
straight over IPC. SQLite on desktop (WAL), any SQLAlchemy URL on servers.
"""
from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from sqlalchemy import create_engine, event, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from knowledge.ks.embedding import from_blob, to_blob
from knowledge.ks.index import IndexedChunk
from knowledge.ks.models import (
    AuditLog, Base, Chunk, Document, Grant, Job, KnowledgeBase, Listing, Policy, Product, Store, Tenant,
)

PRODUCT_FIELDS = ("code", "title", "category", "brand", "attributes", "variants", "size_chart",
                  "selling_points", "description", "care", "faq", "images", "source")


def content_hash(data: Dict[str, Any]) -> str:
    payload = {k: data.get(k) for k in PRODUCT_FIELDS if k != "source"}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


class KSStore:
    def __init__(self, url: str):
        kwargs: Dict[str, Any] = {"future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        self.engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def _pragmas(dbapi_conn, _):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.close()
        Base.metadata.create_all(self.engine)
        self._Session = sessionmaker(self.engine, expire_on_commit=False, future=True)
        self._write_lock = threading.RLock()  # SQLite: one writer at a time

    @contextmanager
    def session(self, write: bool = False):
        lock = self._write_lock if write else None
        if lock:
            lock.acquire()
        s: Session = self._Session()
        try:
            yield s
            if write:
                s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
            if lock:
                lock.release()

    # ---- serialisers -------------------------------------------------------
    @staticmethod
    def _tenant(t: Tenant) -> Dict[str, Any]:
        return {"id": t.id, "name": t.name, "kind": t.kind, "email_domain": t.email_domain or ""}

    @staticmethod
    def _store(s: Store) -> Dict[str, Any]:
        return {"id": s.id, "tenant_id": s.tenant_id, "name": s.name, "platform": s.platform or "",
                "platform_store_id": s.platform_store_id or "", "ecan_store_id": s.ecan_store_id or ""}

    @staticmethod
    def _kb(k: KnowledgeBase) -> Dict[str, Any]:
        return {"id": k.id, "tenant_id": k.tenant_id, "name": k.name, "description": k.description or "",
                "kind": k.kind, "plane": k.plane, "sensitivity": k.sensitivity,
                "index_profile": k.index_profile, "embedder_id": k.embedder_id or "", "owner": k.owner or "",
                "created_at": _iso(k.created_at)}

    @staticmethod
    def _product(p: Product, with_listings: bool = True) -> Dict[str, Any]:
        d = {f: getattr(p, f) for f in PRODUCT_FIELDS}
        d.update({"id": p.id, "tenant_id": p.tenant_id, "kb_id": p.kb_id, "updated_at": _iso(p.updated_at)})
        for f, default in (("attributes", {}), ("variants", []), ("size_chart", {}), ("selling_points", []),
                           ("faq", []), ("images", [])):
            if d[f] is None:
                d[f] = default
        if with_listings:
            d["listings"] = [{"id": l.id, "store_id": l.store_id, "platform_item_id": l.platform_item_id or "",
                              "title_override": l.title_override or ""} for l in p.listings]
        return d

    @staticmethod
    def _policy(p: Policy) -> Dict[str, Any]:
        return {"id": p.id, "tenant_id": p.tenant_id, "store_id": p.store_id, "topic": p.topic,
                "title": p.title or "", "text": p.text or "", "updated_at": _iso(p.updated_at)}

    @staticmethod
    def _job(j: Job) -> Dict[str, Any]:
        return {"id": j.id, "kind": j.kind, "tenant_id": j.tenant_id, "title": j.title, "status": j.status,
                "stage": j.stage, "progress": j.progress or 0.0, "done": j.done or 0, "total": j.total or 0,
                "message": j.message or "", "errors": j.errors or [], "result": j.result or {},
                "created_at": _iso(j.created_at), "updated_at": _iso(j.updated_at)}

    # ---- tenants / stores / KBs ------------------------------------------
    def ensure_tenant(self, name: str, kind: str = "merchant", tenant_id: Optional[str] = None) -> Dict[str, Any]:
        with self.session(write=True) as s:
            t = s.get(Tenant, tenant_id) if tenant_id else s.scalars(select(Tenant).order_by(Tenant.created_at)).first()
            if t is None:
                t = Tenant(id=tenant_id, name=name, kind=kind) if tenant_id else Tenant(name=name, kind=kind)
                s.add(t)
                s.flush()
            return self._tenant(t)

    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        with self.session() as s:
            t = s.get(Tenant, tenant_id)
            return self._tenant(t) if t else None

    def update_tenant(self, tenant_id: str, **fields) -> Dict[str, Any]:
        with self.session(write=True) as s:
            t = s.get(Tenant, tenant_id)
            for k in ("name", "kind", "email_domain"):
                if k in fields and fields[k] is not None:
                    setattr(t, k, fields[k])
            return self._tenant(t)

    def ensure_kb(self, tenant_id: str, name: str, kind: str = "catalog", plane: str = "local",
                  owner: str = "") -> Dict[str, Any]:
        with self.session(write=True) as s:
            k = s.scalars(select(KnowledgeBase).where(KnowledgeBase.tenant_id == tenant_id,
                                                      KnowledgeBase.kind == kind)).first()
            if k is None:
                k = KnowledgeBase(tenant_id=tenant_id, name=name, kind=kind, plane=plane, owner=owner)
                s.add(k)
                s.flush()
                s.add(Grant(kb_id=k.id, principal_type="user", principal_id=owner or "owner", permission="manage"))
            return self._kb(k)

    def list_kbs(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self.session() as s:
            return [self._kb(k) for k in s.scalars(select(KnowledgeBase).where(KnowledgeBase.tenant_id == tenant_id)
                                                   .order_by(KnowledgeBase.created_at))]

    def get_kb(self, kb_id: str) -> Optional[Dict[str, Any]]:
        with self.session() as s:
            k = s.get(KnowledgeBase, kb_id)
            return self._kb(k) if k else None

    def update_kb(self, kb_id: str, **fields) -> Dict[str, Any]:
        with self.session(write=True) as s:
            k = s.get(KnowledgeBase, kb_id)
            for f in ("name", "description", "plane", "sensitivity", "index_profile", "embedder_id"):
                if f in fields and fields[f] is not None:
                    setattr(k, f, fields[f])
            return self._kb(k)

    def list_stores(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self.session() as s:
            rows = s.scalars(select(Store).where(Store.tenant_id == tenant_id).order_by(Store.created_at)).all()
            out = []
            for st in rows:
                d = self._store(st)
                d["product_count"] = s.scalar(select(func.count(Listing.id)).where(Listing.store_id == st.id)) or 0
                d["policy_overrides"] = s.scalar(select(func.count(Policy.id)).where(Policy.store_id == st.id)) or 0
                out.append(d)
            return out

    def upsert_store(self, tenant_id: str, name: str, platform: str = "", store_id: Optional[str] = None,
                     platform_store_id: str = "", ecan_store_id: str = "") -> Dict[str, Any]:
        with self.session(write=True) as s:
            st = s.get(Store, store_id) if store_id else None
            if st is None:
                st = s.scalars(select(Store).where(Store.tenant_id == tenant_id, Store.name == name)).first()
            if st is None:
                st = Store(tenant_id=tenant_id, name=name)
                s.add(st)
            st.name, st.platform = name, platform or st.platform or ""
            st.platform_store_id = platform_store_id or st.platform_store_id or ""
            st.ecan_store_id = ecan_store_id or st.ecan_store_id or ""
            s.flush()
            return self._store(st)

    def delete_store(self, store_id: str) -> None:
        with self.session(write=True) as s:
            st = s.get(Store, store_id)
            if st:
                s.delete(st)

    def get_store(self, store_id: str) -> Optional[Dict[str, Any]]:
        with self.session() as s:
            st = s.get(Store, store_id)
            return self._store(st) if st else None

    def find_store(self, tenant_id: str, ref: str) -> Optional[Dict[str, Any]]:
        """Store by id, eCan store id, platform store id or name."""
        if not ref:
            return None
        with self.session() as s:
            st = s.get(Store, ref)
            if st is None:
                st = s.scalars(select(Store).where(Store.tenant_id == tenant_id, or_(
                    Store.ecan_store_id == ref, Store.platform_store_id == ref, Store.name == ref))).first()
            return self._store(st) if st else None

    # ---- products ----------------------------------------------------------
    def upsert_product(self, tenant_id: str, kb_id: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """Insert or update by merchant product code. Returns (product, changed)."""
        h = content_hash(data)
        with self.session(write=True) as s:
            p = None
            if data.get("id"):
                p = s.get(Product, data["id"])
            if p is None:
                p = s.scalars(select(Product).where(Product.tenant_id == tenant_id,
                                                    Product.code == data["code"])).first()
            changed = p is None or p.content_hash != h
            created = p is None
            if p is None:
                p = Product(tenant_id=tenant_id, kb_id=kb_id, code=data["code"], title=data["title"])
                s.add(p)
            if changed:
                for f in PRODUCT_FIELDS:
                    if f in data and data[f] is not None:
                        setattr(p, f, data[f])
                p.content_hash = h
            s.flush()
            return {**self._product(p), "created": created}, changed

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        with self.session() as s:
            p = s.get(Product, product_id)
            return self._product(p) if p else None

    def delete_product(self, product_id: str) -> Optional[str]:
        with self.session(write=True) as s:
            p = s.get(Product, product_id)
            if not p:
                return None
            tid = p.tenant_id
            s.delete(p)
            return tid

    def list_products(self, tenant_id: str, q: str = "", category: str = "", store_id: str = "",
                      offset: int = 0, limit: int = 50) -> Dict[str, Any]:
        with self.session() as s:
            stmt = select(Product).where(Product.tenant_id == tenant_id)
            if q:
                like = f"%{q}%"
                stmt = stmt.where(or_(Product.title.like(like), Product.code.like(like),
                                      Product.id.in_(select(Listing.product_id).where(Listing.platform_item_id == q))))
            if category:
                stmt = stmt.where(Product.category == category)
            if store_id:
                stmt = stmt.where(Product.id.in_(select(Listing.product_id).where(Listing.store_id == store_id)))
            total = s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
            rows = s.scalars(stmt.order_by(Product.updated_at.desc()).offset(offset).limit(limit)).all()
            items = []
            for p in rows:
                d = self._product(p)
                d["chunk_count"] = s.scalar(select(func.count(Chunk.id)).where(Chunk.product_id == p.id)) or 0
                d["doc_count"] = s.scalar(select(func.count(Document.id)).where(Document.product_id == p.id)) or 0
                items.append(d)
            return {"items": items, "total": total}

    def categories(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self.session() as s:
            rows = s.execute(select(Product.category, func.count(Product.id)).where(Product.tenant_id == tenant_id)
                             .group_by(Product.category).order_by(func.count(Product.id).desc())).all()
            return [{"category": c or "", "count": n} for c, n in rows]

    def set_listings(self, product_id: str, listings: Iterable[Dict[str, Any]]) -> None:
        """Replace a product's store listings."""
        with self.session(write=True) as s:
            p = s.get(Product, product_id)
            wanted = {}
            for l in listings:
                if l.get("store_id"):
                    wanted[l["store_id"]] = l
            for existing in list(p.listings):
                if existing.store_id not in wanted:
                    s.delete(existing)
            have = {l.store_id: l for l in p.listings}
            for sid, l in wanted.items():
                row = have.get(sid) or Listing(product_id=product_id, store_id=sid)
                row.platform_item_id = str(l.get("platform_item_id") or "")
                row.title_override = l.get("title_override") or ""
                if sid not in have:
                    s.add(row)

    def add_listing(self, product_id: str, store_id: str, platform_item_id: str = "") -> None:
        with self.session(write=True) as s:
            row = s.scalars(select(Listing).where(Listing.product_id == product_id,
                                                  Listing.store_id == store_id)).first()
            if row is None:
                s.add(Listing(product_id=product_id, store_id=store_id, platform_item_id=platform_item_id))
            elif platform_item_id:
                row.platform_item_id = platform_item_id

    def resolve_item(self, tenant_id: str, platform_item_id: str, store_id: Optional[str] = None) -> Optional[str]:
        """Product id for a platform item id (商品ID), preferring the given store."""
        if not platform_item_id:
            return None
        with self.session() as s:
            stmt = select(Listing).join(Store, Store.id == Listing.store_id).where(
                Store.tenant_id == tenant_id, Listing.platform_item_id == str(platform_item_id))
            rows = s.scalars(stmt).all()
            if not rows:
                return None
            for r in rows:
                if store_id and r.store_id == store_id:
                    return r.product_id
            return rows[0].product_id

    def store_product_ids(self, store_id: str) -> set:
        with self.session() as s:
            return set(s.scalars(select(Listing.product_id).where(Listing.store_id == store_id)))

    # ---- policies ------------------------------------------------------------
    def upsert_policy(self, tenant_id: str, topic: str, text: str, store_id: Optional[str] = None,
                      title: str = "") -> Dict[str, Any]:
        with self.session(write=True) as s:
            p = s.scalars(select(Policy).where(Policy.tenant_id == tenant_id, Policy.topic == topic,
                                               Policy.store_id.is_(None) if not store_id else Policy.store_id == store_id)).first()
            if p is None:
                p = Policy(tenant_id=tenant_id, store_id=store_id or None, topic=topic)
                s.add(p)
            p.text, p.title = text, title or p.title or ""
            s.flush()
            return self._policy(p)

    def delete_policy(self, policy_id: str) -> None:
        with self.session(write=True) as s:
            p = s.get(Policy, policy_id)
            if p:
                s.delete(p)

    def list_policies(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self.session() as s:
            return [self._policy(p) for p in s.scalars(select(Policy).where(Policy.tenant_id == tenant_id)
                                                       .order_by(Policy.topic, Policy.store_id))]

    def effective_policies(self, tenant_id: str, store_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
        """topic -> policy, store override first, then merchant default."""
        out: Dict[str, Dict[str, Any]] = {}
        for p in self.list_policies(tenant_id):
            if p["store_id"] is None:
                out.setdefault(p["topic"], {**p, "inherited": True})
        for p in self.list_policies(tenant_id):
            if store_id and p["store_id"] == store_id:
                out[p["topic"]] = {**p, "inherited": False}
        return out

    # ---- documents -----------------------------------------------------------
    def add_document(self, kb_id: str, tenant_id: str, filename: str, content_hash: str, doc_type: str,
                     product_id: Optional[str] = None, store_id: Optional[str] = None,
                     meta: Optional[dict] = None) -> Dict[str, Any]:
        with self.session(write=True) as s:
            d = s.scalars(select(Document).where(Document.kb_id == kb_id, Document.filename == filename,
                                                 Document.product_id == product_id)).first()
            if d is None:
                d = Document(kb_id=kb_id, tenant_id=tenant_id, filename=filename, product_id=product_id)
                s.add(d)
            d.content_hash, d.doc_type, d.store_id, d.meta = content_hash, doc_type, store_id, meta or {}
            s.flush()
            return {"id": d.id, "filename": d.filename, "product_id": d.product_id, "doc_type": d.doc_type}

    def list_documents(self, product_id: str) -> List[Dict[str, Any]]:
        with self.session() as s:
            return [{"id": d.id, "filename": d.filename, "doc_type": d.doc_type, "status": d.status,
                     "created_at": _iso(d.created_at),
                     "chunk_count": s.scalar(select(func.count(Chunk.id)).where(Chunk.document_id == d.id)) or 0}
                    for d in s.scalars(select(Document).where(Document.product_id == product_id))]

    def delete_document(self, document_id: str) -> Optional[str]:
        with self.session(write=True) as s:
            d = s.get(Document, document_id)
            if not d:
                return None
            tid = d.tenant_id
            s.delete(d)
            return tid

    # ---- chunks ----------------------------------------------------------------
    def replace_chunks(self, owner: Dict[str, Optional[str]], chunks: Sequence[Dict[str, Any]],
                       vectors: Optional[np.ndarray], embedder_id: str) -> int:
        """Replace the chunks of one owner (product / policy / document)."""
        key, value = next((k, v) for k, v in owner.items() if k in ("product_id", "policy_id", "document_id") and v)
        with self.session(write=True) as s:
            q = select(Chunk).where(getattr(Chunk, key) == value)
            if key == "product_id":
                q = q.where(Chunk.document_id.is_(None))  # attached documents keep their chunks
            for c in s.scalars(q):
                s.delete(c)
            for i, c in enumerate(chunks):
                s.add(Chunk(
                    kb_id=owner["kb_id"], tenant_id=owner["tenant_id"], product_id=owner.get("product_id"),
                    document_id=owner.get("document_id"), policy_id=owner.get("policy_id"),
                    store_id=owner.get("store_id"), doc_type=c["doc_type"], category=owner.get("category") or "",
                    text=c["text"], answer=c.get("answer", ""), embedder_id=embedder_id,
                    embedding=to_blob(vectors[i]) if vectors is not None else None,
                ))
            return len(chunks)

    def load_index(self, tenant_id: str) -> Tuple[List[IndexedChunk], Optional[np.ndarray], set]:
        with self.session() as s:
            rows = s.scalars(select(Chunk).where(Chunk.tenant_id == tenant_id)).all()
            chunks, vecs, embedders = [], [], set()
            dim = None
            for c in rows:
                v = from_blob(c.embedding)
                chunks.append(IndexedChunk(c.id, c.tenant_id, c.kb_id, c.product_id, c.store_id, c.doc_type,
                                           c.text, c.answer or "", c.category or ""))
                embedders.add(c.embedder_id or "")
                if v is not None and dim is None:
                    dim = v.shape[0]
                vecs.append(v)
            if not chunks:
                return [], None, embedders
            if dim is None or any(v is None or v.shape[0] != dim for v in vecs):
                return chunks, None, embedders  # mixed/missing vectors: keyword-only until re-indexed
            return chunks, np.vstack(vecs), embedders

    def chunk_texts_for_reindex(self, tenant_id: str) -> List[Tuple[str, str]]:
        with self.session() as s:
            return [(c.id, c.text) for c in s.scalars(select(Chunk).where(Chunk.tenant_id == tenant_id))]

    def set_chunk_vectors(self, ids: Sequence[str], vectors: np.ndarray, embedder_id: str) -> None:
        with self.session(write=True) as s:
            for cid, v in zip(ids, vectors):
                c = s.get(Chunk, cid)
                if c:
                    c.embedding, c.embedder_id = to_blob(v), embedder_id

    # ---- stats -----------------------------------------------------------------
    def stats(self, tenant_id: str) -> Dict[str, Any]:
        with self.session() as s:
            def n(model, *where):
                return s.scalar(select(func.count(model.id)).where(*where)) or 0
            embedders = [e or "" for e in s.scalars(select(Chunk.embedder_id).where(Chunk.tenant_id == tenant_id).distinct())]
            return {
                "products": n(Product, Product.tenant_id == tenant_id),
                "stores": n(Store, Store.tenant_id == tenant_id),
                "policies": n(Policy, Policy.tenant_id == tenant_id),
                "documents": n(Document, Document.tenant_id == tenant_id),
                "chunks": n(Chunk, Chunk.tenant_id == tenant_id),
                "faqs": n(Chunk, Chunk.tenant_id == tenant_id, Chunk.doc_type == "faq"),
                "embedders": embedders,
            }

    # ---- jobs --------------------------------------------------------------------
    def create_job(self, kind: str, title: str, tenant_id: str = "") -> Dict[str, Any]:
        with self.session(write=True) as s:
            j = Job(kind=kind, title=title, tenant_id=tenant_id, status="queued")
            s.add(j)
            s.flush()
            return self._job(j)

    def update_job(self, job_id: str, **fields) -> Dict[str, Any]:
        with self.session(write=True) as s:
            j = s.get(Job, job_id)
            for k, v in fields.items():
                setattr(j, k, v)
            s.flush()
            return self._job(j)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.session() as s:
            j = s.get(Job, job_id)
            return self._job(j) if j else None

    def list_jobs(self, tenant_id: str = "", limit: int = 30) -> List[Dict[str, Any]]:
        with self.session() as s:
            stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
            if tenant_id:
                stmt = stmt.where(Job.tenant_id == tenant_id)
            return [self._job(j) for j in s.scalars(stmt)]

    # ---- audit -----------------------------------------------------------------
    def audit(self, actor: str, action: str, target: str = "", detail: Optional[dict] = None) -> None:
        with self.session(write=True) as s:
            s.add(AuditLog(actor=actor or "", action=action, target=target, detail=detail or {}))

    def list_audit(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.session() as s:
            return [{"ts": _iso(a.ts), "actor": a.actor, "action": a.action, "target": a.target, "detail": a.detail}
                    for a in s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))]
