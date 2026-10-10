# Knowledge Service on CloudBase as an HTTP cloud function (CN public plane)

**Why a function and not 云托管.** 云托管 containers can't reach the CloudBase PostgreSQL: the connection to
`172.17.0.16:5432` times out, even though they sit in the same VPC/subnet as the cloud functions that can reach it.
eCan_lambda's notes record the same open issue for the SSE gateway. Functions reach the database, so the Knowledge
Service runs as one.

## Deploy (from this machine; commands run on the CVM, where `tcb` is logged in)

```bash
python deploy/ks/tcb/make_context.py           # -> deploy/ks/tcb/dist (knowledge/ks only)
scp -i C:/qcloud/tcsh0.pem -r deploy/ks/tcb/dist deploy/ks/scf/scf_bootstrap deploy/ks/scf/requirements-scf.txt \
    ubuntu@49.235.169.108:ks-deploy/
scp -i C:/qcloud/tcsh0.pem deploy/ks/scf/deploy.sh ubuntu@49.235.169.108:ks-deploy/deploy-scf.sh
ssh -i C:/qcloud/tcsh0.pem ubuntu@49.235.169.108 'cd ~/ks-deploy && bash deploy-scf.sh ecan-knowledge-test'
ssh -i C:/qcloud/tcsh0.pem ubuntu@49.235.169.108 \
    'cd ~/ks-deploy && python3 e2e_check.py https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/knowledge-test'
```

What the deploy script does, every time:

1. **Stage** `knowledge/ks` plus Linux wheels for Python 3.10 (about 180 MB, uploaded through COS).
2. **Deploy** as an HTTP function.
3. **Set the route** to `WEB_SCF`. `fn deploy --path` makes an `SCF` route that answers `FUNCTIONS_PARAM_INVALID`.
4. **Restore the environment and VpcConfig.** `fn deploy --force` resets both. The secrets are copied from
   `llm_proxy` inside the cloud and verified.
5. **Health-check** `/v1/health`. When the database is unreachable it reports `degraded` with the reason (no
   secrets) instead of crash-looping.

| service | schema | route |
|---|---|---|
| `ecan-knowledge-test` | `knowledge_test` | `/api/knowledge-test` |
| `ecan-knowledge` | `knowledge` | `/api/knowledge` |

**New schema** (once per schema, the same way as `langgraph`): `remote_create_schema.sh knowledge` creates it,
owned by `cloudbase_postgres` with USAGE and CREATE for `ecanai`.

**Sign-in.** The CN app's 30-day eCan session token (`ECAN_JWT_SECRET`), or a CloudBase access token checked with
`/auth/v1/user/me`.

**Embeddings.** Through `llm_proxy` with the internal token, `source=lightrag`, billed to the tenant owner.

## Verified (2026-10-10, `ecan-knowledge-test`)

`e2e_check.py`: 10/10 pass.
- Health check, bad token rejected, session token accepted.
- Tenant, store, product and policy writes (15 tables in `knowledge_test`, none in `public`).
- Embeddings via `llm_proxy`.
- Product-fact, paraphrased-FAQ and store-rule searches, about 0.5 s each.
- Cold start about 1.3 s.

## Production (2026-10-10, `ecan-knowledge`)

- **URL:** `https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/knowledge`, schema `knowledge`.
- **Checks:** health ok in 0.56 s; requests without a token or with a bad token get 401; 15 tables created in
  `knowledge`; the other routes (graphql, llm-proxy, ws, publish) are unchanged.
- **Not run on production:** the full `e2e_check.py`, because it writes a synthetic organisation. Run it against
  the test twin instead.
- **Routes:** a new route must name a real domain. `tcb routes add` rejects `*`, so the script uses
  `<env>.service.tcloudbase.com`, and CloudBase mirrors the route to the `app.tcloudbase.com` domain.
