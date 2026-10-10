# Enterprise RAG plan (branch `rag-enterprise`)

Branched from `master` at `0253f4805`. This document is the source of truth for the enterprise RAG work.
Section 9 tracks execution status.

## 0. Scenarios and constraints

1. **E-commerce merchants.** A merchant owns one or more stores. A store is either a specialist (one category,
   e.g. clothing) or a broad mixed catalog (Walmart-style). RAG answers buyer questions in 千牛 / 飞鸽 / 拼多多.
   **Merchants prepare and ingest their own documents through the eCan app.** One product is often sold in
   several of the merchant's stores, and store policies differ only slightly between stores.
2. **Semiconductor design houses (enterprises).** Broad product lines, plus documents from other departments
   (HR, legal, sales policy). Many customers want **true on-prem**, with the whole stack physically in-house.

Data classes:

- **Private (proprietary).** Stays on an in-house server running its own LLMs. Reference box: 2 × RTX PRO 5500
  with 84 GB each, plus a strong CPU.
- **Public.** May be hosted in our cloud (TCB for CN, AWS for intl).

Ingestion and retrieval route between the two automatically. The RAG layer has its own users and permissions,
separate from app sign-in.

Working constraints:

- **No on-prem hardware is available for development.** On-prem pieces get a clean interface, a configuration
  surface and a mock/fake implementation for tests. They cannot be validated on real metal yet.
- **Every feature added or changed in the RAG layer ships with its GUI** in the app's Knowledge page. The GUI
  must be easy to read, easy to operate and informative. Every long job (ingest, import, re-index, rebuild)
  shows a progress indicator with stage, count and errors.

---

## 1. Current state (review of master @ 0253f4805)

### 1.1 How it is built

| Area | What exists |
|---|---|
| **Desktop RAG** | One LightRAG 1.5.6 HTTP subprocess per app session on port 9621 (`gui/MainGUI.py:2383`, `knowledge/lightrag_server.py:1471`, `knowledge/lightrag_launcher.py:917-971`). File-based storage: JSON KV, Faiss, NetworkX (`lightrag_server.py:358-361`). Data lives in the user's profile directory. |
| **Knowledge bases** | LightRAG workspaces: bare folder names under `rag_storage`, selected per request by the `LIGHTRAG-WORKSPACE` header (`knowledge/lightrag_client.py:35-51`). They have no owner, description or ACL. |
| **Ingestion** | Parser rules for native, MinerU and Docling (`knowledge/lightrag_parser_config.py`). A table-aware chunker is injected by monkeypatching `LightRAG.__init__` (`lightrag_launcher.py:113-162`). Uploads carry **no document metadata** (`lightrag_client.py:150-155`). |
| **Query** | MCP tool `rag_query` (`agent/ec_skills/rag/local_rag_mcp.py:234-563`). The LLM fills a free-text `workspace` argument. A confidence scorer and off-topic gate run on top (`knowledge/lightrag_confidence_scorer.py`). |
| **Cloud (AWS)** | `rag_worker` is a one-shot Fargate indexer that writes to `s3://ecan-rags/{sub}/{pid}`. Queries are a Lambda keyword search over `chunks.json`. |
| **Cloud (CN)** | CloudBase `rag_index_event`: no LightRAG, DashScope embeddings, cosine search over `vectors.jsonl`. Its source is not in this repo. |
| **GUI** | Desktop-only LightRAG page with four tabs (`gui_v2/src/pages/Knowledge/LightRAGPorted/`). A web-only `pages/RAG/RAGDocuments.tsx` hard-coded to `pid='default'`. Dead legacy permission/collaboration pages (`pages/Knowledge/components/*`, backed by localStorage). |
| **Agents** | E-commerce Q&A runs classifier LLM → an LLM turn that calls `rag_query` / `query_*` → answer LLM (`docs/FEIGE_QA_TOKEN_COST.md`). `store_id` never reaches RAG. The buyer's product card reaches the LLM only as plain text. |
| **Identity** | Tokens carry email, sub, phone and openid only. They are decoded without signature verification (`auth/auth_manager.py:389`). The "org" tree groups AI agents, not people (`agent/db/models/org_model.py`). |

### 1.2 Defects (Phase 0)

All of these are in **eCan.ai's own LightRAG server and its GUI/agent glue**: the RAG engine the desktop app
starts on each user's PC. They are not in `rag_benchmark`, which is a separate test harness that only measures
RAG engines.

| # | Defect | Where |
|---|---|---|
| 1 | `statistics.pstdev` is used but `statistics` is never imported. With 2 or more scored chunks this raises NameError, the handler returns `should_answer=False`, and valid answers are probably replaced by the no-answer text. | `knowledge/lightrag_confidence_scorer.py:315` |
| 2 | `HOST=0.0.0.0` with no `LIGHTRAG_API_KEY`. Anyone on the same Wi-Fi or LAN can read or delete the merchant's knowledge base. | `resource/data/lightrag_template.env:6,84` |
| 3 | A fast path, on by default, forces naive mode without rerank. The 10 s MCP timeout returns an empty answer. In the Q&A logs, 270 calls returned zero references. | `local_rag_mcp.py:379-387`, `agent/mcp/local_client.py:108-121` |
| 4 | When rerank is disabled, the passthrough returns `relevance_score=1.0`, which inflates confidence. The "Ollama rerank" is a sigmoid of an embedding sum. | `gui/lightrag_rerank_proxy.py:437-448,494-504` |
| 5 | Graph API, query history and clear-cache ignore the selected workspace. Clear-cache wipes the whole `WORKING_DIR`. | `gui_v2/src/services/ipc/lightragApi.ts:190-268`, `lightrag_handler.py:590-632,2287-2400` |
| 6 | `deleteWorkspace` deletes `lightrag_{name}`, but the workspace list reads `rag_storage/<name>`. | `lightrag_handler.py:1711-1755` vs `1817-1827` |
| 7 | TLS verification is off by default. | `lightrag_server.py:489-490` |
| 8 | `rag_worker` logs the first 8 characters of the OpenAI key. | `rag_worker/main.py:217,456` |
| 9 | The `ids` filter is documented but never forwarded. | `lightrag_client.py:346` vs `:380-399` |
| 10 | Two workspace-switch models conflict: a per-request header, and an env rewrite plus server restart. | `SettingsTab.tsx:448-525` |

### 1.3 Lessons carried over from `rag_benchmark`

- **Sister-document confusion is the dominant failure.** 33 of 108 calls retrieved only sister-datasheet chunks
  (mean score 0.34, versus 0.70 when a gold page was hit). Similar products, such as the same shirt in two
  fabrics, are the e-commerce version of this problem. **Scoping retrieval by product or part is the single
  largest accuracy lever.**
- Second hops fail, and only about 3.5 chunks per call reach the LLM, so the agent layer needs a second
  retrieval step.
- Figures and plots need a VLM description at ingest time.
- Selection and parametric questions are structured problems. A catalog with a filter beats RAG
  (`build_selection.py`).

---

## 2. Architecture

**Core decision:** LightRAG stays an engine. It is not forked into a multi-tenant product. A new
**eCan Knowledge Service (KS)** owns identity, permissions, the product catalog, document metadata, plane
routing, the fast product Q&A path and audit.

```
 Desktop app / Web app / LangGraph agents
                 │   bearer token (Cognito | CloudBase; enterprise OIDC later)
        ┌────────▼──────────┐
        │ Knowledge Service │  verify → principal → policy → plan → retrieve → merge/rerank → taint tag
        │                   │  tenants, KBs, grants, documents, products, listings, policies, jobs, audit
        └──┬────────────┬───┘
   private │            │ public (outbound only from on-prem)
 ┌─────────▼────────┐  ┌▼──────────────────────────────┐
 │ On-prem plane    │  │ Cloud plane (TCB CN / AWS intl)│
 │ LightRAG + PG    │  │ PG(+pgvector) / LightRAG       │
 │ vLLM, embed,     │  │ cloud LLMs                     │
 │ rerank, VLM      │  └────────────────────────────────┘
 └──────────────────┘
```

### 2.1 Two retrieval paths under one service

This is how the speed vs accuracy trade-off is resolved.

| | **A. Fast product Q&A** | **B. Deep document search** |
|---|---|---|
| Used for | E-commerce customer service | Datasheets, design docs, enterprise policies |
| Engine | KS's own lean pipeline: product table + filtered keyword/vector search + rerank. **No LLM calls inside retrieval.** | LightRAG (vector, optional graph, optional VLM), with agentic multi-hop on top |
| Latency target | Retrieval < 0.6 s, end-to-end 1.5–3 s (dominated by the answer LLM) | 5–20 s |
| Scoping | Store → product (from the product card) → doc type | Tenant → group → product family / part number |

LightRAG's graph adds little for FAQs and product facts. Its `mix` mode also spends an LLM call on keyword
extraction, and it cannot filter by metadata. That is why path A does not go through LightRAG.

### 2.2 Deployment modes

| Mode | Who | Where KS and its ACL DB run | Identity |
|---|---|---|---|
| **Cloud** | Merchants, small teams | Our cloud, multi-tenant | Cognito / CloudBase |
| **On-prem** | Enterprises (expected to be many) | Their own server, physically in-house | **Cloud sign-in (v1).** Enterprise OIDC/LDAP is a later plug-in. |
| **Desktop local** | Single user, offline | Inside the app | App sign-in |

#### Decision: on-prem users still sign in through the cloud (v1)

Sign-in only proves who the user is. **Documents, queries and answers never leave the on-prem server.** Only
the user's identity (email) and login events touch the cloud. The on-prem KS verifies cloud-issued tokens
against cached Cognito/CloudBase signing keys.

Consequences and mitigations:

- **Air-gapped sites cannot log in.** The identity layer stays pluggable (an `IdentityProvider` interface) so
  enterprise OIDC/LDAP can be added for those customers.
- **Group membership is managed in the on-prem KS admin UI.** Sync with the company directory comes later.
- **Off-boarding.** A departed employee's cloud account still exists. Each tenant is tied to a verified email
  domain: matching users can join, and the admin can revoke anyone. Directory sync comes later.
- **Updates.** On-prem installs ship as offline packages (images plus model weights). No call-home is required
  other than sign-in.

### 2.3 Identity and permissions (separate from app sign-in)

**Tables**, owned by KS: SQLite on desktop, PostgreSQL on servers, same SQLAlchemy models.

| Table | Contents |
|---|---|
| `tenant` | A merchant or an enterprise; verified email domain |
| `membership` | User → tenant, with a role: owner, admin, editor or viewer |
| `group` | Department or team |
| `kb` | Tenant, plane, sensitivity, index profile, owner, description |
| `kb_grant` | A principal (user, group, agent or store) with read, write or manage |
| `document` | KB, metadata, labels, per-plane status, content hash |
| `job` | Long-running work, with stage, progress, errors |
| `audit_log` | Who did what, when |

Plus the catalog tables in §3.

**Rules:**

- **A permission boundary is always a hard partition boundary** (LightRAG workspace, or a mandatory
  `tenant_id`/`kb_id` predicate in KS queries). Metadata only narrows relevance inside the boundary. Filtering
  results after retrieval is never used for security.
- **Agents act for a principal.** The harness injects the principal (user, store, tenant) out-of-band. The LLM
  never chooses it. Agents can hold their own grants.

### 2.4 Private / public routing

- **Each KB has a fixed plane** (`local`, `private` or `public`). A document's plane follows its KB.
- **An optional ingest classifier** runs on the private plane and flags confidential markers.
  **It never moves data from private to public automatically.** When unsure, data stays private.
- **Retrieval** fans out to the permitted KBs on both planes, then merges and reranks centrally.
- **Taint rule.** Every result carries `sensitivity`. If any private chunk enters a context, every downstream
  LLM step must run on a private model. The LangGraph harness gets a guard for this.
- **Per-tenant policy switches:**
  - May query text be sent to the public plane?
  - May public results join private answers? (Always safe.)

### 2.5 Engine changes (LightRAG, path B)

1. **Upgrade** from 1.5.6 to the current upstream release, which adds role-specific LLMs and RAG-Anything
   multimodal. Re-audit the monkeypatches.
2. **PostgreSQL storage on servers.** File storage stays for desktop.
3. **Index profiles per KB:** `vector`, `vector+graph`, `vector+graph+mm`.
4. **Metadata:**
   - Inject a scope prefix (part number, SKU, product) into chunks.
   - Add a `doc_id` filter on the PG backend.
   - Forward `ids`.
5. **Namespace graph entities** (`FT62F0Mx::ADC`), or use one workspace per product family.
6. **Quality fixes:** scorer bug, a real reranker, honest confidence.

### 2.6 Private server sizing (2 × 84 GB)

| GPU | Workload |
|---|---|
| GPU 0 | Main LLM on vLLM (answer, planning, graph extraction). A 30B-class FP8 model leaves about 45 GB for KV cache and concurrency. A 70B-class FP8 model also fits, with less concurrency. Benchmark both. |
| GPU 1 | VLM (30B-class MoE, FP8), embedding model, reranker, MinerU GPU backend |
| CPU | PostgreSQL + pgvector, KS, parse queue |

- Query traffic has priority. Bulk ingest runs in a low-priority queue.
- A 235B-class model, even at 4-bit, would take both cards. Not recommended.
- **Without hardware:** KS talks to the private plane only through OpenAI-compatible LLM, embedding and rerank
  endpoints plus the LightRAG HTTP API, all configured by URL. Tests use fakes, and a CPU-only Docker Compose
  profile can stand in.

---

## 3. E-commerce product knowledge (path A)

### 3.1 Not everything goes into vectors

| Kind | Examples | Store | Lookup |
|---|---|---|---|
| **Structured facts** | specs, material, size table, variants (color/size), weight | `product` table | Exact match by product id, < 50 ms |
| **Fast-changing facts** | price, stock, promotions | **Not stored.** Read from the live product card or platform tools (`query_price`, `query_inventories`) | Live. Stored copies go stale. |
| **Unstructured text** | selling points, manuals, care, FAQ, policies | Chunks + keyword index + vectors, all tagged | Filtered hybrid search |

Most customer-service questions ("what size for 170 cm", "is it cotton", "when does it ship") are answered
from the product record plus the store policy. **Once the product card names the product, no vector search is
needed.** Vector search handles the long tail.

### 3.2 Standard data model

```
Product            (owned by the merchant, shared by all of that merchant's stores)
  product_id, title, category, brand, attributes{k:v},
  variants[{sku, color, size, ...}], size_chart(table),
  selling_points, description, care, faq[{q,a}], images, docs[]
Listing            (one per store that sells the product)
  store_id, platform, platform_item_id(商品ID) -> product_id
Policy             (merchant default + per-store overrides that state only the differences)
  scope: merchant | store, topic(shipping/returns/invoice/after-sales/...), text
```

- **A product shared across stores** is ingested once and mapped through `Listing`. Every store's 商品ID
  resolves to the same product.
- **Policies inherit.** Retrieval reads the store override first, then the merchant default. The answer always
  cites the policy of the store the chat is in.

### 3.3 Ingestion: three entry points, one canonical record

1. **One product at a time** (best for small and mid-sized stores). Upload the product's PDF, Word file or
   detail-page images. The LLM extracts a draft record, and the merchant confirms or edits it in a pre-filled
   form.
2. **Bulk catalog import** (CSV, XLSX, JSON, such as a 千牛 or 抖店 product export). A column-mapping wizard
   maps the merchant's headers to canonical fields. Known header synonyms map automatically; the LLM can
   suggest the rest.
3. **Policy and FAQ documents** at store or merchant level.

**Data cleaning in the app** is automatic plus review, not a full ETL tool:

- normalise units and sizes, strip HTML, trim whitespace;
- de-duplicate by product id, title and content hash;
- detect contradictions (two materials for one SKU);
- show a validation report (errors, warnings, rows skipped);
- preview the chunks before committing.

**Tagging** is mostly automatic (category, product link, doc type), with merchant confirmation.

### 3.4 What gets vectorized

Every chunk carries `{tenant, kb, product_id?, store_id?, doc_type, category, lang}`.

- **One "product summary" chunk per product:** title, key attributes and selling points. It identifies the
  product when there is no card ("do you have a waterproof jacket").
- **FAQ entries.** The question is embedded and the stored answer is returned. This is the most precise path.
- **Description and manual text chunks.**
- **Policy clauses**, one chunk each.
- **Size charts:** a structured table for exact lookup, plus a text rendering for search.

### 3.5 Storage choice

Raw scale is rarely the problem. A small store has about 2k chunks, and 10k products is about 300k vectors,
which any index handles. What decides the choice:

1. **Metadata filtering** (product or store scope), the biggest accuracy lever.
2. **Hybrid keyword + vector search.** Chinese product questions are full of exact terms (型号, 尺码, 面料).
3. **Multi-tenant cloud scale.** Thousands of merchants means hundreds of millions of vectors, with concurrent
   writes and deletes.

| Backend | When |
|---|---|
| **Embedded** (SQLite + numpy/Faiss with id pre-filter, plus a BM25 keyword index) | Desktop and single-merchant local. Built first. |
| **PostgreSQL + pgvector** | Default for cloud and on-prem: products, vectors, ACL and audit in one transactional store. Comfortable up to tens of millions of vectors per deployment. Chinese full-text search needs zhparser or pg_jieba; check TCB managed PG support. |
| **Milvus** | When one deployment exceeds about 50M vectors or very high QPS. It has partition keys, scalar filters and hybrid sparse+dense search. |

All three sit behind one `VectorIndex` interface, so moving to Milvus is a swap, not a rewrite.

### 3.6 Retrieval tiers and latency budget (path A)

| Tier | What | Target |
|---|---|---|
| 0 | Product card present: fetch the product record and the store policy (cached) | < 50 ms |
| 1 | FAQ match within product and store scope. A high score answers directly. | 50–150 ms |
| 2 | Hybrid search filtered to the product, then rerank the top 20 to 5 | 200–600 ms |
| 3 | No card ("recommend", "do you have…"): search product summaries in the store's catalog | 300–800 ms |

- **LLM calls per chat** drop from 3 today (classifier → tool-call turn → answer) to 2 (planner → answer), or
  to 1 when a product card is present and retrieval is deterministic.
- **Accuracy levers, in order:**
  1. scope filtering;
  2. facts from the product record, not from the LLM reading chunks;
  3. FAQ matching;
  4. reranker;
  5. "not sure → hand off to a human" instead of guessing.
- **Flywheel.** Buyer questions answered by a human become suggested FAQ entries, which the merchant approves.

### 3.7 Channels

The Q&A skill is shared across channels. Per-channel work is only the mapping from platform item id to product
id through `Listing`. Pilot on the channel where the first real merchant has the most traffic. 飞鸽 captures
the richest product details (`product_detail_store.py`); 千牛 reliably provides the 商品ID.

### 3.8 Semiconductor mapping (path B)

- `tenant=enterprise` → groups (Eng, FAE, Sales, HR, Legal) → KBs:
  - one per product family (`vector+graph+mm`);
  - one per department policy set (`vector`, granted only to that group);
  - restricted KBs (errata, roadmap, NDA documents).
- Part-number detection scopes the query and surfaces cross-part conflicts.
- The parametric catalog tool handles part selection.

---

## 4. Agent layer (LangGraph harness)

1. **A retrieval planner node** replaces the Q&A routing classifier. It outputs
   `{intent, scope_hints, plan: structured|kb_search|both, need_clarify}`.
2. **One `kb_search` tool from KS**, replacing `rag_query`. The principal comes from harness context. On a
   product card it runs path A deterministically.
3. **Structured data before RAG.**
4. **Loops:** multi-hop second retrieval, conflict check, abstain.
5. **Taint guard, plus a latency/token budget.** When the budget runs out, return partial results marked as
   partial, never an empty answer.

## 5. GUI: the Knowledge page

Requirements for every feature: easy to read, easy to operate, informative, and long jobs show stage, progress,
count, ETA when known, and errors.

- **Knowledge bases:** a card list showing owner, a plane badge (Local / Private 🔒 / Public ☁), index profile,
  description, document count, health.
- **Members & permissions:** grant read, write or manage to users, groups, agents and stores.
- **Documents:** metadata columns, bulk edit, sensitivity labels, per-plane status, retry and abort.
- **Product catalog** (new):
  - product list with search and category filter;
  - product detail and edit form;
  - store listings;
  - import wizard: upload → column mapping → cleaning report → preview → commit, with a progress bar;
  - single-product ingest with an extracted-draft review.
- **Store policies:** a merchant default editor with per-store override diffs.
- **Retrieval test:** "ask as store X / product Y". Shows the tier used, timing per stage, sources, plane,
  scores and confidence.
- **Jobs panel:** all long-running jobs with live progress.
- **Audit log** (admin).

## 6. Phased plan

| Phase | Scope | Exit criteria |
|---|---|---|
| **0. Fix & secure** | Defects 1–10 in §1.2, with GUI where it is affected | Unit tests; server bound to localhost with an API key; workspace scope respected |
| **1. Measure** | `ecan` adapter in `rag_benchmark`; e-commerce test set (specialist + mixed store, shared products, policy overrides, similar-product traps, cross-merchant leak questions) | Baseline numbers |
| **2. KS core + path A (local)** | SQLAlchemy models (tenant / KB / grant / document / product / listing / policy / job / audit); embedded index (hybrid BM25 + vector, filtered); tiered retrieval; import pipeline with cleaning; IPC handlers | Unit tests; benchmark ≥ baseline on the e-commerce set; retrieval p95 < 600 ms locally |
| **3. Knowledge page GUI** | §5 for path A: product catalog, import wizard, policies, retrieval test, jobs panel | Usable end-to-end on desktop |
| **4. Agent integration** | `kb_search` MCP tool with principal injection; store → KB binding; planner prompt; taint guard | Q&A uses product scope; tests |
| **5. Permissions & identity** | Token verification (Cognito JWKS, CloudBase), roles, grants, members UI, audit | Permission tests, including cross-tenant prompt injection |
| **6. Planes** | `Plane` interface (local / private / public) with HTTP adapters; private-plane config UI; fan-out merge; taint tags; PG / pgvector backend | Fake-plane tests; leak test against a mock cloud endpoint |
| **7. Engine (path B)** | LightRAG upgrade, PG backend, profiles, entity namespacing | `rag_benchmark` FT62F0Mx ≥ baseline |
| **8. Enterprise extras** | OIDC/LDAP, directory sync, retention, dashboards | — |

## 7. Open decisions

- Should the product catalog sync from platform APIs later? For now the assumption is that merchants import it.
- Pick the first pilot channel once a pilot merchant is chosen.

## 8. Testing without on-prem hardware

- **Planes are configured by URL.** Tests use in-process fakes: an OpenAI-compatible stub and a LightRAG stub.
- **Leak tests** run a mock "public" endpoint that records every payload and assert that no private chunk text
  arrives.
- **Embeddings in tests** use a deterministic hashing embedder, so the tests need no model and no network.

## 9. Execution log

Status as of 2026-10-09, branch `rag-enterprise`.

| Phase | Status | Commits / notes |
|---|---|---|
| 0. Fix & secure | **Done** | See defect table below. |
| 1. Measure | **Done** | `rag_benchmark` branch `ecommerce-benchmark`: 30-question e-commerce set and `ecommerce/ks_adapter.py`. |
| 2. KS core + path A | **Done** | `knowledge/ks/*`: models, import, cleaning, chunking, hybrid index, tiered retrieval, jobs. |
| 3. Knowledge page GUI | **Done** | Product Knowledge tab: Overview, Products, Import, Store policies, Q&A test, Servers, Members & access, Jobs. |
| 4. Agent integration | **Done** | `rag_query` uses product knowledge first. Scope comes from run state (task `store_id`, product card `商品ID`). Store linking picker and sync. `docs/RAG_QA_SKILL_GUIDE.md`. The planner prompt itself is skill data and is described in the guide. |
| 5. Permissions & identity | **Done** | JWKS verification (Cognito / OIDC / CloudBase), local accounts, roles, grants, groups, confidential KBs, invites, domain auto-join, audit. |
| 6. Planes | **Done (software)** | KS HTTP server, RemoteKS + PlaneRouter, private-data guard in the harness, `deploy/ks` (compose for the private GPU box and the cloud). **Not run on real hardware or in the cloud yet.** |
| 7. Engine (path B, LightRAG) | **Not started** | LightRAG upgrade, PG backend, entity namespacing. Needs the desktop LightRAG server running for validation. |
| 8. Enterprise extras | Not started | Directory sync (SCIM/LDAP), retention, dashboards. |

Phase 0 defects:

| # | Status |
|---|---|
| 1 | Fixed: scorer import, plus restored the ws111 off-topic gate that the 1.5 rewrite had lost. |
| 2 | Fixed: loopback bind, API key, guest mode off. |
| 3 | Not changed: the fast path is a deliberate latency choice and is superseded by path A. Rationale in commit `79bc0d74d`. |
| 4 | Fixed: passthrough rerank scores ignored. |
| 5 | Fixed: workspace scope for graph, history and clear. |
| 6 | Fixed: workspace delete. |
| 7 | Fixed: TLS verification on by default, with a toggle. |
| 8 | Fixed: key prefix no longer logged. |
| 9 | Fixed: misleading `ids` documentation. |
| 10 | Fixed: the two workspace switches now stay in sync. |

**LAN sharing (commander → platoons), added after review.** Merchants run one commander and several platoon
machines on the same LAN, all serving stores from the commander's knowledge.

- LightRAG stays on 127.0.0.1. The commander exposes only `knowledge/ks/lan.py`'s gateway (default port 9630), and
  starts it automatically when its role is Commander.
- Platoons find the commander through zeroconf discovery and pair once with a 6-digit code. Codes last 10 minutes,
  are single-use, and pairing locks for a minute after 5 wrong codes.
- Each platoon gets its own revocable device token; only its hash is stored.
- Through the gateway, platoons get read-only product-knowledge search and the LightRAG query/graph routes. The
  commander adds its local API key, and the device token never reaches LightRAG.
- On a paired platoon, `LightragClient` and the plane router point at the commander.
- GUI: a LAN card in Product Knowledge → Servers, and a banner on platoons.

**Benchmark** (rag_benchmark/ecommerce, offline hashing embedder for both runs):

| run | score | fatal |
|---|---:|---:|
| path A, scoped | 90.0 | 0 |
| unscoped baseline (mimics the current fast path) | 36.7 | 12 |

The remaining misses are paraphrases that need a neural embedding model.

**Tests:**
- `tests/ks`: 73 Python tests, covering retrieval, import, IPC, the agent bridge, permissions, the server, planes and
  the guard.
- `gui_v2/src/tests/components/ProductKnowledge.test.tsx`: 5 GUI tests.
- RAG-related suites show no new failures against base `0253f4805`.

**Embedding (2026-10-09):** product knowledge has its own model setting. With Qwen3-Embedding-8B (Q4_K_M in
LM Studio for testing; full precision on the private server):

| set | Qwen3-Embedding-8B | offline matcher | unscoped baseline |
|---|---|---|---|
| main (30) | 100.0 | 90.0 | 31.7, 11 fatal |
| held-out (10) | 90.0, first clean run 70.0 | 40.0 | 40.0, 2 fatal |

The held-out set has since been used for diagnosis, so it is no longer clean. Margins between related and unrelated
similarities are thin (around 0.6–0.7), so a reranker is the next accuracy step.

**Open items:**
- **LAN commander/platoon test on two machines.** Deferred by the owner, since the second machine is busy.
- **TCB deployment.** The test twin `ecan-knowledge-test` is live as an HTTP cloud function and passes the
  end-to-end check (see `deploy/ks/scf/README.md`). The production schema `knowledge` exists. Deploying the
  production function `ecan-knowledge` needs the owner's go-ahead. AWS comes after the CN cut-over (§10).
- **Reranker** (Qwen3-Reranker) in path A.
- **A held-out set from real merchant chats.**
- **Validate `deploy/ks` on the 2 × RTX PRO 5500 box.**
- **Phase 7.**

## 10. CN cut-over: from `rag_*` functions to the Knowledge Service

Status 2026-10-10: plan only. Nothing in the app points at the new service yet.

### 10.1 What the CN web app does today

The web build's documents page (`pages/RAG/RAGDocuments.tsx`) and its store (`stores/ragStore.ts`, through
`services/web/presignedFileOps.ts`) make these calls:

| step | call | backend |
|---|---|---|
| upload | `rag_upload_signer_event` returns a COS URL, and the PHP relay uploads to `ecan-rags-1251680599/<owner>/<pid>/docs/<file>` | Event function + COS |
| register | GraphQL `reqRAGStore` | `ecan-graphql-api` |
| list | `rag_upload_signer_event` `listDocuments` | COS listing |
| index | `rag_index_event` `startIndex` / `getIndexStatus` over the whole pid | Event function, `vectors.jsonl` in COS |
| ask | `rag_index_event` `queryIndex`: cosine top-k, then a `qwen-plus` answer | Event function |
| delete | GraphQL `ragDeleteDocs` | `ecan-graphql-api` |

### 10.2 Gaps in the Knowledge Service before it can replace that

| # | gap | plan |
|---|---|---|
| 1 | **No general document route over HTTP.** Documents can only be attached to a product, from the desktop. | Add `POST/GET/DELETE /v1/tenants/{tid}/kbs/{kb}/documents` for knowledge-base documents that aren't tied to a product. Chunking and extraction are reused. |
| 2 | **Large uploads.** The HTTP gateway for functions limits the request body to a few MB, and the KS upload limit is 50 MB. | Keep the existing COS upload (`rag_upload_signer_event` and the relay). KS takes a COS key and reads the object itself, using the function role's COS access scoped to `ecan-rags`. A direct upload is used only for small files. |
| 3 | **No answer synthesis.** KS returns facts and chunks; the desktop agent writes the answer. | Add an `/answer` endpoint: KS search, then a chat call through `llm_proxy` (same internal token, `source=lightrag`, billed to the tenant owner). Public plane only. |
| 4 | **Browser access.** No CORS handling, and `ksApi.ts` only speaks desktop IPC. | Add CORS for the app origins (`KS_CORS_ORIGINS`) and a small HTTP client `services/web/ksHttp.ts`. It sends the CloudBase access token, which KS already verifies through `/auth/v1/user/me`. |
| 5 | **Multi-request flows on functions.** Instances don't share `/tmp`. | Done for catalog import, which can now re-send the file. The COS-key route (#2) removes the issue for documents. |
| 6 | **Index per instance.** Each instance rebuilds a tenant's index from the database on first use; the shared version keeps instances consistent. | Fine at current sizes. Move vectors to pgvector when a tenant passes ~50k chunks or a cold rebuild passes ~2 s. |

### 10.3 Steps

1. **Server parity** (gaps 1–4), with tests, then redeploy `ecan-knowledge-test` and extend `e2e_check.py` to
   cover upload by COS key, list, delete and `/answer`.
2. **Production function** `ecan-knowledge`, with the same script and the `knowledge` schema.
3. **Web client behind a switch.** `ragStore` picks the backend from app config, `knowledge.backend: legacy | ks`
   (default `legacy`). The old calls stay untouched while the switch is off.
4. **Migration per owner.** A one-off job run from the CVM:
   - for each `<owner>/<pid>/docs/*` in `ecan-rags`, create the owner's tenant if needed;
   - create one knowledge base per pid;
   - ingest the documents from COS.

   The old `vectors.jsonl` isn't reused, because chunking and models differ. The job is re-runnable, matching on
   file hash, and reports per owner.
5. **Staged rollout.** Turn the switch on for internal accounts, then everyone. Compare answers on a sample of real
   questions against the old function before the full switch.
6. **Desktop.** The CN build gets a built-in connection to `/api/knowledge` with "Use my eCan sign-in", so desktop
   agents can also search cloud knowledge (public plane; the private-data guard applies).
7. **Retire** `rag_index_event` and `rag_upload_signer_event`'s list action after 30 days without traffic. Keep
   the COS objects. Removing the functions is a separate, explicit decision.

### 10.4 Rollback

Set `knowledge.backend` back to `legacy`. The old functions and COS data are untouched until step 7.

