# Knowledge Service deployment

The Knowledge Service (`knowledge/ks`) runs in three places:

| plane | where | how |
|---|---|---|
| local | inside the eCan desktop app | nothing to deploy |
| private | the customer's own server (on-prem) | `docker-compose.private.yml` |
| public | our cloud, multi-tenant | `docker-compose.cloud.yml` behind HTTPS |

Desktop users add a server under **Knowledge → Product Knowledge → Servers**. Admins then manage people under
**Members & access**.

## Private server (on-prem)

Reference hardware: 2 × RTX PRO 5500 (84 GB each), a strong CPU, NVIDIA driver plus the NVIDIA Container Toolkit.

| GPU | service | default model (benchmark before go-live) |
|---|---|---|
| 0 | `llm` | 30B-class instruct, FP8 (about 32 GB of weights, the rest is KV cache for concurrency) |
| 1 | `embed`, `rerank`, optional `vlm` | 4B-class embedding and reranker, about 25 % of the card each; VLM on the remainder |

### Offline install (no internet on the server)

On a machine with internet access:

```bash
docker build -f deploy/ks/Dockerfile.ks -t ecan/knowledge-service:1 .
docker pull pgvector/pgvector:pg16
docker pull vllm/vllm-openai:latest
docker save ecan/knowledge-service:1 pgvector/pgvector:pg16 vllm/vllm-openai:latest | gzip > ecan-private-images.tar.gz
# download the model folders (huggingface-cli / modelscope) into ./models/<name>
```

Carry `ecan-private-images.tar.gz`, `models/`, and `deploy/ks/` to the server, then:

```bash
gunzip -c ecan-private-images.tar.gz | docker load
cp .env.example .env    # fill in passwords, secret, bootstrap admin, model folder names
KS_TAG=1 docker compose -f docker-compose.private.yml up -d
docker compose -f docker-compose.private.yml --profile multimodal up -d vlm   # optional
curl http://127.0.0.1:8790/v1/health
```

### First sign-in and access

1. In the eCan app, open **Servers**, choose **Add server**, select **Private (on-prem)**, enter
   `http://<server-ip>:8790`, and set sign-in to **Server account**.
2. Sign in with `KS_BOOTSTRAP_ADMIN`. **Test** shows the organisation id; save it in the connection.
3. Under **Members & access** (manage on: your server), invite colleagues by email and create groups (for example FAE
   or Sales). Mark knowledge bases confidential where needed.
4. When `KS_COGNITO_*` or `KS_OIDC_*` is set, colleagues sign in with their usual eCan account. Invited emails
   activate on first sign-in. Set an email domain to let everyone from the company join as viewers.
5. Remove `KS_BOOTSTRAP_ADMIN` once real admins exist.

### What stays private

- Knowledge, questions and answers stay on this server. Clients send questions to it over the LAN.
- Answers from a private server are tagged `private`. The eCan agent then refuses to pass them to any model that is
  not on loopback, a private network, or `ECAN_PRIVATE_LLM_HOSTS`.
- Sign-in through Cognito or CloudBase sends only the sign-in to the cloud. Signing keys are cached in `/data`, so
  token checks keep working when the internet link drops. With local accounts only, no cloud is involved at all.

## Cloud (public plane)

```bash
docker compose -f docker-compose.cloud.yml up -d
```

- Run it behind the existing HTTPS gateway. Clients refuse `http://` for cloud connections.
- Use managed PostgreSQL (`KS_DB_URL`).
- Merchants create their own organisation on first use (`KS_ALLOW_TENANT_CREATE=1`).

## Status

- Verified in tests: the server, auth, permissions, routing and the private-data guard. The tests use an in-process
  server and SQLite.
- Not yet verified:
  - the compose files on real GPUs;
  - vLLM embedding and rerank flags on a specific vLLM version;
  - PostgreSQL at scale.

  Treat the first install as a pilot, and run `rag_benchmark` against it.
- Search runs on an in-memory index built per tenant from the database. That is fine up to hundreds of thousands of
  chunks per tenant; the pgvector / Milvus backends are planned (docs/RAG_ENTERPRISE_PLAN.md §3.5).
