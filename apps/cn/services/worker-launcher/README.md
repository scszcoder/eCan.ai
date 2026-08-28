# CN TKE Worker Launcher

Internal service used by `agentScheduler`. It verifies HMAC requests, prevents
replays, creates a resource-limited TKE Job from one configured image, and
persists current/history run records in PostgreSQL.

Before creating a Job it verifies that `agent_tasks.id` belongs to the supplied
authenticated owner. The worker receives only task/owner identifiers and small
options; it loads the authoritative task definition from the CN backend instead
of receiving an S3 payload assembled by Scheduler.

Apply `schema.sql`, build the image, create the `ecan-workers` namespace and a
service account allowed only to create/get/list Jobs in that namespace. Expose
`POST /jobs` only through an internal load balancer or service mesh; do not
publish it to the internet. `deployment.yaml` uses a TKE internal-CLB annotation;
replace the subnet placeholder with a subnet reachable from the Scheduler SCF.

Required variables: `DATABASE_URL`, `WORKER_LAUNCH_SECRET`, `WORKER_IMAGE`.
Optional variables configure namespace, service account, database pool and
CPU/memory requests and limits. `WORKER_SECRET_NAME` selects a fixed Kubernetes
Secret containing runtime-only CN backend credentials; callers cannot override
it. The Launcher secret must equal
`TENCENT_WORKER_LAUNCH_SECRET` on agentScheduler.

Run `npm test` before building. Production also requires PostgreSQL and TKE
integration tests; the unit test uses injected fakes and does not contact cloud
resources.
