> **Superseded (2026-10-10):** 云托管 containers cannot reach the CloudBase PostgreSQL. The Knowledge Service
> runs as an HTTP cloud function instead; see `deploy/ks/scf/README.md`. This folder still provides
> `make_context.py`, which builds `dist/`, and the 云托管 package if that network path is ever fixed.

# Knowledge Service on Tencent CloudBase (public plane, CN)

Target: CloudBase environment `sccb0-d0gc5398xf028be6a` (ap-shanghai), 云托管 service `ecan-knowledge`. The
service is reached over the 云托管 HTTPS domain, and the CN app signs in with CloudBase.

## What the service needs

| setting | value |
|---|---|
| `KS_DB_URL` | `postgresql+psycopg://<user>:<password>@<host>:5432/ecan_ks`. Use a new database `ecan_ks` on the existing PostgreSQL `postgres-khj3tzyk`, with the service in the same VPC/subnet as the GraphQL SCF. |
| `KS_CLOUDBASE_ENV_ID` | `sccb0-d0gc5398xf028be6a`. App sign-in is checked with CloudBase `/auth/v1/user/me`. |
| `KS_ALLOW_TENANT_CREATE` | `1`: merchants create their own organisation on first use. |
| `KS_EMBED_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `KS_EMBED_MODEL` | `text-embedding-v4` (DashScope; confirm it is the Qwen3-Embedding generation before go-live, and re-run `rag_benchmark/ecommerce` against it) |
| `KS_EMBED_API_KEY` | DashScope API key. Store it as a 云托管 secret / environment variable, never in the repository. |

Recommended service settings:
- port 8080;
- 0.5 CPU / 1 GB to start;
- minimum instances 1, to avoid a cold start that rebuilds each tenant's in-memory index;
- maximum instances 1 until the index moves to pgvector. Each instance holds its own in-memory index, so more than
  one instance would need cache invalidation across instances.

## Steps

1. Install and sign in to the CloudBase CLI. Signing in opens a browser, so the account owner runs it:

   ```powershell
   npm i -g @cloudbase/cli
   tcb login
   ```

2. Create the database once:

   ```sql
   CREATE DATABASE ecan_ks;
   CREATE USER ecan_ks WITH PASSWORD '...';
   GRANT ALL PRIVILEGES ON DATABASE ecan_ks TO ecan_ks;
   ```

   KS creates its tables on start.

3. Build the upload folder and deploy:

   ```powershell
   python deploy/ks/tcb/make_context.py
   tcb cloudrun deploy -e sccb0-d0gc5398xf028be6a -s ecan-knowledge --port 8080 --source deploy/ks/tcb/dist
   ```

   Set the environment variables above in the 云托管 console (or with `--envParams`), and bind the VPC.

4. Check it:

   ```powershell
   curl https://<service-domain>/v1/health
   ```

   Expected: `{"status":"ok","plane":"public",...}`.

5. In the app (CN build), add the server under **Knowledge → Product Knowledge → Servers**: choose **Cloud**, enter
   `https://<service-domain>`, and set sign-in to **Use my eCan sign-in**. Then press **Test**.

## Rollback

Delete the `ecan-knowledge` service, or set its traffic to 0. The app keeps working on its local knowledge; the
connection only adds a source.
