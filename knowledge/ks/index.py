"""
Embedded hybrid index: BM25 keyword search + vector search, fused with
reciprocal rank fusion, with metadata pre-filtering.

Filtering happens BEFORE scoring, so a product-scoped query can only ever
return that product's chunks. This is the in-process backend for desktop and
single-merchant use; PostgreSQL/pgvector and Milvus implement the same
``search`` contract on servers (docs/RAG_ENTERPRISE_PLAN.md §3.5).
"""
from __future__ import annotations

import math
import threading
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from knowledge.ks.text import signal_terms, tokenize

RRF_K = 60


@dataclass
class IndexedChunk:
    id: str
    tenant_id: str
    kb_id: str
    product_id: Optional[str]
    store_id: Optional[str]
    doc_type: str
    text: str
    answer: str = ""
    category: str = ""


@dataclass
class Hit:
    chunk: IndexedChunk
    score: float            # fused score (RRF)
    cosine: float           # raw vector similarity, the confidence signal
    bm25: float             # raw keyword score
    matched_terms: List[str] = field(default_factory=list)
    coverage: float = 0.0   # share of the query's distinctive terms found in the chunk

    @property
    def relevance(self) -> float:
        """One 0..1 relevance signal: vector similarity or keyword coverage."""
        return max(self.cosine, 0.7 * self.coverage)


class HybridIndex:
    def __init__(self, k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self._lock = threading.RLock()
        self._chunks: List[IndexedChunk] = []
        self._vecs: Optional[np.ndarray] = None
        self._tf: List[Counter] = []
        self._len: np.ndarray = np.zeros(0)
        self._df: Counter = Counter()
        self._avg_len = 0.0

    def __len__(self) -> int:
        return len(self._chunks)

    def build(self, chunks: Sequence[IndexedChunk], vectors: Optional[np.ndarray]) -> None:
        with self._lock:
            self._chunks = list(chunks)
            self._vecs = None if vectors is None or len(chunks) == 0 else np.asarray(vectors, dtype=np.float32)
            self._tf = [Counter(tokenize(c.text + " " + c.answer)) for c in self._chunks]
            self._len = np.array([sum(tf.values()) for tf in self._tf], dtype=np.float32)
            self._df = Counter()
            for tf in self._tf:
                self._df.update(tf.keys())
            self._avg_len = float(self._len.mean()) if len(self._len) else 0.0

    def _bm25(self, q_tokens: List[str], rows: np.ndarray) -> np.ndarray:
        n = len(self._chunks)
        scores = np.zeros(len(rows), dtype=np.float32)
        if not q_tokens or n == 0:
            return scores
        for term in set(q_tokens):
            df = self._df.get(term, 0)
            if df == 0:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for j, r in enumerate(rows):
                tf = self._tf[r].get(term, 0)
                if tf:
                    denom = tf + self.k1 * (1 - self.b + self.b * self._len[r] / (self._avg_len or 1))
                    scores[j] += idf * tf * (self.k1 + 1) / denom
        return scores

    def search(
        self,
        query: str,
        query_vec: Optional[np.ndarray],
        where: Callable[[IndexedChunk], bool],
        k: int = 20,
    ) -> List[Hit]:
        with self._lock:
            rows = np.array([i for i, c in enumerate(self._chunks) if where(c)], dtype=np.int64)
            if len(rows) == 0:
                return []
            q_tokens = tokenize(query)
            bm25 = self._bm25(q_tokens, rows)
            if query_vec is not None and self._vecs is not None:
                cos = self._vecs[rows] @ np.asarray(query_vec, dtype=np.float32).reshape(-1)
            else:
                cos = np.zeros(len(rows), dtype=np.float32)

            fused = np.zeros(len(rows), dtype=np.float32)
            for scores, enabled in ((cos, query_vec is not None), (bm25, bool(q_tokens))):
                if not enabled:
                    continue
                order = np.argsort(-scores, kind="stable")
                for rank, j in enumerate(order):
                    # Keyword ranks only count when the term actually matched.
                    if scores is bm25 and scores[j] <= 0:
                        continue
                    fused[j] += 1.0 / (RRF_K + rank + 1)

            top = np.argsort(-fused, kind="stable")[:k]
            q_terms = signal_terms(q_tokens)
            hits = []
            for j in top:
                if fused[j] <= 0:
                    continue
                r = int(rows[j])
                matched = [t for t in q_terms if t in self._tf[r]]
                coverage = len(matched) / len(q_terms) if q_terms else 0.0
                hits.append(Hit(self._chunks[r], float(fused[j]), float(cos[j]), float(bm25[j]), matched, coverage))
            return hits


class IndexCache:
    """One HybridIndex per tenant, rebuilt lazily after writes."""

    def __init__(self, loader: Callable[[str], tuple]):
        self._loader = loader
        self._lock = threading.Lock()
        self._indexes: Dict[str, HybridIndex] = {}
        self._dirty: set = set()

    def invalidate(self, tenant_id: str) -> None:
        with self._lock:
            self._dirty.add(tenant_id)

    def get(self, tenant_id: str) -> HybridIndex:
        with self._lock:
            idx = self._indexes.get(tenant_id)
            if idx is not None and tenant_id not in self._dirty:
                return idx
        chunks, vectors = self._loader(tenant_id)
        idx = HybridIndex()
        idx.build(chunks, vectors)
        with self._lock:
            self._indexes[tenant_id] = idx
            self._dirty.discard(tenant_id)
        return idx
