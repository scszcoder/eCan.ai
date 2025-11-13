from __future__ import annotations

import threading
import time
import os
from queue import Queue, Empty
from typing import List, Optional, Dict, Any, Tuple

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

from utils.logger_helper import logger_helper as logger
from agent.memory.models import MemoryItem, RetrievalQuery, RetrievedMemory
from langchain_community.vectorstores import Chroma
from langchain_core.embeddings import FakeEmbeddings

from agent.memory.embedding_utils import EmbeddingFactory

class MemorySettings(BaseModel):
	"""Settings for procedural memory."""

	agent_id: str
	interval: int = 10
	config: Optional[dict] | None = None

DEFAULT_EPISODIC_SUMMERY_PROMPT = """
Given the provided messsages in the context, summarize dialogs, Your goal is simply to reduce 
the size of the context(tokens) as much as possible but still captures the essence of the 
tasks at hand, such that what was requested to search, what paramters are most critical to the component
being searched, what tools have been used and results, where have we searched, what have we found. what
intermediate goals have we achieved, what are the final results.
Context: {context}
"""

DEFAULT_PROCEDURAL_SUMMERY_PROMPT = """
Given the provided messsages in the context, summarize dialogs, Your goal is simply to reduce 
the size of the context(tokens) as much as possible but still captures the essence of the 
tasks at hand, such that what was requested to search, what paramters are most critical to the component
being searched, what tools have been used and results, where have we searched, what have we found. what
intermediate goals have we achieved, what are the final results.
Context: {context}
"""
class MemoryManager:
	"""Background memory manager that ingests items via a queue and
    persists them into a Chroma vector store per hierarchical namespace.

    Exposes retrieval and placeholder lifecycle hooks for episodic summaries,
    procedural accumulation, and compression/pruning.
    """
	def __init__(
        self,
        agent_id: str,
        persist_dir: str | None = None,
        embedding_model: str = None,
        embedding_provider: str = None,
        collection_prefix: str = "ecan_mem_",
		llm: BaseChatModel = None,
    ) -> None:
		self.agent_id = agent_id
		# Resolve persist directory to a user-writable location when not provided
		if persist_dir is None:
			try:
				from config.app_info import app_info
				persist_dir = os.path.join(app_info.appdata_path, "memory", "chroma")
			except Exception as e:
				# Do not fallback; provide clear error logging and stop initialization
				logger.error(f"[MemoryManager] Failed to resolve persist_dir from app_info.appdata_path: {e}")
				raise
		self.persist_dir = persist_dir
		os.makedirs(self.persist_dir, exist_ok=True)
		self.llm = llm
		
		# Get default embedding settings if not provided
		if embedding_provider is None or embedding_model is None:
			try:
				from app_context import AppContext
				main_window = AppContext.get_main_window()
				if main_window:
					general_settings = main_window.config_manager.general_settings
					if embedding_provider is None:
						embedding_provider = general_settings.default_embedding or "OpenAI"
					if embedding_model is None:
						embedding_model = general_settings.default_embedding_model or "text-embedding-3-small"
				else:
					# Fallback if main_window not available
					if embedding_provider is None:
						embedding_provider = "OpenAI"
					if embedding_model is None:
						embedding_model = "text-embedding-3-small"
			except Exception as e:
				logger.warning(f"[MemoryManager] Failed to get embedding settings, using defaults: {e}")
				if embedding_provider is None:
					embedding_provider = "OpenAI"
				if embedding_model is None:
					embedding_model = "text-embedding-3-small"
		
		# Initialize embeddings using EmbeddingFactory with settings from config
		try:
			self._embeddings = EmbeddingFactory.create_embeddings(
				provider_name=embedding_provider,
				model_name=embedding_model
			)
			logger.debug(f"[MemoryManager] Initialized embeddings for agent {agent_id} with provider={embedding_provider}, model={embedding_model}")
		except Exception as e:
			# Fallback to FakeEmbeddings if initialization fails
			self._embeddings = FakeEmbeddings(size=1536)
			logger.warning(f"[MemoryManager] Failed to initialize embeddings, using FakeEmbeddings: {e}")
		
		self.max_context_size = 65536
		self._collection_prefix = collection_prefix

		# One Chroma instance per namespace key (lazy init)
		self._stores: Dict[str, Chroma] = {}

		# Background worker
		self._queue: Queue[MemoryItem] = Queue()
		self._stop_event = threading.Event()
		self._thread: Optional[threading.Thread] = None

		# Tuning
		self._drain_batch_size = 32
		self._drain_interval_sec = 0.25

	# ---------- lifecycle ----------
	def start(self) -> None:
		if self._thread and self._thread.is_alive():
			return
		self._stop_event.clear()
		self._thread = threading.Thread(
            target=self._worker_loop,
            name=f"MemoryMgr-{self.agent_id}",
            daemon=True,
        )
		self._thread.start()
		logger.info(f"[MemoryManager] started for agent={self.agent_id}")

	def stop(self, timeout: float = 2.0) -> None:
		self._stop_event.set()
		if self._thread:
			self._thread.join(timeout=timeout)
		# Ensure Chroma persists to disk
		for _, store in self._stores.items():
			try:
				store.persist()
			except Exception:
				pass
		logger.info(f"[MemoryManager] stopped for agent={self.agent_id}")

	# ---------- enqueue ----------
	def put(self, item: MemoryItem) -> None:
		"""Enqueue a memory item to be persisted."""
		self._queue.put(item)

	# ---------- retrieval ----------
	def retrieve(self, rq: RetrievalQuery) -> List[RetrievedMemory]:
		store = self._get_store(rq.namespace)
		try:
			docs_scores = store.similarity_search_with_score(
                rq.query,
                k=rq.k,
                filter=rq.filters or {},
            )
		except TypeError:
			# Some chroma versions use 'where' instead of 'filter'
			docs_scores = store.similarity_search_with_score(
                rq.query,
                k=rq.k,
                where=rq.filters or {},
            )
		results: List[RetrievedMemory] = []
		for doc, score in docs_scores:
			results.append(
				RetrievedMemory(
					id=getattr(doc, "id", None),
					text=doc.page_content,
                    score=float(score),
                    metadata=doc.metadata or {},
                )
            )
		return results

	# ---------- placeholders for lifecycle management ----------
	def generate_episodic_summary(self) -> None:
		"""Placeholder: create episodic (summarized) memory from recent items.
		Wire to LangGraph summarization utilities later.
		"""

		logger.trace("[MemoryManager] generate_episodic_summary: placeholder executed")

	def accumulate_procedural_memory(self) -> None:
		"""Placeholder: detect flows/repetition and store procedural knowledge."""

		logger.trace("[MemoryManager] accumulate_procedural_memory: placeholder executed")

	def compress_and_prune(self) -> None:
		"""Placeholder: compress vectors, prune low-utility items, maintain budget."""

		logger.trace("[MemoryManager] compress_and_prune: placeholder executed")

	# ---------- internal ----------
	def _worker_loop(self) -> None:
		last_persist = time.time()
		batch: List[MemoryItem] = []
		while not self._stop_event.is_set():
			try:
				item = self._queue.get(timeout=self._drain_interval_sec)
				batch.append(item)
				if len(batch) >= self._drain_batch_size:
					self._drain(batch)
					batch = []
			except Empty:
				# time to drain partial batch
				if batch:
					self._drain(batch)
					batch = []

			# periodic persist & maintenance hooks
			now = time.time()
			if now - last_persist > 5.0:
				for _, store in self._stores.items():
					try:
						store.persist()
					except Exception:
						pass
				# run maintenance placeholders
				self.generate_episodic_summary()
				self.accumulate_procedural_memory()
				self.compress_and_prune()
				last_persist = now

		def _drain(self, items: List[MemoryItem]) -> None:
			# group by namespace tuple
			by_ns: Dict[Tuple[str, ...], List[MemoryItem]] = {}
			for it in items:
				by_ns.setdefault(it.namespace, []).append(it)

			for ns, group in by_ns.items():
				store = self._get_store(ns)
				texts = [g.text for g in group]
				ns_key = self._namespace_key(ns)
				metadatas = [
                dict(g.metadata or {}, agent_id=self.agent_id, namespace=ns, namespace_key=ns_key)
                for g in group
				]
				ids = [g.id for g in group] if any(g.id for g in group) else None
				try:
					store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
				except Exception as e:
					logger.error(f"[MemoryManager] add_texts failed ns={ns}: {e}")

	def _get_store(self, namespace: Tuple[str, ...]) -> Chroma:
		ns_key = self._namespace_key(namespace)
		if ns_key in self._stores:
			return self._stores[ns_key]
		collection_name = f"{self._collection_prefix}{self.agent_id}_{ns_key}"
		store = Chroma(
            collection_name=collection_name,
            embedding_function=self._embeddings,
            persist_directory=self.persist_dir,
        )
		self._stores[ns_key] = store
		return store

	def _namespace_key(self, namespace: Tuple[str, ...]) -> str:
		"""Create a stable string key for a hierarchical namespace tuple.
		Use double underscores to avoid common collisions and keep readable.
		"""
		try:
			parts = [str(p).strip().replace("__", "_") for p in namespace]
			return "__".join(parts) if parts else "default"
		except Exception:
			return "default"


	def update_embeddings(self, provider_name: str = "OpenAI", model_name: str = "text-embedding-3-small"):
		"""Update the embeddings instance and recreate all Chroma stores.
		
		This method should be called when embedding settings change to ensure
		all existing stores use the new embeddings.
		
		Args:
			provider_name: Name of the embedding provider
			model_name: Model name to use
		"""
		try:
			logger.info(f"[MemoryManager] Updating embeddings to {provider_name}/{model_name}")
			
			# Create new embeddings instance using EmbeddingFactory
			new_embeddings = EmbeddingFactory.create_embeddings(provider_name, model_name)
			
			# Update the embeddings instance
			self._embeddings = new_embeddings
			
			# Recreate all Chroma stores with new embeddings
			# We need to persist old stores first, then recreate them
			old_stores = {}
			for ns_key, store in self._stores.items():
				try:
					store.persist()
					old_stores[ns_key] = store
				except Exception as e:
					logger.warning(f"[MemoryManager] Failed to persist store {ns_key}: {e}")
			
			# Clear existing stores - they will be recreated on next access
			self._stores.clear()
			
			# logger.info(f"[MemoryManager] Updated embeddings and cleared {len(old_stores)} stores")
			
		except Exception as e:
			logger.error(f"[MemoryManager] Error updating embeddings: {e}", exc_info=True)

	def move_item(self, doc_id: str, old_ns: Tuple[str, ...], new_ns: Tuple[str, ...]) -> None:
		"""Move a single item by id from old_ns collection to new_ns collection.
		Fetch the document and metadata via low-level Chroma get, best-effort delete
		from old_ns, then reinsert into new_ns with updated namespace metadata.
		"""
		if not doc_id:
			return

		old_store = self._get_store(old_ns)
		# Fetch doc+metadata by id
		try:
			client = old_store._collection  # caution: internal API
			rec = client.get(ids=[doc_id], include=["documents", "metadatas"])
			docs = rec.get("documents") or []
			metas = rec.get("metadatas") or []
			if not docs:
				return
			text = docs[0]
			meta = (metas[0] or {}) if metas else {}
		except Exception:
			raise

		# Best-effort delete from old collection
		try:
			old_store.delete(ids=[doc_id])
		except Exception:
			pass

		# Insert into new collection with updated namespace metadata
		ns_key = self._namespace_key(new_ns)
		new_store = self._get_store(new_ns)
		new_store.add_texts(
			texts=[text],
			metadatas=[{**meta, "namespace": new_ns, "namespace_key": ns_key}],
			ids=[doc_id],
		)

def move_items(self, doc_ids: List[str], old_ns: Tuple[str, ...], new_ns: Tuple[str, ...]) -> None:
	"""Move multiple items by id from old_ns collection to new_ns collection.
	Fetch documents/metadatas in bulk via low-level Chroma get, best-effort delete
	from old_ns, then reinsert into new_ns with updated namespace metadata.
	"""
	if not doc_ids:
		return

	old_store = self._get_store(old_ns)
	# Fetch in bulk using low-level collection API
	try:
		client = old_store._collection  # caution: internal API
		rec = client.get(ids=doc_ids, include=["ids", "documents", "metadatas"])
		ids_found = rec.get("ids") or []
		docs = rec.get("documents") or []
		metas = rec.get("metadatas") or []
		# Align by index; drop not-found docs
		triples = [(i, d, m) for i, d, m in zip(ids_found, docs, metas) if d is not None]
		if not triples:
			return
	except Exception:
		raise

	# Best-effort delete from old collection
	try:
		old_store.delete(ids=[i for i, _, _ in triples])
	except Exception:
		pass

	# Insert into new namespace
	ns_key = self._namespace_key(new_ns)
	new_store = self._get_store(new_ns)
	new_store.add_texts(
		texts=[d for _, d, _ in triples],
		metadatas=[{**(m or {}), "namespace": new_ns, "namespace_key": ns_key} for _, _, m in triples],
		ids=[i for i, _, _ in triples],
	)