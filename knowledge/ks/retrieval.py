"""
Path A: fast product Q&A retrieval (docs/RAG_ENTERPRISE_PLAN.md §3.6).

  Tier 0  product card -> product record facts + store policies   (no search)
  Tier 1  FAQ match within the product / merchant scope
  Tier 2  hybrid search filtered to the product (+ merchant-wide policy text)
  Tier 3  no product: search product summaries of the store's catalog

No LLM call happens here. Scope filtering is applied before scoring, so a
question about product X can only see product X's chunks plus the store's
policies; another merchant's data is never in the candidate set.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from knowledge.ks.index import Hit
from knowledge.ks.text import (
    POLICY_TOPIC_LABELS, attribute_family, detect_attribute_families, detect_topics, signal_terms, tokenize,
)

# Cosine thresholds differ by embedder family: the hashing embedder's scores
# are lexical and run lower than a neural model's.
FAQ_DIRECT = {"hashing": 0.62, "neural": 0.80}
RELEVANT = {"hashing": 0.18, "neural": 0.45}


def _faq_question(h: Hit) -> str:
    return h.chunk.text.split("】", 1)[-1]


def _faq_relevance(h: Hit, q_terms: List[str]) -> float:
    """FAQ relevance judged on the question only: the chunk text also carries
    the product title, which must not make every FAQ of that product match."""
    if not q_terms:
        return h.cosine
    q_tokens = set(tokenize(_faq_question(h)))
    coverage = sum(1 for t in q_terms if t in q_tokens) / len(q_terms)
    return max(h.cosine, 0.7 * coverage) if coverage > 0 else min(h.cosine, 0.3)


def _family(embedder_id: str) -> str:
    return "hashing" if embedder_id.startswith("hashing") else "neural"


@dataclass
class Retrieval:
    query: str
    tier: int = 0
    tenant_id: str = ""
    store: Optional[Dict[str, Any]] = None
    product: Optional[Dict[str, Any]] = None
    facts: List[Dict[str, str]] = field(default_factory=list)
    policies: List[Dict[str, Any]] = field(default_factory=list)
    faq: List[Dict[str, Any]] = field(default_factory=list)
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    timings_ms: Dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    should_answer: bool = False
    reason: str = ""
    scope: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query, "tier": self.tier, "tenant_id": self.tenant_id, "store": self.store,
            "product": _product_brief(self.product) if self.product else None,
            "facts": self.facts, "policies": self.policies, "faq": self.faq, "chunks": self.chunks,
            "candidates": self.candidates, "timings_ms": self.timings_ms,
            "confidence": round(self.confidence, 3), "should_answer": self.should_answer,
            "reason": self.reason, "scope": self.scope, "context": self.context_text(),
            "sensitivity": self.scope.get("sensitivity", "internal"),
        }

    def context_text(self) -> str:
        """Labelled context block for the answering LLM."""
        parts: List[str] = []
        if self.product:
            p = self.product
            parts.append(f"[商品] {p.get('title')}（编码 {p.get('code')}）")
            if self.facts:
                parts.append("[商品信息] " + "；".join(f"{f['key']}:{f['value']}" for f in self.facts))
        for faq in self.faq[:2]:
            parts.append(f"[常见问题] 问:{faq['question']} 答:{faq['answer']}")
        for pol in self.policies:
            scope = "店铺规则" if not pol.get("inherited") else "商家通用规则"
            parts.append(f"[{scope}·{POLICY_TOPIC_LABELS.get(pol['topic'], pol['topic'])}] {pol['text']}")
        for c in self.chunks[:5]:
            parts.append(f"[资料] {c['text']}")
        if self.candidates:
            parts.append("[可能相关商品] " + "；".join(c["title"] for c in self.candidates[:5]))
        return "\n".join(parts)


def _product_brief(p: Dict[str, Any]) -> Dict[str, Any]:
    return {k: p.get(k) for k in ("id", "code", "title", "category", "brand")}


def product_facts(product: Dict[str, Any], query: str) -> List[Dict[str, str]]:
    """Attributes relevant to the question, from the structured record."""
    families = set(detect_attribute_families(query))
    q = query.lower()
    q_terms = set(signal_terms(tokenize(query)))
    facts: List[Dict[str, str]] = []
    for key, value in (product.get("attributes") or {}).items():
        fam = attribute_family(key)
        # Merchant-defined keys (保温时长, 续航, 颗粒数) match on shared terms.
        key_terms = set(signal_terms(tokenize(key)))
        if (fam and fam in families) or key.lower() in q or (key_terms & q_terms):
            facts.append({"key": key, "value": str(value), "source": "attribute"})
    if "size" in families and product.get("size_chart", {}).get("rows"):
        from knowledge.ks.chunking import render_size_chart
        facts.append({"key": "尺码表", "value": render_size_chart(product["size_chart"]).replace("\n", " | "),
                      "source": "size_chart"})
    if "care" in families and product.get("care"):
        facts.append({"key": "洗涤保养", "value": product["care"], "source": "care"})
    if "color" in families and product.get("variants"):
        colors = sorted({v.get("颜色") for v in product["variants"] if v.get("颜色")})
        if colors and not any(f["key"] == "可选颜色" for f in facts):
            facts.append({"key": "可选颜色", "value": "、".join(colors), "source": "variants"})
    return facts


class ProductRetriever:
    def __init__(self, store, index_cache, embedder):
        self.store = store
        self.indexes = index_cache
        self.embedder = embedder

    def retrieve(self, tenant_id: str, query: str, store_ref: str = "", platform_item_id: str = "",
                 product_id: str = "", k: int = 5, allowed_kbs: Optional[set] = None) -> Retrieval:
        t0 = time.perf_counter()
        r = Retrieval(query=query, tenant_id=tenant_id)
        fam = _family(getattr(self.embedder, "id", ""))

        def mark(stage: str, since: float) -> float:
            now = time.perf_counter()
            r.timings_ms[stage] = round((now - since) * 1000, 1)
            return now

        # ---- scope ---------------------------------------------------------
        store = self.store.find_store(tenant_id, store_ref) if store_ref else None
        store_id = store["id"] if store else None
        if not product_id and platform_item_id:
            hit = self.store.resolve_listing(tenant_id, platform_item_id, store_id)
            if hit:
                product_id = hit[0]
                if store is None:  # the listing tells us which store the chat is in
                    store = self.store.get_store(hit[1])
                    store_id = hit[1]
        r.store = store
        product = self.store.get_product(product_id) if product_id else None
        if product and product["tenant_id"] != tenant_id:
            product = None  # never cross tenants, even with a guessed id
        r.product = product
        r.scope = {"tenant_id": tenant_id, "store_id": store_id, "product_id": product["id"] if product else None,
                   "platform_item_id": platform_item_id or None, "sensitivity": "internal"}
        t = mark("scope", t0)

        # ---- tier 0: facts + policies ---------------------------------------
        topics = detect_topics(query)
        policies = self.store.effective_policies(tenant_id, store_id)
        r.policies = [policies[tp] for tp in topics if tp in policies]
        if product:
            r.facts = product_facts(product, query)
        t = mark("tier0_facts", t)

        # ---- tier 1/2: search -----------------------------------------------
        index = self.indexes.get(tenant_id)
        qvec = None
        if len(index):
            qvec = self.embedder.embed([query])[0]
        t = mark("embed_query", t)

        pid = product["id"] if product else None
        store_products = self.store.store_product_ids(store_id) if store_id else None

        def in_scope(c) -> bool:
            if c.tenant_id != tenant_id:
                return False
            if allowed_kbs is not None and c.kb_id not in allowed_kbs:
                return False
            if c.doc_type == "policy":
                return False  # policies come from the structured lookup above
            if pid:
                return c.product_id == pid or c.product_id is None
            if store_products is not None and c.product_id is not None:
                return c.product_id in store_products
            return True

        hits: List[Hit] = index.search(query, qvec, in_scope, k=20) if len(index) else []
        faq_hits = [h for h in hits if h.chunk.doc_type == "faq"]
        q_terms = signal_terms(tokenize(query))
        faq_scored = sorted(((h, _faq_relevance(h, q_terms)) for h in faq_hits), key=lambda x: -x[1])
        faq_scored = [(h, sc) for h, sc in faq_scored if sc >= RELEVANT[fam]]
        r.faq = [{"question": _faq_question(h), "answer": h.chunk.answer,
                  "score": round(sc, 3), "product_id": h.chunk.product_id} for h, sc in faq_scored[:3]]
        other = [h for h in hits if h.chunk.doc_type != "faq"]
        r.chunks = [{"text": h.chunk.text, "doc_type": h.chunk.doc_type, "product_id": h.chunk.product_id,
                     "score": round(h.relevance, 3), "keyword_score": round(h.bm25, 2),
                     "matched_terms": h.matched_terms[:8], "chunk_id": h.chunk.id} for h in other[:k]]
        t = mark("search", t)

        # ---- tier 3: product candidates when no card -------------------------
        if not product:
            best: Dict[str, float] = {}
            for h in hits:
                if h.chunk.product_id and h.relevance >= RELEVANT[fam]:
                    best[h.chunk.product_id] = max(best.get(h.chunk.product_id, 0.0), h.relevance)
            for p_id in sorted(best, key=lambda x: -best[x])[:5]:
                p = self.store.get_product(p_id)
                if p:
                    r.candidates.append({"id": p["id"], "title": p["title"], "code": p["code"],
                                         "score": round(best[p_id], 3)})
        mark("candidates", t)

        # ---- decide tier + confidence ------------------------------------------
        top_faq = faq_scored[0][1] if faq_scored else 0.0
        top_chunk = max((h.relevance for h in other), default=0.0)
        if product and r.facts:
            r.tier, r.confidence = 0, 0.9
        elif top_faq >= FAQ_DIRECT[fam]:
            r.tier, r.confidence = 1, min(0.95, 0.6 + top_faq / 2)
        elif top_chunk >= RELEVANT[fam] or r.policies:
            r.tier = 2 if product else 3
            r.confidence = max(0.75 if r.policies else 0.0, min(0.85, 0.35 + top_chunk))
        else:
            r.tier = 2 if product else 3
            r.confidence = min(0.4, top_chunk)
        if r.policies and r.tier != 1:
            r.confidence = max(r.confidence, 0.8)
        r.should_answer = r.confidence >= 0.5
        if not r.should_answer:
            r.reason = "no_relevant_knowledge"
        r.timings_ms["total"] = round((time.perf_counter() - t0) * 1000, 1)
        return r
