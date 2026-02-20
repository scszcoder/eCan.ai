"""
RAG Worker — Fargate task for indexing documents with RAG-Anything.

Environment variables (set by Lambda via ECS container overrides):
  RAG_BUCKET       – S3 bucket (default: ecan-rags)
  RAG_USER_DIR     – User directory (cognito sub or sanitised email)
  RAG_PID          – Product/service ID (default: "default")
  RAG_MODE         – "index" or "query" (default: index)
  OPENAI_API_KEY   – Required for LLM + embeddings
  OPENAI_BASE_URL  – Optional custom endpoint

Workflow (index mode):
  1. Download all docs from  s3://{RAG_BUCKET}/{RAG_USER_DIR}/{RAG_PID}/docs/
  2. Run RAG-Anything to parse + chunk + build knowledge graph
  3. Export chunks.json for Lambda keyword search fallback
  4. Upload working_dir artefacts back to S3 index prefix
  5. Update index_status.json with completion status
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

import boto3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rag_worker")

# ── env ─────────────────────────────────────────────────────────────────
RAG_BUCKET = os.environ.get("RAG_BUCKET", "ecan-rags")
RAG_USER_DIR = os.environ.get("RAG_USER_DIR", "")
RAG_PID = os.environ.get("RAG_PID", "default")
RAG_MODE = os.environ.get("RAG_MODE", "index")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", None)

# LLM model configuration
LLM_MODEL = os.environ.get("RAG_LLM_MODEL", "gpt-4o-mini")
VISION_MODEL = os.environ.get("RAG_VISION_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.environ.get("RAG_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = int(os.environ.get("RAG_EMBEDDING_DIM", "1536"))

s3 = boto3.client("s3")


def _registry_key() -> str:
    # Global per-user registry written by AppSync/Lambda
    return f"{RAG_USER_DIR}/doc_registry.json"


def load_doc_registry() -> dict:
    if not RAG_USER_DIR:
        return {"docs": {}}
    reg = s3_get_json(RAG_BUCKET, _registry_key())
    if not reg or not isinstance(reg, dict):
        return {"docs": {}}
    docs = reg.get("docs")
    if not isinstance(docs, dict):
        reg["docs"] = {}
    return reg


def _safe_categories(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace("|", ",").replace(";", ",").split(",")]
        return [p for p in parts if p]
    return [str(value).strip()]


# ── S3 helpers ──────────────────────────────────────────────────────────
def s3_download_dir(bucket: str, prefix: str, local_dir: str) -> list[str]:
    """Download all objects under prefix to local_dir. Returns list of local paths."""
    logger.info(f"s3_download_dir: listing s3://{bucket}/{prefix}")
    downloaded = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            size_mb = obj.get("Size", 0) / (1024 * 1024)
            if key.endswith("/"):
                continue
            rel = key[len(prefix):].lstrip("/")
            local_path = os.path.join(local_dir, rel)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            logger.info(f"Downloading s3://{bucket}/{key} ({size_mb:.2f} MB) → {local_path}")
            try:
                s3.download_file(bucket, key, local_path)
                downloaded.append(local_path)
            except Exception as e:
                logger.error(f"Failed to download s3://{bucket}/{key}: {e}")
                raise
    logger.info(f"s3_download_dir: downloaded {len(downloaded)} files from s3://{bucket}/{prefix}")
    return downloaded


def s3_upload_dir(local_dir: str, bucket: str, prefix: str) -> int:
    """Upload all files in local_dir to S3 under prefix. Returns count."""
    logger.info(f"s3_upload_dir: uploading {local_dir} → s3://{bucket}/{prefix}/")
    count = 0
    for root, _dirs, files in os.walk(local_dir):
        for f in files:
            local_path = os.path.join(root, f)
            rel = os.path.relpath(local_path, local_dir)
            key = f"{prefix}/{rel}".replace("\\", "/")
            size_mb = os.path.getsize(local_path) / (1024 * 1024)
            logger.info(f"Uploading {local_path} ({size_mb:.2f} MB) → s3://{bucket}/{key}")
            try:
                s3.upload_file(local_path, bucket, key)
                count += 1
            except Exception as e:
                logger.error(f"Failed to upload {local_path} → s3://{bucket}/{key}: {e}")
                raise
    logger.info(f"s3_upload_dir: uploaded {count} files to s3://{bucket}/{prefix}/")
    return count


def s3_put_json(bucket: str, key: str, data: dict):
    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(data, indent=2, ensure_ascii=False),
            ContentType="application/json",
        )
        logger.debug(f"s3_put_json: wrote s3://{bucket}/{key}")
    except Exception as e:
        logger.error(f"s3_put_json FAILED for s3://{bucket}/{key}: {e}")
        raise


def s3_get_json(bucket: str, key: str) -> dict | None:
    try:
        resp = s3.get_object(Bucket=bucket, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8"))
    except Exception:
        return None


# ── Index status helpers ────────────────────────────────────────────────
def _status_key():
    return f"{RAG_USER_DIR}/{RAG_PID}/index_status.json"


def update_status(status: str, message: str = "", progress: int = 0, **extra):
    payload = {
        "status": status,
        "message": message,
        "progress": progress,
        "updatedAt": _iso_now(),
        **extra,
    }
    s3_put_json(RAG_BUCKET, _status_key(), payload)
    logger.info(f"Status → {status} ({progress}%): {message}")


def _iso_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ── RAG-Anything setup ─────────────────────────────────────────────────
def build_rag(working_dir: str):
    """Create a RAGAnything instance with OpenAI models."""
    logger.info(f"build_rag: initializing RAGAnything in {working_dir}")
    logger.info(f"  LLM_MODEL={LLM_MODEL}, VISION_MODEL={VISION_MODEL}, "
                f"EMBEDDING_MODEL={EMBEDDING_MODEL}, EMBEDDING_DIM={EMBEDDING_DIM}")
    logger.info(f"  OPENAI_API_KEY={'set (' + OPENAI_API_KEY[:8] + '...)' if OPENAI_API_KEY else 'NOT SET'}")
    logger.info(f"  OPENAI_BASE_URL={OPENAI_BASE_URL or '(default)'}")
    from raganything import RAGAnything, RAGAnythingConfig
    from lightrag.llm.openai import openai_complete_if_cache, openai_embed
    from lightrag.utils import EmbeddingFunc

    api_key = OPENAI_API_KEY
    base_url = OPENAI_BASE_URL

    async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        return await openai_complete_if_cache(
            LLM_MODEL, prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=api_key,
            base_url=base_url,
            **kwargs,
        )

    async def vision_model_func(prompt, system_prompt=None, history_messages=[],
                                image_data=None, messages=None, **kwargs):
        if messages:
            return await openai_complete_if_cache(
                VISION_MODEL, "", messages=messages,
                api_key=api_key, base_url=base_url, **kwargs,
            )
        elif image_data:
            return await openai_complete_if_cache(
                VISION_MODEL, "",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
                    ],
                }],
                api_key=api_key, base_url=base_url, **kwargs,
            )
        else:
            return await llm_model_func(prompt, system_prompt, history_messages, **kwargs)

    embedding_func = EmbeddingFunc(
        embedding_dim=EMBEDDING_DIM,
        max_token_size=8192,
        func=lambda texts: openai_embed(
            texts, model=EMBEDDING_MODEL,
            api_key=api_key, base_url=base_url,
        ),
    )

    config = RAGAnythingConfig(
        working_dir=working_dir,
        parser="mineru",
        parse_method="auto",
        enable_image_processing=True,
        enable_table_processing=True,
        enable_equation_processing=True,
    )

    rag = RAGAnything(
        config=config,
        llm_model_func=llm_model_func,
        vision_model_func=vision_model_func,
        embedding_func=embedding_func,
    )
    logger.info("build_rag: RAGAnything instance created successfully")
    return rag


# ── Export chunks.json for Lambda keyword search ────────────────────────
def export_chunks_json(working_dir: str, output_path: str):
    """Read LightRAG text_chunks KV store and export as JSON array."""
    chunks_file = os.path.join(working_dir, "kv_store_text_chunks.json")
    chunks = []
    registry = load_doc_registry()
    reg_docs = registry.get("docs", {}) if isinstance(registry, dict) else {}
    logger.info(f"export_chunks_json: looking for {chunks_file}")
    if os.path.exists(chunks_file):
        logger.info(f"  Found KV store, size={os.path.getsize(chunks_file) / 1024:.1f} KB")
        with open(chunks_file, "r") as f:
            kv = json.load(f)
        for chunk_id, chunk_data in kv.items():
            text = ""
            source = ""
            metadata = {}
            if isinstance(chunk_data, dict):
                text = chunk_data.get("content", chunk_data.get("text", ""))
                source = chunk_data.get("source_id", chunk_data.get("source", ""))
                metadata = {k: v for k, v in chunk_data.items() if k not in ("content", "text")}
            elif isinstance(chunk_data, str):
                text = chunk_data
            # Attach registry metadata if we can identify the originating docKey.
            # For per-pid indexing, docs are downloaded from: s3://.../{RAG_USER_DIR}/{RAG_PID}/docs/<file>
            # LightRAG usually uses source_id similar to the file name/path.
            file_name = ""
            if source:
                file_name = str(source).split("/")[-1]
            elif isinstance(metadata, dict) and metadata.get("source_id"):
                file_name = str(metadata.get("source_id")).split("/")[-1]

            doc_key = ""
            if file_name:
                doc_key = f"{RAG_USER_DIR}/{RAG_PID}/docs/{file_name}"

            reg = reg_docs.get(doc_key) if doc_key and isinstance(reg_docs, dict) else None
            if isinstance(reg, dict):
                # Normalize/merge into chunk metadata
                metadata = {
                    **metadata,
                    "pid": reg.get("pid") or RAG_PID,
                    "fid": reg.get("fid"),
                    "version": reg.get("version"),
                    "format": reg.get("format"),
                    "categories": _safe_categories(reg.get("categories")),
                    "options": reg.get("options"),
                    "docKey": reg.get("docKey") or doc_key,
                }
            else:
                # At minimum, carry pid
                if isinstance(metadata, dict) and "pid" not in metadata:
                    metadata["pid"] = RAG_PID

            chunks.append({
                "id": chunk_id,
                "text": text,
                "source": source,
                "metadata": metadata,
            })
    else:
        logger.warning(f"  KV store file NOT found at {chunks_file} — listing working_dir contents:")
        for item in os.listdir(working_dir):
            logger.warning(f"    {item}")
    with open(output_path, "w") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=1)
    logger.info(f"Exported {len(chunks)} chunks to {output_path}")
    return len(chunks)


# ── Main index workflow ─────────────────────────────────────────────────
async def run_index():
    """Download docs → RAG-Anything index → upload artefacts → update status."""
    if not RAG_USER_DIR:
        logger.error("RAG_USER_DIR not set")
        update_status("error", "RAG_USER_DIR not set", progress=0)
        return

    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set")
        update_status("error", "OPENAI_API_KEY not set", progress=0)
        return

    docs_prefix = f"{RAG_USER_DIR}/{RAG_PID}/docs/"
    index_prefix = f"{RAG_USER_DIR}/{RAG_PID}/index"

    with tempfile.TemporaryDirectory(prefix="rag_work_") as tmpdir:
        docs_dir = os.path.join(tmpdir, "docs")
        working_dir = os.path.join(tmpdir, "rag_storage")
        output_dir = os.path.join(tmpdir, "parser_output")
        os.makedirs(docs_dir, exist_ok=True)
        os.makedirs(working_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        # 1. Download docs from S3
        update_status("indexing", "Downloading documents from S3", progress=5)
        downloaded = s3_download_dir(RAG_BUCKET, docs_prefix, docs_dir)
        if not downloaded:
            update_status("error", "No documents found to index", progress=0)
            return
        logger.info(f"Downloaded {len(downloaded)} documents")

        # 2. Run RAG-Anything
        update_status("indexing", f"Processing {len(downloaded)} documents with RAG-Anything", progress=15)
        t0 = time.time()
        try:
            logger.info("Creating RAG-Anything instance...")
            rag = build_rag(working_dir)
            logger.info(f"Starting process_folder_complete on {docs_dir} → {output_dir}")
            await rag.process_folder_complete(
                folder_path=docs_dir,
                output_dir=output_dir,
                parse_method="auto",
                recursive=True,
            )
            logger.info("process_folder_complete finished, finalizing storages...")
            update_status("indexing", "Finalizing knowledge graph storage", progress=70)
            await rag.finalize_storages()
            logger.info("finalize_storages completed")
        except Exception as e:
            logger.error(f"RAG-Anything processing failed: {e}\n{traceback.format_exc()}")
            update_status("error", f"Processing failed: {e}", progress=0)
            return
        elapsed = time.time() - t0
        logger.info(f"RAG-Anything processing completed in {elapsed:.1f}s")

        # 3. Export chunks for Lambda keyword search
        update_status("indexing", "Exporting search chunks", progress=80)
        chunks_path = os.path.join(working_dir, "chunks.json")
        chunk_count = export_chunks_json(working_dir, chunks_path)

        # 4. Upload working_dir artefacts to S3
        update_status("indexing", "Uploading index artefacts to S3", progress=85)
        file_count = s3_upload_dir(working_dir, RAG_BUCKET, index_prefix)
        logger.info(f"Uploaded {file_count} index files to s3://{RAG_BUCKET}/{index_prefix}/")

        # 5. Update status
        update_status(
            "ready",
            f"Indexed {len(downloaded)} docs → {chunk_count} chunks in {elapsed:.1f}s",
            progress=100,
            completedAt=_iso_now(),
            docCount=len(downloaded),
            chunkCount=chunk_count,
            processingTimeSec=round(elapsed, 1),
        )

    logger.info("Index workflow complete ✓")


# ── Entry point ─────────────────────────────────────────────────────────
def main():
    logger.info("=" * 60)
    logger.info("RAG Worker container starting")
    logger.info(f"  RAG_MODE       = {RAG_MODE}")
    logger.info(f"  RAG_BUCKET     = {RAG_BUCKET}")
    logger.info(f"  RAG_USER_DIR   = {RAG_USER_DIR}")
    logger.info(f"  RAG_PID        = {RAG_PID}")
    logger.info(f"  OPENAI_API_KEY = {'set (' + OPENAI_API_KEY[:8] + '...)' if OPENAI_API_KEY else 'NOT SET'}")
    logger.info(f"  LLM_MODEL      = {LLM_MODEL}")
    logger.info(f"  EMBEDDING_MODEL= {EMBEDDING_MODEL}")
    logger.info(f"  Python         = {sys.version}")
    logger.info("=" * 60)

    if RAG_MODE == "index":
        try:
            asyncio.run(run_index())
            logger.info("RAG Worker exiting normally")
        except Exception as e:
            logger.error(f"RAG Worker crashed: {e}\n{traceback.format_exc()}")
            update_status("error", f"Worker crashed: {e}", progress=0)
            sys.exit(1)
    else:
        logger.error(f"Unknown RAG_MODE: {RAG_MODE}")
        update_status("error", f"Unknown mode: {RAG_MODE}")
        sys.exit(1)


if __name__ == "__main__":
    main()
