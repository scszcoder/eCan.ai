"""
Embedders for the Knowledge Service.

Every embedder has a stable ``id``; chunks record the id they were embedded
with so a model change is detected and the KB is re-embedded instead of
silently mixing vector spaces.

- ``HashingEmbedder``: deterministic character n-gram hashing. No model, no
  network. Used offline, in tests, and as the fallback when no embedding
  provider is configured.
- ``LangChainEmbedder``: wraps the app's configured embedding provider
  (Settings > default embedding), the same one agent memory uses.
"""
from __future__ import annotations

import hashlib
import unicodedata
from typing import List, Optional, Protocol, Sequence

import numpy as np

from utils.logger_helper import logger_helper as logger


class Embedder(Protocol):
    id: str
    dim: int

    def embed(self, texts: Sequence[str]) -> np.ndarray:  # (n, dim) float32, L2-normalised
        ...


def _normalise(mat: np.ndarray) -> np.ndarray:
    mat = np.asarray(mat, dtype=np.float32)
    if mat.ndim == 1:
        mat = mat[None, :]
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


class HashingEmbedder:
    """Signed feature hashing over character 1-3 grams."""

    def __init__(self, dim: int = 512):
        self.dim = dim
        self.id = f"hashing-ngram-v1:{dim}"

    def _features(self, text: str) -> List[str]:
        s = unicodedata.normalize("NFKC", text or "").lower()
        s = "".join(ch for ch in s if not ch.isspace())
        feats: List[str] = []
        for n in (1, 2, 3):
            feats.extend(s[i:i + n] for i in range(max(0, len(s) - n + 1)))
        return feats

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for feat in self._features(text):
                h = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
                idx = int.from_bytes(h[:4], "little") % self.dim
                sign = 1.0 if h[4] & 1 else -1.0
                # Longer n-grams are more specific; weight them up.
                out[row, idx] += sign * (1.0 + 0.5 * (len(feat) - 1))
        return _normalise(out)


class LangChainEmbedder:
    """Adapter for a langchain ``Embeddings`` instance."""

    def __init__(self, embeddings, provider: str, model: str, batch_size: int = 32):
        self._emb = embeddings
        self.id = f"{provider}:{model}"
        self.batch_size = batch_size
        self.dim = 0

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        rows: List[List[float]] = []
        for i in range(0, len(texts), self.batch_size):
            rows.extend(self._emb.embed_documents(list(texts[i:i + self.batch_size])))
        mat = _normalise(np.asarray(rows, dtype=np.float32)) if rows else np.zeros((0, self.dim), np.float32)
        if mat.size:
            self.dim = mat.shape[1]
        return mat


def resolve_app_embedder(main_window=None) -> Embedder:
    """The app's default embedding provider, or the hashing fallback."""
    try:
        if main_window is None:
            from app_context import AppContext
            main_window = AppContext.get_main_window()
        settings = main_window.config_manager.general_settings if main_window else None
        provider = getattr(settings, "default_embedding", None) if settings else None
        model = getattr(settings, "default_embedding_model", None) if settings else None
        if provider and model:
            from agent.memory.embedding_utils import EmbeddingFactory
            emb = EmbeddingFactory.create_embeddings(provider_name=provider, model_name=model)
            if type(emb).__name__ != "FakeEmbeddings":
                return LangChainEmbedder(emb, provider, model)
    except Exception as e:
        logger.warning(f"[KS] Embedding provider unavailable, using hashing embedder: {e}")
    return HashingEmbedder()


def to_blob(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_blob(blob: Optional[bytes]) -> Optional[np.ndarray]:
    if not blob:
        return None
    return np.frombuffer(blob, dtype=np.float32)


class OpenAICompatibleEmbedder:
    """Embeddings from any OpenAI-compatible /v1/embeddings endpoint: vLLM or
    TEI on the private GPU server, or a cloud provider (DashScope, OpenAI)."""

    def __init__(self, base_url: str, model: str, api_key: str = "", batch_size: int = 32,
                 timeout: float = 60.0, verify_tls: bool = True):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.batch_size = batch_size
        self.timeout = timeout
        self.verify_tls = verify_tls
        self.id = f"openai-compatible:{model}"
        self.dim = 0

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        import httpx
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        url = self.base_url + ("/embeddings" if self.base_url.endswith("/v1") else "/v1/embeddings")
        rows: List[List[float]] = []
        with httpx.Client(timeout=self.timeout, verify=self.verify_tls) as client:
            for i in range(0, len(texts), self.batch_size):
                resp = client.post(url, headers=headers,
                                   json={"model": self.model, "input": list(texts[i:i + self.batch_size])})
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda d: d.get("index", 0))
                rows.extend(d["embedding"] for d in data)
        mat = _normalise(np.asarray(rows, dtype=np.float32)) if rows else np.zeros((0, self.dim), np.float32)
        if mat.size:
            self.dim = mat.shape[1]
        return mat
