# RAG Worker — Fargate Document Indexing Service

Fargate task that indexes uploaded documents using [RAG-Anything](https://github.com/HKUDS/RAG-Anything) (LightRAG + MinerU parser) for the eCan.ai web app.

## Architecture

```
Frontend (RAG page)
  │
  ├─ Upload files ──► AppSync mutation ──► Lambda generates presigned S3 PUT URLs
  │                                         └─► Files uploaded directly to S3 (ecan-rags bucket)
  │
  ├─ "Build Index" ──► AppSync mutation ──► Lambda launches this Fargate task
  │                                         └─► Downloads docs, runs RAG-Anything, uploads index
  │
  └─ Query ──────────► AppSync query ───► Lambda keyword search over chunks.json
```

### S3 Bucket Layout (`ecan-rags`)

```
{cognito_sub}/{pid}/
├── docs/                  # Uploaded source documents (PDF, DOCX, images, etc.)
│   ├── report.pdf
│   └── data.xlsx
├── index/                 # RAG-Anything output artefacts
│   ├── chunks.json        # Exported text chunks (Lambda keyword search fallback)
│   ├── vdb_chunks.json    # nano-vectordb chunk index
│   ├── vdb_entities.json  # nano-vectordb entity index
│   ├── vdb_relationships.json
│   ├── graph_chunk_entity_relation.graphml  # Knowledge graph
│   ├── kv_store_full_docs.json
│   ├── kv_store_text_chunks.json
│   └── ...
├── manifest.json          # Document tracking manifest
└── index_status.json      # Indexing status (status, taskArn, docCount, etc.)
```

- `{cognito_sub}` — User's Cognito identity sub (e.g. `dbcabea3-1fcb-461b-abe9-df54723db582`)
- `{pid}` — Product/service ID, or `"default"` if not specified

## Components

### 1. Fargate Worker (`main.py`)

The worker runs as a single-shot ECS Fargate task:

1. **Downloads** all documents from `s3://ecan-rags/{userDir}/{pid}/docs/`
2. **Processes** them with RAG-Anything (`process_folder_complete`)
   - MinerU parser extracts text, tables, images, equations from PDFs
   - LightRAG builds knowledge graph + vector indexes
3. **Exports** `chunks.json` for Lambda keyword search fallback
4. **Uploads** all index artefacts to `s3://ecan-rags/{userDir}/{pid}/index/`
5. **Updates** `index_status.json` with completion status

#### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `RAG_BUCKET` | No | `ecan-rags` | S3 bucket for RAG data |
| `RAG_USER_DIR` | **Yes** | — | User directory (Cognito sub) |
| `RAG_PID` | No | `default` | Product/service ID |
| `RAG_MODE` | No | `index` | Operation mode |
| `OPENAI_API_KEY` | **Yes** | — | For LLM + embeddings |
| `OPENAI_BASE_URL` | No | — | Custom API endpoint |
| `RAG_LLM_MODEL` | No | `gpt-4o-mini` | LLM model for extraction |
| `RAG_VISION_MODEL` | No | `gpt-4o-mini` | Vision model for images |
| `RAG_EMBEDDING_MODEL` | No | `text-embedding-3-small` | Embedding model |
| `RAG_EMBEDDING_DIM` | No | `1536` | Embedding dimensions |

### 2. Lambda Handlers (`agentScheduler/index.js`)

Seven GraphQL resolvers added to the agentScheduler Lambda:

**Mutations:**
- `ragRequestUploadURLs` — Generates presigned S3 PUT URLs for file uploads
- `ragConfirmUploads` — Marks documents as uploaded in `manifest.json`
- `ragTriggerIndex` — Launches this Fargate task via ECS `RunTask`
- `ragDeleteDocs` — Deletes documents from S3 and updates manifest

**Queries:**
- `ragQuery` — Keyword search over `chunks.json` (fallback until full vector search)
- `ragListDocs` — Lists user's uploaded documents from manifest
- `ragGetIndexStatus` — Returns current indexing status

#### Lambda Environment Variables

| Variable | Default | Description |
|---|---|---|
| `RAG_BUCKET` | `ecan-rags` | S3 bucket |
| `RAG_ECS_CLUSTER` | (from `ECS_CLUSTER`) | ECS cluster ARN |
| `RAG_ECS_TASK_DEF` | — | ECS task definition for RAG worker |
| `RAG_ECS_SUBNETS` | (from `ECS_SUBNETS`) | Comma-separated subnet IDs |
| `RAG_ECS_SECURITY_GROUPS` | (from `ECS_SECURITY_GROUPS`) | Comma-separated SG IDs |

### 3. Frontend

- **Page:** `gui_v2/src/pages/RAG/RAGDocuments.tsx` — Drag-and-drop upload, document table, index controls, query interface
- **Store:** `gui_v2/src/stores/ragStore.ts` — Zustand store (fetchDocs, uploadFiles, triggerIndex, deleteDocs, query)
- **Route:** `/rag` with sidebar nav item "RAG Documents"
- **GraphQL:** 4 mutations + 3 queries in `gui_v2/src/services/api/api-config.ts`

### 4. AppSync Schema

Types defined in `scripts/schema.graphql`:
- Input: `RAGUploadRequestInput`, `RAGQueryInput`, `RAGDeleteDocsInput`
- Output: `RAGUploadURL`, `RAGDocument`, `RAGChunk`, `RAGQueryResult`, `RAGIndexStatus`
- All types use `@aws_api_key @aws_cognito_user_pools` auth directives

## Build & Deploy

### Docker Image

```bash
# Build locally
./build.sh

# Build and push to ECR
./build.sh --push

# Custom tag
IMAGE_TAG=v1.0.0 ./build.sh --push
```

### ECS Task Definition

Register a task definition with:
- **Container name:** `ecan-rag-worker`
- **Image:** `{account}.dkr.ecr.us-east-1.amazonaws.com/ecan-rag-worker:latest`
- **CPU/Memory:** 1024/4096 (or higher for large document sets)
- **Environment:** `OPENAI_API_KEY` (required)
- **Task role:** Needs `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `s3:DeleteObject` on `ecan-rags`

Then set `RAG_ECS_TASK_DEF` on the agentScheduler Lambda.

### Lambda Deployment

```bash
cd lambda_functions/agentScheduler
./build_lambda.sh --deploy
```

### Schema Deployment

```bash
aws appsync start-schema-creation \
  --api-id ydusqd3wgfb6loiu2daej6qa6y \
  --definition "$(base64 -w0 scripts/schema.graphql)" \
  --profile maipps8 --region us-east-1
```

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `raganything` | ≥1.2.9 | Multimodal RAG (LightRAG + MinerU) |
| `lightrag-hku` | ≥1.0.0 | Knowledge graph RAG engine |
| `faiss-cpu` | ≥1.8.0 | Vector similarity search |
| `openai` | ≥1.30.0 | LLM + embedding API |
| `boto3` | ≥1.34.0 | AWS S3 access |
| `Pillow` | ≥10.0.0 | Image processing |
| `tiktoken` | ≥0.7.0 | Token counting |

## Flow Detail

```
User clicks "Upload Files"
  → Frontend opens file picker
  → Calls ragRequestUploadURLs mutation with file metadata
  → Lambda returns presigned S3 PUT URLs
  → Frontend uploads files directly to S3 via PUT
  → Frontend calls ragConfirmUploads to update manifest

User clicks "Build Index"
  → Frontend calls ragTriggerIndex mutation
  → Lambda writes index_status.json = "indexing"
  → Lambda calls ECS RunTask → Fargate spins up this worker
  → Worker downloads docs from S3
  → Worker runs RAG-Anything (parse → chunk → embed → graph)
  → Worker uploads index artefacts to S3
  → Worker writes index_status.json = "ready"
  → Frontend polls ragGetIndexStatus every 10s until "ready"

User types a query
  → Frontend calls ragQuery
  → Lambda loads chunks.json from S3
  → Lambda does keyword matching (fallback; real vector search TBD)
  → Returns ranked chunks with source attribution
```
