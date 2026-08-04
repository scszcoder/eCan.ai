const http = require('node:http');
const k8s = require('@kubernetes/client-node');
const { Pool } = require('pg');
const { launch } = require('./core');

const required = (name) => { if (!process.env[name]) throw new Error(`${name} is required`); return process.env[name]; };
const config = {
  secret: required('WORKER_LAUNCH_SECRET'), image: required('WORKER_IMAGE'),
  namespace: process.env.WORKER_NAMESPACE || 'ecan-workers',
  serviceAccount: process.env.WORKER_SERVICE_ACCOUNT || 'ecan-cloud-worker',
  workerSecret: process.env.WORKER_SECRET_NAME || 'ecan-cloud-worker',
  resources: {
    requests: { cpu: process.env.WORKER_CPU_REQUEST || '250m', memory: process.env.WORKER_MEMORY_REQUEST || '512Mi' },
    limits: { cpu: process.env.WORKER_CPU_LIMIT || '2', memory: process.env.WORKER_MEMORY_LIMIT || '4Gi' },
  },
};
const pool = new Pool({ connectionString: required('DATABASE_URL'), max: Number(process.env.DB_POOL_SIZE || 5), ssl: process.env.DB_SSL === 'true' ? { rejectUnauthorized: true } : undefined });
const kc = new k8s.KubeConfig(); kc.loadFromCluster();
const batch = kc.makeApiClient(k8s.BatchV1Api);
const jobs = { async create(namespace, body) { const response = await batch.createNamespacedJob({ namespace, body }); return response.metadata?.uid || response.metadata?.name || body.metadata.name; } };
const store = {
  async authorize(p) {
    const result = await pool.query('SELECT 1 FROM agent_tasks WHERE id=$1 AND owner=$2 LIMIT 1', [p.task_id, p.owner_id]);
    return result.rowCount === 1;
  },
  async claim(id, p) {
    const inserted = await pool.query('INSERT INTO worker_launch_requests(request_id, owner_id, task_id, status) VALUES($1,$2,$3,$4) ON CONFLICT (request_id) DO NOTHING RETURNING request_id', [id, p.owner_id, p.task_id, 'launching']);
    if (inserted.rowCount === 1) return { claimed: true, runId: null };
    const prior = await pool.query('SELECT run_id FROM worker_launch_requests WHERE request_id=$1', [id]);
    return { claimed: false, runId: prior.rows[0]?.run_id || null };
  },
  async complete(id, p, runId) {
    const client = await pool.connect();
    try { await client.query('BEGIN');
      await client.query('UPDATE worker_launch_requests SET status=$2, run_id=$3, updated_at=now() WHERE request_id=$1', [id, 'running', runId]);
      await client.query('INSERT INTO cloud_task_runs(owner_id,task_id,run_id,schedule,meta_data,updated_at) VALUES($1,$2,$3,$4,$5,now()) ON CONFLICT(owner_id,task_id) DO UPDATE SET run_id=EXCLUDED.run_id,schedule=EXCLUDED.schedule,meta_data=EXCLUDED.meta_data,updated_at=now()', [p.owner_id,p.task_id,runId,p.schedule || '',p.meta_data || {}]);
      await client.query('INSERT INTO cloud_task_run_history(owner_id,task_id,run_id,schedule,meta_data) VALUES($1,$2,$3,$4,$5)', [p.owner_id,p.task_id,runId,p.schedule || '',p.meta_data || {}]);
      await client.query('COMMIT');
    } catch (e) { await client.query('ROLLBACK'); throw e; } finally { client.release(); }
  },
  async fail(id, message) { await pool.query('UPDATE worker_launch_requests SET status=$2,error=$3,updated_at=now() WHERE request_id=$1', [id,'failed',String(message).slice(0,2000)]); },
};

http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/healthz') { res.writeHead(200); return res.end('ok'); }
  if (req.method !== 'POST' || req.url !== '/jobs') { res.writeHead(404); return res.end(); }
  let rawBody = ''; for await (const chunk of req) { rawBody += chunk; if (rawBody.length > 262144) { res.writeHead(413); return res.end(); } }
  try {
    const result = await launch({ rawBody, headers: { timestamp: req.headers['x-ecan-timestamp'], signature: req.headers['x-ecan-signature'] }, config, store, jobs });
    res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(result));
  } catch (error) { res.writeHead(/signature|Expired|authentication/.test(error.message) ? 401 : /already in progress/.test(error.message) ? 409 : 400, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ error: error.message })); }
}).listen(Number(process.env.PORT || 8080));
